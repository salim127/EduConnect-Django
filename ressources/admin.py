from django.contrib import admin
from .models import Categorie, Ressource


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('nom', 'icone', 'couleur', 'nb_ressources')
    search_fields = ('nom',)


@admin.register(Ressource)
class RessourceAdmin(admin.ModelAdmin):
    list_display = ('titre', 'categorie', 'type_ressource', 'info', 'date_ajout')
    list_filter = ('categorie', 'type_ressource')
    search_fields = ('titre', 'info')
