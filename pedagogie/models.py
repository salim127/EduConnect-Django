from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from uuid import uuid4
from pathlib import Path


def support_path(instance, filename):
    return f'cours/{instance.cours_id}/{uuid4().hex}{Path(filename).suffix.lower()}'


class Cours(models.Model):
    NIVEAUX = [('debutant', 'Débutant'), ('intermediaire', 'Intermédiaire'), ('avance', 'Avancé')]

    titre = models.CharField(max_length=200)
    description = models.TextField('Description courte')
    matiere = models.CharField('Matière', max_length=100)
    niveau = models.CharField(max_length=20, choices=NIVEAUX, default='debutant')
    contenu = models.TextField('Contenu du cours')
    chapitres = models.JSONField(default=list, blank=True)
    masque = models.BooleanField('Masquer ce cours aux étudiants', default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    enseignant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cours')

    class Meta:
        ordering = ['-date_creation']
        verbose_name_plural = 'cours'

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('pedagogie:cours_detail', args=[self.pk])


class Exercice(models.Model):
    TYPES = [('qcm', 'QCM'), ('vf', 'Vrai / Faux'), ('ouverte', 'Question ouverte')]
    DIFFICULTES = [('facile', 'Facile'), ('moyen', 'Moyen'), ('difficile', 'Difficile')]

    titre = models.CharField(max_length=200)
    question = models.TextField()
    type_exercice = models.CharField('Type', max_length=10, choices=TYPES, default='qcm')
    difficulte = models.CharField('Difficulté', max_length=10, choices=DIFFICULTES, default='facile')
    propositions = models.TextField('Propositions (QCM)', blank=True, help_text='Une proposition par ligne.')
    bonne_reponse = models.TextField('Bonne réponse')
    explication = models.TextField('Explication de la réponse', blank=True)
    bareme = models.TextField('Barème de correction', blank=True)
    ai_generation_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    questions_supplementaires = models.JSONField(default=list, blank=True)
    chapitre_id = models.CharField('Chapitre', max_length=36, blank=True)
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='exercices')

    class Meta:
        ordering = ['cours__titre', 'titre']

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('pedagogie:exercice_detail', args=[self.pk])

    @property
    def enseignant(self):
        return self.cours.enseignant

    @property
    def liste_propositions(self):
        return [p.strip() for p in self.propositions.splitlines() if p.strip()]

    @property
    def chapitre_titre(self):
        return next((c['titre'] for c in self.cours.chapitres if c.get('id') == self.chapitre_id), '')

    def clean(self):
        rep = (self.bonne_reponse or '').strip()
        if self.type_exercice == 'qcm':
            props = self.liste_propositions
            if len(props) < 2:
                raise ValidationError({'propositions': 'Un QCM nécessite au moins deux propositions.'})
            match = next((p for p in props if p.lower() == rep.lower()), None)
            if match is None:
                raise ValidationError({'bonne_reponse': 'La bonne réponse doit correspondre à une proposition.'})
            self.propositions, rep = '\n'.join(props), match
        elif self.type_exercice == 'vf':
            if rep.lower() not in ('vrai', 'faux'):
                raise ValidationError({'bonne_reponse': 'Saisissez « Vrai » ou « Faux ».'})
            self.propositions, rep = '', rep.capitalize()
        else:
            self.propositions = ''
        self.bonne_reponse = rep


class SupportCours(models.Model):
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='supports')
    chapitre_id = models.CharField('Chapitre', max_length=36, blank=True, db_index=True)
    fichier = models.FileField(upload_to=support_path)
    nom = models.CharField(max_length=255)
    masque = models.BooleanField('Masquer ce document aux étudiants', default=False)

    class Meta:
        ordering = ['pk']


class TentativeExercice(models.Model):
    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tentatives_exercices')
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE, related_name='tentatives')
    revision = models.CharField(max_length=64)
    reponses = models.JSONField(default=list)
    resultats = models.JSONField(default=list)
    corrections = models.JSONField(default=dict, blank=True)
    numero = models.PositiveIntegerField(default=1)
    enonce = models.JSONField(default=dict, blank=True)
    note = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    points_obtenus = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    points_possibles = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    commentaire_prof = models.TextField(blank=True)
    validee_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='notes_validees')
    date_validation = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['eleve', 'exercice', 'numero'], name='unique_numero_tentative'),
            models.CheckConstraint(condition=models.Q(note__isnull=True) | models.Q(note__gte=0, note__lte=20), name='note_sur_vingt'),
        ]


class ParticipationExercice(models.Model):
    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE)
    tentatives_autorisees = models.PositiveIntegerField(default=1)
    tentatives_utilisees = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['eleve', 'exercice'], name='unique_participation_exercice')]


class EntrainementChapitre(models.Model):
    eleve = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE)
    chapitre_id = models.CharField(max_length=36)
    revision = models.CharField(max_length=64)
    questions = models.JSONField(default=list)
    reponses = models.JSONField(default=list, blank=True)
    resultats = models.JSONField(default=list, blank=True)
    contenu_tronque = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation', '-pk']
