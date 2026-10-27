"""Fondation métier du coaching.

Comme les autres modèles du projet, utiliser full_clean() avant save() hors
ModelForm/admin. save(), update() et bulk_create() ne valident pas le métier.
Les contrôles de chevauchement ne constituent pas un verrou : deux écritures
concurrentes peuvent passer la validation sous SQLite. Une future réservation
concurrente devra sérialiser les écritures et revérifier les disponibilités.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.roles import LEARNER, TEACHER


class SessionCoaching(models.Model):
    class Statut(models.TextChoices):
        PLANIFIEE = 'planifiee', 'Planifiée'
        TERMINEE = 'terminee', 'Terminée'
        ANNULEE = 'annulee', 'Annulée'

    titre = models.CharField('Titre', max_length=200)
    notes = models.TextField('Notes de séance', blank=True, validators=[MaxLengthValidator(6000)])
    date_session = models.DateTimeField('Date de la séance')
    duree = models.PositiveIntegerField('Durée (minutes)', validators=[MinValueValidator(1)])
    statut = models.CharField('Statut', max_length=10, choices=Statut.choices, default=Statut.PLANIFIEE)
    coach = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Coach', on_delete=models.PROTECT, related_name='sessions_coachees')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Apprenant', on_delete=models.PROTECT, related_name='sessions_coaching')

    class Meta:
        verbose_name = 'séance de coaching'
        verbose_name_plural = 'séances de coaching'
        ordering = ['date_session', 'pk']
        constraints = [models.CheckConstraint(condition=models.Q(duree__gt=0), name='coaching_duree_positive')]

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('coaching:session_detail', args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}
        if not (self.titre or '').strip():
            errors['titre'] = 'Saisissez un titre non vide.'
        if self.coach_id and self.coach_id == self.etudiant_id:
            errors['etudiant'] = 'Le coach et l’apprenant doivent être différents.'
        for field, role in [('coach', TEACHER), ('etudiant', LEARNER)]:
            user_id = getattr(self, f'{field}_id')
            if user_id:
                participant = get_user_model().objects.filter(pk=user_id).first()
                if participant is None:
                    errors[field] = 'Utilisateur introuvable.'
                elif not participant.is_active:
                    errors[field] = 'Le participant doit être actif.'
                elif not participant.groups.filter(name=role).exists():
                    errors[field] = f'Le participant doit appartenir au groupe « {role} ».'

        # full_clean appelle clean même lorsqu’un champ est déjà invalide.
        valid_date = isinstance(self.date_session, datetime)
        if valid_date and timezone.is_naive(self.date_session):
            errors['date_session'] = 'La date doit inclure un fuseau horaire.'
            valid_date = False
        valid_duration = isinstance(self.duree, int) and self.duree > 0
        if not valid_duration:
            errors['duree'] = 'La durée doit être strictement positive.'
        if valid_date and valid_duration:
            try:
                end = self.date_session + timedelta(minutes=self.duree)
            except OverflowError:
                errors['duree'] = 'La durée dépasse la plage de dates autorisée.'
            else:
                now = timezone.now()
                previous = type(self).objects.filter(pk=self.pk).first() if not self._state.adding else None
                schedule = ('date_session', 'duree', 'coach_id', 'etudiant_id')
                changed = previous and any(getattr(previous, f) != getattr(self, f) for f in schedule)
                if previous and previous.date_session <= now and changed:
                    errors['date_session'] = 'Les participants et le créneau d’une séance passée ne sont plus modifiables.'
                if self.statut == self.Statut.PLANIFIEE and self.date_session <= now:
                    if not previous or changed or previous.statut != self.Statut.PLANIFIEE:
                        errors['date_session'] = 'Une nouvelle planification doit être dans le futur.'
                if self.statut == self.Statut.TERMINEE and end > now:
                    errors['statut'] = 'La séance ne peut être terminée avant la fin de son créneau.'
                if self.statut != self.Statut.ANNULEE and self.coach_id and self.etudiant_id:
                    participants = [self.coach_id, self.etudiant_id]
                    candidates = type(self).objects.filter(
                        models.Q(coach_id__in=participants) | models.Q(etudiant_id__in=participants),
                        date_session__lt=end,
                    ).exclude(statut=self.Statut.ANNULEE)
                    if not self._state.adding:
                        candidates = candidates.exclude(pk=self.pk)
                    for other in candidates.only('date_session', 'duree'):
                        if other.date_session + timedelta(minutes=other.duree) > self.date_session:
                            errors['date_session'] = 'Un participant possède déjà une séance sur ce créneau.'
                            break
        if errors:
            raise ValidationError(errors)


class ConseilPedagogique(models.Model):
    class TypeConseil(models.TextChoices):
        ORGANISATION = 'organisation', 'Organisation'
        MEMORISATION = 'memorisation', 'Mémorisation'
        METHODE = 'methode', 'Méthode'
        BIEN_ETRE = 'bien_etre', 'Bien-être'

    titre = models.CharField('Titre', max_length=200)
    description = models.TextField('Description')
    date_creation = models.DateTimeField('Date de création', auto_now_add=True)
    type_conseil = models.CharField('Type de conseil', max_length=20, choices=TypeConseil.choices)
    session = models.ForeignKey(SessionCoaching, verbose_name='Séance', on_delete=models.CASCADE, related_name='conseils')

    class Meta:
        verbose_name = 'conseil pédagogique'
        verbose_name_plural = 'conseils pédagogiques'
        ordering = ['-date_creation', '-pk']

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('coaching:conseil_detail', args=[self.pk])

    def clean(self):
        super().clean()
        errors = {field: 'Saisissez un contenu non vide.' for field in ('titre', 'description') if not (getattr(self, field) or '').strip()}
        if errors:
            raise ValidationError(errors)


WEEKDAYS = [
    (0, 'Lundi'), (1, 'Mardi'), (2, 'Mercredi'), (3, 'Jeudi'),
    (4, 'Vendredi'), (5, 'Samedi'), (6, 'Dimanche'),
]


def _validate_coach(coach_id, errors, field='coach'):
    if not coach_id:
        return
    coach = get_user_model().objects.filter(pk=coach_id).first()
    if coach is None or not coach.is_active or not coach.groups.filter(name=TEACHER).exists():
        errors[field] = 'Le coach doit être un compte actif du groupe Enseignant / Coach.'


class CoachAvailability(models.Model):
    coach = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coaching_availabilities')
    weekday = models.PositiveSmallIntegerField('Jour', choices=WEEKDAYS)
    start_time = models.TimeField('Début')
    end_time = models.TimeField('Fin')
    is_active = models.BooleanField('Active', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['weekday', 'start_time', 'pk']
        constraints = [models.UniqueConstraint(
            fields=['coach', 'weekday', 'start_time', 'end_time'], name='coaching_availability_unique_window'
        )]
        permissions = [('manage_coachavailability', 'Peut gérer les disponibilités de coaching')]

    def __str__(self):
        return f'{self.coach} · {self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}'

    def clean(self):
        super().clean()
        errors = {}
        _validate_coach(self.coach_id, errors)
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            errors['end_time'] = 'La fin doit être postérieure au début; les plages de nuit ne sont pas prises en charge.'
        if self.is_active and self.coach_id and self.weekday is not None and self.start_time and self.end_time:
            overlaps = type(self).objects.filter(
                coach_id=self.coach_id, weekday=self.weekday, is_active=True,
                start_time__lt=self.end_time, end_time__gt=self.start_time,
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            if overlaps.exists():
                errors['start_time'] = 'Cette plage chevauche une autre disponibilité active.'
        if errors:
            raise ValidationError(errors)


class CoachAvailabilityException(models.Model):
    coach = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coaching_availability_exceptions')
    start_datetime = models.DateTimeField('Début de l’indisponibilité')
    end_datetime = models.DateTimeField('Fin de l’indisponibilité')
    reason = models.CharField('Motif (facultatif)', max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_datetime', 'pk']

    def clean(self):
        super().clean()
        errors = {}
        _validate_coach(self.coach_id, errors)
        if self.start_datetime and self.end_datetime:
            if timezone.is_naive(self.start_datetime) or timezone.is_naive(self.end_datetime):
                errors['start_datetime'] = 'Les dates doivent inclure un fuseau horaire.'
            elif self.start_datetime >= self.end_datetime:
                errors['end_datetime'] = 'La fin doit être postérieure au début.'
        if errors:
            raise ValidationError(errors)


class BookingRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        APPROVED = 'approved', 'Approuvée'
        REJECTED = 'rejected', 'Refusée'
        CANCELLED = 'cancelled', 'Annulée'

    DURATION_CHOICES = [(30, '30 minutes'), (45, '45 minutes'), (60, '60 minutes'), (90, '90 minutes')]

    coach = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='coaching_booking_requests_received')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='coaching_booking_requests')
    requested_start = models.DateTimeField('Créneau demandé')
    duration = models.PositiveSmallIntegerField('Durée', choices=DURATION_CHOICES)
    topic = models.CharField('Sujet', max_length=200)
    status = models.CharField('État de la demande', max_length=10, choices=Status.choices, default=Status.PENDING)
    session = models.OneToOneField(SessionCoaching, null=True, blank=True, on_delete=models.PROTECT, related_name='booking_request')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['requested_start', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['coach', 'requested_start'], condition=models.Q(status='pending'),
                name='coaching_one_pending_request_per_start',
            ),
            models.CheckConstraint(
                condition=(models.Q(status='approved', session__isnull=False) | (~models.Q(status='approved') & models.Q(session__isnull=True))),
                name='coaching_booking_approved_has_session',
            ),
        ]

    def get_absolute_url(self):
        return reverse('coaching:booking_detail', args=[self.pk])

    def clean(self):
        super().clean()
        errors = {}
        _validate_coach(self.coach_id, errors)
        if self.etudiant_id:
            learner = get_user_model().objects.filter(pk=self.etudiant_id).first()
            if learner is None or not learner.is_active or not learner.groups.filter(name=LEARNER).exists():
                errors['etudiant'] = 'L’apprenant doit être un compte actif du groupe Apprenant.'
        if self.coach_id and self.coach_id == self.etudiant_id:
            errors['etudiant'] = 'Le coach et l’apprenant doivent être différents.'
        if self.requested_start and timezone.is_naive(self.requested_start):
            errors['requested_start'] = 'Le créneau doit inclure un fuseau horaire.'
        elif self.requested_start and self.status == self.Status.PENDING and self.requested_start <= timezone.now():
            errors['requested_start'] = 'Une demande doit porter sur un créneau futur.'
        if self.status == self.Status.APPROVED and not self.session_id:
            errors['session'] = 'Une demande approuvée doit être liée à sa séance confirmée.'
        if self.status != self.Status.APPROVED and self.session_id:
            errors['session'] = 'Seule une demande approuvée peut être liée à une séance.'
        if self.session_id and self.coach_id and self.etudiant_id:
            session = self.session
            if (session.coach_id, session.etudiant_id, session.date_session, session.duree) != (
                self.coach_id, self.etudiant_id, self.requested_start, self.duration
            ):
                errors['session'] = 'La séance confirmée doit correspondre à la demande.'
        if errors:
            raise ValidationError(errors)


class CoachingAction(models.Model):
    class ActionType(models.TextChoices):
        EXERCISE = 'exercise', 'Exercice'
        RESOURCE = 'resource', 'Ressource'
        REVISION = 'revision', 'Révision'
        PROJECT = 'project', 'Projet'
        OTHER = 'other', 'Autre'

    class Priority(models.TextChoices):
        LOW = 'low', 'Basse'
        MEDIUM = 'medium', 'Moyenne'
        HIGH = 'high', 'Haute'

    class Status(models.TextChoices):
        TODO = 'todo', 'À faire'
        IN_PROGRESS = 'in_progress', 'En cours'
        COMPLETED = 'completed', 'Terminée'

    session = models.ForeignKey(SessionCoaching, on_delete=models.CASCADE, related_name='actions')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='coaching_actions')
    title = models.CharField('Titre', max_length=160)
    description = models.TextField('Consigne', max_length=2000)
    action_type = models.CharField('Type', max_length=12, choices=ActionType.choices, default=ActionType.OTHER)
    priority = models.CharField('Priorité', max_length=6, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField('Échéance', null=True, blank=True)
    resource_url = models.URLField('Lien de ressource', max_length=500, blank=True)
    feedback = models.TextField('Retour du coach', max_length=2000, blank=True)
    status = models.CharField('Avancement', max_length=12, choices=Status.choices, default=Status.TODO)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', '-priority', '-created_at', 'pk']
        permissions = [('view_own_coachingaction', 'Peut voir ses propres actions pédagogiques')]

    def clean(self):
        super().clean()
        errors = {}
        if self.session_id and self.etudiant_id and self.session.etudiant_id != self.etudiant_id:
            errors['etudiant'] = 'L’action doit appartenir à l’apprenant de la séance.'
        if self.due_date and self._state.adding and self.due_date < timezone.localdate():
            errors['due_date'] = 'L’échéance doit être aujourd’hui ou ultérieure.'
        if self.status == self.Status.COMPLETED and not self.completed_at:
            errors['completed_at'] = 'Une action terminée doit avoir une date de réalisation.'
        if self.status != self.Status.COMPLETED and self.completed_at:
            errors['completed_at'] = 'Seule une action terminée peut avoir une date de réalisation.'
        if errors:
            raise ValidationError(errors)
