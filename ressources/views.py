from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)

from config.mixins import QueryStringMixin
from .ai import invalider_fiche
from .forms import CategorieForm, RessourceForm
from .models import Categorie, Ressource


# ─────────────────────────────────────────────────────────────────────────────
# Catégories
# ─────────────────────────────────────────────────────────────────────────────

class CategoriesView(PermissionRequiredMixin, QueryStringMixin, ListView):
    model = Categorie
    template_name = 'ressources/categories.html'
    context_object_name = 'categories'
    permission_required = 'ressources.view_categorie'

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nom__icontains=q)
        return qs


class CategorieCreateView(PermissionRequiredMixin, CreateView):
    model = Categorie
    form_class = CategorieForm
    template_name = 'ressources/categorie_form.html'
    permission_required = 'ressources.add_categorie'
    success_url = reverse_lazy('ressources:categories')

    def form_valid(self, form):
        messages.success(self.request, 'Catégorie ajoutée avec succès.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titre_page'] = 'Ajouter une catégorie'
        return ctx


class CategorieUpdateView(PermissionRequiredMixin, UpdateView):
    model = Categorie
    form_class = CategorieForm
    template_name = 'ressources/categorie_form.html'
    permission_required = 'ressources.change_categorie'
    success_url = reverse_lazy('ressources:categories')

    def form_valid(self, form):
        messages.success(self.request, 'Catégorie mise à jour.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titre_page'] = 'Modifier la catégorie'
        return ctx


class CategorieDeleteView(PermissionRequiredMixin, DeleteView):
    model = Categorie
    permission_required = 'ressources.delete_categorie'
    success_url = reverse_lazy('ressources:categories')
    http_method_names = ['post']

    def form_valid(self, form):
        messages.success(self.request, 'Catégorie supprimée.')
        return super().form_valid(form)


# ─────────────────────────────────────────────────────────────────────────────
# Bibliothèque (Ressources)
# ─────────────────────────────────────────────────────────────────────────────

class BibliothequeView(PermissionRequiredMixin, QueryStringMixin, ListView):
    model = Ressource
    template_name = 'ressources/bibliotheque.html'
    context_object_name = 'ressources'
    permission_required = 'ressources.view_ressource'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().select_related('categorie')
        q = self.request.GET.get('q', '').strip()
        t = self.request.GET.get('type', '').strip()
        cat = self.request.GET.get('categorie', '').strip()
        if q:
            qs = qs.filter(Q(titre__icontains=q) | Q(info__icontains=q))
        if t:
            qs = qs.filter(type_ressource=t)
        if cat:
            qs = qs.filter(categorie__id=cat)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = Categorie.objects.all()
        ctx['type_actif'] = self.request.GET.get('type', '')
        ctx['cat_actif'] = self.request.GET.get('categorie', '')
        return ctx


class RessourceDetailView(PermissionRequiredMixin, DetailView):
    model = Ressource
    template_name = 'ressources/ressource_detail.html'
    permission_required = 'ressources.view_ressource'


class RessourceCreateView(PermissionRequiredMixin, CreateView):
    model = Ressource
    form_class = RessourceForm
    template_name = 'ressources/ressource_form.html'
    permission_required = 'ressources.add_ressource'

    def form_valid(self, form):
        messages.success(self.request, 'Ressource ajoutée avec succès.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titre_page'] = 'Ajouter une ressource'
        return ctx


class RessourceUpdateView(PermissionRequiredMixin, UpdateView):
    model = Ressource
    form_class = RessourceForm
    template_name = 'ressources/ressource_form.html'
    permission_required = 'ressources.change_ressource'

    def form_valid(self, form):
        invalider_fiche(self.object.pk)
        messages.success(self.request, 'Ressource mise à jour.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titre_page'] = 'Modifier la ressource'
        return ctx


class RessourceDeleteView(PermissionRequiredMixin, DeleteView):
    model = Ressource
    permission_required = 'ressources.delete_ressource'
    success_url = reverse_lazy('ressources:bibliotheque')
    http_method_names = ['post']

    def form_valid(self, form):
        invalider_fiche(self.object.pk)
        messages.success(self.request, 'Ressource supprimée.')
        return super().form_valid(form)
