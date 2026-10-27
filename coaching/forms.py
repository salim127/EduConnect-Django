from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.roles import LEARNER, TEACHER, is_admin
from config.forms import BootstrapFormMixin
from .access import managed_sessions
from .models import (
    BookingRequest, CoachAvailability, CoachAvailabilityException, CoachingAction,
    ConseilPedagogique, SessionCoaching,
)


class SessionCoachingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SessionCoaching
        fields = ['titre', 'date_session', 'duree', 'coach', 'etudiant', 'notes']
        widgets = {'date_session': forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M:%S', attrs={'type': 'datetime-local', 'step': '1'}
        ), 'notes': forms.Textarea(attrs={'rows': 5, 'maxlength': 6000})}

    def clean_notes(self):
        return self.cleaned_data.get('notes', '').strip()

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


class GeneratedAdviceReviewForm(BootstrapFormMixin, forms.Form):
    titre = forms.CharField(label='Titre du conseil', max_length=200)
    description = forms.CharField(
        label='Contenu à relire et modifier', max_length=6000,
        widget=forms.Textarea(attrs={'rows': 12, 'maxlength': 6000}),
    )
    type_conseil = forms.ChoiceField(label='Type de conseil', choices=ConseilPedagogique.TypeConseil.choices)

    def clean_titre(self):
        return self.cleaned_data['titre'].strip()

    def clean_description(self):
        return self.cleaned_data['description'].strip()


class SessionNotesForm(BootstrapFormMixin, forms.Form):
    notes = forms.CharField(
        label='Notes de séance', required=False, max_length=6000,
        widget=forms.Textarea(attrs={'rows': 5, 'maxlength': 6000}),
        help_text='Limite de 6 000 caractères. Évitez les données personnelles inutiles.',
    )

    def clean_notes(self):
        return self.cleaned_data.get('notes', '').strip()


class CoachAvailabilityForm(BootstrapFormMixin, forms.ModelForm):
    coach = forms.ModelChoiceField(label='Coach', queryset=get_user_model().objects.none(), required=False)
    class Meta:
        model = CoachAvailability
        fields = ['coach', 'weekday', 'start_time', 'end_time', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coach'].queryset = get_user_model().objects.filter(is_active=True, groups__name=TEACHER).distinct()
        if user is None or not is_admin(user):
            self.fields.pop('coach')


class AvailabilityExceptionForm(BootstrapFormMixin, forms.ModelForm):
    coach = forms.ModelChoiceField(label='Coach', queryset=get_user_model().objects.none(), required=False)
    class Meta:
        model = CoachAvailabilityException
        fields = ['coach', 'start_datetime', 'end_datetime', 'reason']
        widgets = {
            'start_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_datetime': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coach'].queryset = get_user_model().objects.filter(is_active=True, groups__name=TEACHER).distinct()
        if user is None or not is_admin(user):
            self.fields.pop('coach')

    def clean(self):
        cleaned = super().clean()
        for field in ('start_datetime', 'end_datetime'):
            value = cleaned.get(field)
            if value and timezone.is_naive(value):
                cleaned[field] = timezone.make_aware(value, timezone.get_current_timezone())
        return cleaned


class BookingSearchForm(BootstrapFormMixin, forms.Form):
    coach = forms.ModelChoiceField(label='Coach', queryset=get_user_model().objects.none())
    day = forms.DateField(label='Date', widget=forms.DateInput(attrs={'type': 'date'}))
    duration = forms.TypedChoiceField(
        label='Durée', choices=BookingRequest.DURATION_CHOICES, coerce=int, initial=60,
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coach'].queryset = get_user_model().objects.filter(
            is_active=True, groups__name='Enseignant / Coach'
        ).distinct().order_by('last_name', 'first_name', 'username')

    def clean_day(self):
        day = self.cleaned_data['day']
        if day < timezone.localdate():
            raise forms.ValidationError('Choisissez une date future ou la date du jour.')
        if day > timezone.localdate() + timedelta(days=90):
            raise forms.ValidationError('Les créneaux sont proposés sur les 90 prochains jours.')
        return day


class BookingRequestForm(BootstrapFormMixin, forms.Form):
    coach = forms.ModelChoiceField(label='Coach', queryset=get_user_model().objects.none(), widget=forms.HiddenInput)
    requested_start = forms.DateTimeField(widget=forms.HiddenInput)
    duration = forms.TypedChoiceField(choices=BookingRequest.DURATION_CHOICES, coerce=int, widget=forms.HiddenInput)
    topic = forms.CharField(label='Sujet de la séance', max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coach'].queryset = get_user_model().objects.filter(
            is_active=True, groups__name='Enseignant / Coach'
        ).distinct()

    def clean_topic(self):
        return self.cleaned_data['topic'].strip()


class CoachingActionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CoachingAction
        fields = ['title', 'description', 'action_type', 'priority', 'due_date', 'resource_url']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'due_date': forms.DateInput(attrs={'type': 'date'})}

    def clean_resource_url(self):
        value = self.cleaned_data.get('resource_url', '').strip()
        if value and not value.lower().startswith(('https://', 'http://')):
            raise forms.ValidationError('Le lien de ressource doit utiliser HTTP ou HTTPS.')
        return value


class CoachingActionUpdateForm(CoachingActionForm):
    class Meta(CoachingActionForm.Meta):
        fields = CoachingActionForm.Meta.fields + ['feedback']
        widgets = {**CoachingActionForm.Meta.widgets, 'feedback': forms.Textarea(attrs={'rows': 3})}


class CoachingActionProgressForm(BootstrapFormMixin, forms.Form):
    status = forms.ChoiceField(label='Mon avancement', choices=CoachingAction.Status.choices)
