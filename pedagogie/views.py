from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.roles import is_admin
from config.mixins import QueryStringMixin

from .forms import CoursForm, ExerciceForm
from .models import Cours, Exercice


class OwnerOrAdminMixin:
    """Modifier/supprimer : seulement le propriétaire (enseignant du cours) ou un administrateur."""

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not is_admin(self.request.user) and obj.enseignant != self.request.user:
            raise PermissionDenied
        return obj


class DeleteMessageMixin:
    http_method_names = ['post']

    def form_valid(self, form):
        messages.success(self.request, 'Suppression effectuée.')
        return super().form_valid(form)


# ---------- Cours ----------
class CoursListView(PermissionRequiredMixin, QueryStringMixin, ListView):
    permission_required = 'pedagogie.view_cours'
    template_name = 'pedagogie/cours_list.html'
    paginate_by = 9

    def get_queryset(self):
        qs = Cours.objects.select_related('enseignant')
        g = self.request.GET
        if q := g.get('q', '').strip():
            qs = qs.filter(Q(titre__icontains=q) | Q(description__icontains=q) | Q(matiere__icontains=q))
        if g.get('matiere'):
            qs = qs.filter(matiere=g['matiere'])
        if g.get('niveau'):
            qs = qs.filter(niveau=g['niveau'])
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx['matieres'] = Cours.objects.order_by('matiere').values_list('matiere', flat=True).distinct()
        ctx['niveaux'] = Cours.NIVEAUX
        return ctx


class CoursDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'pedagogie.view_cours'
    model = Cours
    template_name = 'pedagogie/cours_detail.html'


class CoursCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'pedagogie.add_cours'
    form_class = CoursForm
    template_name = 'pedagogie/cours_form.html'

    def form_valid(self, form):
        form.instance.enseignant = self.request.user
        messages.success(self.request, 'Cours créé.')
        return super().form_valid(form)


class CoursUpdateView(PermissionRequiredMixin, OwnerOrAdminMixin, UpdateView):
    permission_required = 'pedagogie.change_cours'
    model = Cours
    form_class = CoursForm
    template_name = 'pedagogie/cours_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Cours modifié.')
        return super().form_valid(form)


class CoursDeleteView(PermissionRequiredMixin, OwnerOrAdminMixin, DeleteMessageMixin, DeleteView):
    permission_required = 'pedagogie.delete_cours'
    model = Cours
    success_url = reverse_lazy('pedagogie:cours_list')


# ---------- Exercices ----------
class ExerciceListView(PermissionRequiredMixin, QueryStringMixin, ListView):
    permission_required = 'pedagogie.view_exercice'
    template_name = 'pedagogie/exercice_list.html'
    paginate_by = 10

    def get_queryset(self):
        qs = Exercice.objects.select_related('cours')
        g = self.request.GET
        if q := g.get('q', '').strip():
            qs = qs.filter(Q(titre__icontains=q) | Q(question__icontains=q))
        for field in ('type_exercice', 'difficulte'):
            if g.get(field):
                qs = qs.filter(**{field: g[field]})
        if g.get('cours', '').isdigit():
            qs = qs.filter(cours_id=g['cours'])
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx.update(types=Exercice.TYPES, difficultes=Exercice.DIFFICULTES, cours_all=Cours.objects.order_by('titre'))
        return ctx


class ExerciceDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'pedagogie.view_exercice'
    model = Exercice
    queryset = Exercice.objects.select_related('cours__enseignant')
    template_name = 'pedagogie/exercice_detail.html'

    def post(self, request, *args, **kwargs):
        """Vérification simple (rien n'est enregistré) : compare la réponse à la bonne réponse."""
        self.object = self.get_object()
        donnee = request.POST.get('reponse', '').strip()
        ctx = self.get_context_data(object=self.object)
        if donnee:
            ctx.update(reponse_donnee=donnee, resultat_juste=donnee.lower() == self.object.bonne_reponse.strip().lower())
        else:
            ctx['erreur_reponse'] = 'Choisissez ou saisissez une réponse avant de vérifier.'
        return self.render_to_response(ctx)


class ExerciceFormMixin:
    form_class = ExerciceForm
    template_name = 'pedagogie/exercice_form.html'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['user'] = self.request.user
        return kw


class ExerciceCreateView(PermissionRequiredMixin, ExerciceFormMixin, CreateView):
    permission_required = 'pedagogie.add_exercice'

    def get_initial(self):
        cid = self.request.GET.get('cours', '')
        return {'cours': cid} if cid.isdigit() else {}

    def form_valid(self, form):
        messages.success(self.request, 'Exercice créé.')
        return super().form_valid(form)


class ExerciceUpdateView(PermissionRequiredMixin, OwnerOrAdminMixin, ExerciceFormMixin, UpdateView):
    permission_required = 'pedagogie.change_exercice'
    model = Exercice

    def form_valid(self, form):
        messages.success(self.request, 'Exercice modifié.')
        return super().form_valid(form)


class ExerciceDeleteView(PermissionRequiredMixin, OwnerOrAdminMixin, DeleteMessageMixin, DeleteView):
    permission_required = 'pedagogie.delete_exercice'
    model = Exercice
    success_url = reverse_lazy('pedagogie:exercice_list')
