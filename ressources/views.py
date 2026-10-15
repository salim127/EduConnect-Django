from django.views.generic import TemplateView

from . import demo


class BibliothequeView(TemplateView):
    template_name = 'ressources/bibliotheque.html'
    extra_context = {'ressources': demo.RESSOURCES}


class CategoriesView(TemplateView):
    template_name = 'ressources/categories.html'
    extra_context = {'categories': demo.CATEGORIES}
