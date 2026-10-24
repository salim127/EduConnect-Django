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
from django.core.validators import MinValueValidator
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
