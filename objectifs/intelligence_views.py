from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, FormView
from accounts.roles import LEARNER
from config.forms import BootstrapFormMixin
from .views import ManagerMixin
from .models import DisponibiliteApprenant
from .statistiques import objectifs_visibles
from .intelligence import calcul_charges, recherche_sens, recherche_locale, donnees_besoins, regrouper_besoins


class DisponibiliteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DisponibiliteApprenant
        fields = ['minutes_semaine']
        help_texts = {'minutes_semaine': 'Exemple : 180 minutes = 3 heures par semaine. Laissez vide si vous ne savez pas encore.'}


class DisponibiliteView(PermissionRequiredMixin, FormView):
    permission_required = 'objectifs.view_objectifapprentissage'
    form_class = DisponibiliteForm
    template_name = 'objectifs/disponibilite.html'
    success_url = reverse_lazy('objectifs:charge')

    def has_permission(self):
        return self.request.user.groups.filter(name=LEARNER).exists() and super().has_permission()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = DisponibiliteApprenant.objects.filter(utilisateur=self.request.user).first()
        return kwargs

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.utilisateur = self.request.user
        obj.save()
        messages.success(self.request, 'Disponibilité enregistrée.')
        return super().form_valid(form)


class ChargeView(PermissionRequiredMixin, TemplateView):
    permission_required = 'objectifs.view_objectifapprentissage'
    template_name = 'objectifs/charge.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        goals = list(objectifs_visibles(self.request.user))
        charges = calcul_charges(goals)
        ctx['rows'] = [{'goal': goal, 'charge': charges[goal.pk]} for goal in goals]
        ctx['is_learner'] = self.request.user.groups.filter(name=LEARNER).exists()
        return ctx


class RechercheForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label='Que souhaitez-vous apprendre ?', max_length=300, widget=forms.TextInput(attrs={'placeholder': 'Je veux apprendre à répéter des instructions'}))


def quota_session(request):
    now = timezone.now().timestamp()
    if request.session.get('derniere_analyse', 0) > now - 30:
        raise ValueError('Attendez 30 secondes avant un nouvel appel Gemini.')
    request.session['derniere_analyse'] = now


class RechercheSensView(PermissionRequiredMixin, FormView):
    permission_required = 'objectifs.view_objectifapprentissage'
    form_class = RechercheForm
    template_name = 'objectifs/recherche_sens.html'

    def form_valid(self, form):
        goals = list(objectifs_visibles(self.request.user)[:101])
        ctx = self.get_context_data(form=form, recherche_effectuee=True, limite=len(goals)>100)
        goals = goals[:100]
        if not goals:
            ctx['results'] = []
        else:
            try:
                quota_session(self.request)
                ctx['results'] = recherche_sens(form.cleaned_data['q'], goals)
                ctx['moteur'] = 'Gemini — recherche par sens'
            except ValueError as error:
                ctx['results'] = recherche_locale(form.cleaned_data['q'], goals)
                ctx['moteur'] = 'Recherche locale par concepts — sans analyse IA'
                ctx['erreur'] = str(error)
        return self.render_to_response(ctx)


class BesoinsView(ManagerMixin, TemplateView):
    permission_required = 'objectifs.view_objectifapprentissage'
    template_name = 'objectifs/besoins.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        records = donnees_besoins(objectifs_visibles(self.request.user))
        ctx.update(records=records[:40], nombre_travaux=len(records), nombre_apprenants=len({r['apprenant'] for r in records[:40]}), limite=len(records)>40)
        return ctx

    def post(self, request, *args, **kwargs):
        ctx = self.get_context_data()
        if ctx['nombre_apprenants'] < 2:
            ctx['erreur'] = 'Données insuffisantes : il faut des réponses rendues par au moins deux apprenants distincts.'
        else:
            try:
                quota_session(request)
                ctx['groupes'] = regrouper_besoins(ctx['records'])
                ctx['analyse_effectuee'] = True
            except ValueError as error:
                ctx['erreur'] = str(error)
        return self.render_to_response(ctx)
