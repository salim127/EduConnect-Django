from django import forms
from django.contrib.auth import get_user_model
from accounts.roles import LEARNER
from accounts.roles import is_admin
from config.forms import BootstrapFormMixin
from .models import ObjectifApprentissage, TacheApprentissage


class ObjectifForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ObjectifApprentissage
        fields = ['titre', 'description', 'apprenant', 'niveau', 'critere_reussite', 'priorite', 'date_echeance']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'date_echeance': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['critere_reussite'].required = True
        self.fields['critere_reussite'].widget = forms.Textarea(attrs={'rows': 3, 'placeholder': 'Exemple : réussir au moins 8 questions sur 10.'})
        self.fields['apprenant'].required = True
        self.fields['apprenant'].queryset = get_user_model().objects.filter(is_active=True, groups__name=LEARNER).distinct().order_by('last_name', 'first_name', 'username')
        self.fields['apprenant'].label_from_instance = lambda user: f'{user.get_full_name() or user.username} ({user.username})'
        self.fields['apprenant'].help_text = 'Choisissez l’apprenant auquel cet objectif est adapté.'

    def clean_date_echeance(self):
        date = self.cleaned_data['date_echeance']
        if self.instance.pk and date and self.instance.taches.filter(date_echeance__gt=date).exists():
            raise forms.ValidationError("Certaines tâches ont une échéance postérieure à cette date. Modifiez d’abord leurs échéances.")
        return date


class TacheForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TacheApprentissage
        fields = ['objectif', 'titre', 'description', 'duree_estimee', 'date_echeance']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'date_echeance': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['objectif'].queryset = ObjectifApprentissage.objects.all() if is_admin(user) else ObjectifApprentissage.objects.filter(proprietaire=user)


class TacheTravailForm(BootstrapFormMixin, forms.ModelForm):
    action = forms.ChoiceField(choices=[('brouillon', 'Enregistrer le brouillon'), ('soumettre', 'Soumettre mon travail')], widget=forms.HiddenInput)

    class Meta:
        model = TacheApprentissage
        fields = ['reponse']
        widgets = {'reponse': forms.Textarea(attrs={'rows': 12, 'placeholder': 'Rédigez votre réponse ou collez votre code ici.'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reponse'].required = True
        self.fields['reponse'].help_text = 'Le brouillon reste modifiable. Après soumission, votre réponse attend la décision du professeur.'

    def clean_reponse(self):
        value = self.cleaned_data['reponse'].strip()
        if not value:
            raise forms.ValidationError('Rédigez votre réponse avant de l’enregistrer ou de la soumettre.')
        return value


class TacheValidationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TacheApprentissage
        fields = ['statut']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['statut'].label = 'Décision du professeur'
        self.fields['statut'].choices = [('validee', 'Valider la tâche'), ('a_reprendre', 'Demander une reprise')]
