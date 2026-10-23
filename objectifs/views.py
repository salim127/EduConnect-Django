from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from accounts.roles import is_admin
from config.mixins import QueryStringMixin
from .forms import ObjectifForm, TacheForm, TacheTravailForm, TacheValidationForm
from .access import is_manager
from .models import ObjectifApprentissage, TacheApprentissage


class ManagerMixin(PermissionRequiredMixin):
    def has_permission(self):
        return is_manager(self.request.user) and super().has_permission()


class OwnedMixin(PermissionRequiredMixin):
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_manage_objectifs'] = is_manager(self.request.user)
        return ctx

    def get_queryset(self):
        qs = super().get_queryset()
        if is_admin(self.request.user):
            return qs
        field = 'proprietaire' if self.model == ObjectifApprentissage else 'objectif__proprietaire'
        if is_manager(self.request.user):
            return qs.filter(**{field: self.request.user})
        learner_field = 'apprenant' if self.model == ObjectifApprentissage else 'objectif__apprenant'
        return qs.filter(**{learner_field: self.request.user})


class ObjectifListView(OwnedMixin, QueryStringMixin, ListView):
    model = ObjectifApprentissage
    permission_required = 'objectifs.view_objectifapprentissage'
    template_name = 'objectifs/objectif_list.html'
    paginate_by = 9

    def get_queryset(self):
        qs = super().get_queryset().select_related('proprietaire', 'apprenant').prefetch_related('taches')
        q = self.request.GET.get('q', '').strip()
        return qs.filter(Q(titre__icontains=q) | Q(description__icontains=q)) if q else qs


class ObjectifDetailView(OwnedMixin, DetailView):
    model = ObjectifApprentissage
    permission_required = 'objectifs.view_objectifapprentissage'
    template_name = 'objectifs/objectif_detail.html'

    def get_context_data(self, **kwargs):
        from .statistiques import objectifs_visibles
        from .intelligence import calcul_charges
        ctx = super().get_context_data(**kwargs)
        ctx['charge'] = calcul_charges(objectifs_visibles(self.request.user))[self.object.pk]
        return ctx


class SaveMixin:
    template_name = 'objectifs/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Enregistrement effectué.')
        return super().form_valid(form)


class ObjectifCreateView(ManagerMixin, SaveMixin, CreateView):
    permission_required = 'objectifs.add_objectifapprentissage'
    form_class = ObjectifForm
    extra_context = {'page_label': 'Ajouter un objectif', 'retour': reverse_lazy('objectifs:objectif_list')}

    def form_valid(self, form):
        form.instance.proprietaire = self.request.user
        return super().form_valid(form)


class ObjectifUpdateView(ManagerMixin, OwnedMixin, SaveMixin, UpdateView):
    model = ObjectifApprentissage
    permission_required = 'objectifs.change_objectifapprentissage'
    form_class = ObjectifForm
    extra_context = {'page_label': 'Modifier un objectif', 'retour': reverse_lazy('objectifs:objectif_list')}


class DeleteMixin:
    template_name = 'objectifs/confirm_delete.html'

    def form_valid(self, form):
        messages.success(self.request, 'Suppression effectuée.')
        return super().form_valid(form)


class ObjectifDeleteView(ManagerMixin, OwnedMixin, DeleteMixin, DeleteView):
    model = ObjectifApprentissage
    permission_required = 'objectifs.delete_objectifapprentissage'
    success_url = reverse_lazy('objectifs:objectif_list')
    extra_context = {'is_objectif': True}


class TacheListView(OwnedMixin, QueryStringMixin, ListView):
    model = TacheApprentissage
    permission_required = 'objectifs.view_tacheapprentissage'
    template_name = 'objectifs/tache_list.html'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('objectif')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(description__icontains=q))
        statut = self.request.GET.get('statut', '')
        if statut in dict(TacheApprentissage.STATUTS):
            qs = qs.filter(statut=statut)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(statuts=TacheApprentissage.STATUTS, **kwargs)


class TacheDetailView(OwnedMixin, DetailView):
    model = TacheApprentissage
    permission_required = 'objectifs.view_tacheapprentissage'
    template_name = 'objectifs/tache_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['can_submit_work'] = self.object.objectif.apprenant_id == self.request.user.pk and self.request.user.has_perm('objectifs.update_statut_tacheapprentissage') and self.object.statut in ('a_faire', 'en_cours', 'a_reprendre')
        ctx['can_validate'] = is_manager(self.request.user) and self.request.user.has_perm('objectifs.change_tacheapprentissage') and self.object.statut == 'soumise'
        return ctx


class TacheFormMixin(SaveMixin):
    form_class = TacheForm

    def get_form_kwargs(self):
        return dict(super().get_form_kwargs(), user=self.request.user)


class TacheCreateView(ManagerMixin, TacheFormMixin, CreateView):
    permission_required = 'objectifs.add_tacheapprentissage'
    extra_context = {'page_label': 'Ajouter une tâche', 'retour': reverse_lazy('objectifs:tache_list')}

    def get_initial(self):
        qs = ObjectifApprentissage.objects.all()
        if not is_admin(self.request.user):
            qs = qs.filter(proprietaire=self.request.user)
        pk = self.request.GET.get('objectif', '')
        return {'objectif': pk} if pk.isdigit() and qs.filter(pk=pk).exists() else {}


class TacheUpdateView(ManagerMixin, OwnedMixin, TacheFormMixin, UpdateView):
    model = TacheApprentissage
    permission_required = 'objectifs.change_tacheapprentissage'
    extra_context = {'page_label': 'Modifier une tâche', 'retour': reverse_lazy('objectifs:tache_list')}


class TacheDeleteView(ManagerMixin, OwnedMixin, DeleteMixin, DeleteView):
    model = TacheApprentissage
    permission_required = 'objectifs.delete_tacheapprentissage'
    success_url = reverse_lazy('objectifs:tache_list')


class TacheTravailView(OwnedMixin, UpdateView):
    model = TacheApprentissage
    form_class = TacheTravailForm
    template_name = 'objectifs/travail_form.html'
    permission_required = 'objectifs.update_statut_tacheapprentissage'

    def get_queryset(self):
        return TacheApprentissage.objects.filter(objectif__apprenant=self.request.user, statut__in=['a_faire', 'en_cours', 'a_reprendre'])

    def form_valid(self, form):
        submitted = form.cleaned_data['action'] == 'soumettre'
        # Ne jamais accepter un statut transmis par le navigateur.
        changes = {'reponse': form.cleaned_data['reponse'], 'statut': 'soumise' if submitted else 'en_cours'}
        if submitted:
            changes['date_soumission'] = timezone.now()
        changed = self.get_queryset().filter(pk=self.object.pk).update(**changes)
        if not changed:
            raise Http404('Cette tâche ne peut plus être modifiée.')
        messages.success(self.request, 'Travail soumis au professeur.' if submitted else 'Brouillon enregistré.')
        return HttpResponseRedirect(self.object.get_absolute_url())


class TacheValidationView(ManagerMixin, OwnedMixin, SaveMixin, UpdateView):
    template_name = 'objectifs/validation_form.html'
    model = TacheApprentissage
    form_class = TacheValidationForm
    permission_required = 'objectifs.change_tacheapprentissage'
    extra_context = {'page_label': 'Valider une tâche soumise', 'retour': reverse_lazy('objectifs:tache_list')}

    def get_queryset(self):
        return super().get_queryset().filter(statut='soumise')
