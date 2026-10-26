from django import forms
from config.forms import BootstrapFormMixin
from .models import Categorie, Ressource


class CategorieForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ['nom', 'icone', 'couleur']
        labels = {
            'nom': 'Nom de la catégorie',
            'icone': 'Icône',
            'couleur': 'Couleur',
        }


class RessourceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Ressource
        fields = ['titre', 'categorie', 'type_ressource', 'info', 'url']
        labels = {
            'titre': 'Titre de la ressource',
            'categorie': 'Catégorie',
            'type_ressource': 'Type',
            'info': 'Information complémentaire',
            'url': 'Lien / URL',
        }
