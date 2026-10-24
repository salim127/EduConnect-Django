from django import forms
from django.contrib.auth import get_user_model

from accounts.roles import LEARNER, TEACHER, is_admin
from config.forms import BootstrapFormMixin
from .access import managed_sessions
from .models import ConseilPedagogique, SessionCoaching


class SessionCoachingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SessionCoaching
        fields = ['titre', 'date_session', 'duree', 'coach', 'etudiant']
        widgets = {'date_session': forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M:%S', attrs={'type': 'datetime-local', 'step': '1'}
        )}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        users = get_user_model().objects.filter(is_active=True)
        self.fields['etudiant'].queryset = users.filter(groups__name=LEARNER).distinct().order_by('username')
        self.fields['coach'].queryset = users.filter(groups__name=TEACHER).distinct().order_by('username')
        self.fields['date_session'].help_text = 'Heure locale de Tunis.'
        if not is_admin(user):
            self.instance.coach = user
            self.initial['coach'] = user.pk
            self.fields['coach'].disabled = True
            self.fields['coach'].queryset = self.fields['coach'].queryset.filter(pk=user.pk)
            self.fields['coach'].help_text = 'Vous êtes le coach de cette séance.'

    def clean_coach(self):
        # Le champ désactivé est une aide visuelle ; l'autorité reste le serveur.
        return self.instance.coach if not is_admin(self._user) else self.cleaned_data['coach']


class ConseilPedagogiqueForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ConseilPedagogique
        fields = ['titre', 'description', 'type_conseil', 'session']
        widgets = {'description': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['session'].queryset = managed_sessions(user, SessionCoaching.objects.all())
