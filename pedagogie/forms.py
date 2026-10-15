from django import forms

from accounts.roles import is_admin
from config.forms import BootstrapFormMixin

from .models import Cours, Exercice


class CoursForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Cours
        fields = ('titre', 'description', 'matiere', 'niveau', 'contenu')
        widgets = {'description': forms.Textarea(attrs={'rows': 3}), 'contenu': forms.Textarea(attrs={'rows': 10})}


class ExerciceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Exercice
        fields = ('titre', 'cours', 'type_exercice', 'difficulte', 'question', 'propositions', 'bonne_reponse')
        widgets = {
            'question': forms.Textarea(attrs={'rows': 3}),
            'propositions': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Choix A\nChoix B\nChoix C'}),
            'bonne_reponse': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Cours.objects.all() if is_admin(user) else Cours.objects.filter(enseignant=user)
        self.fields['cours'].queryset = qs
