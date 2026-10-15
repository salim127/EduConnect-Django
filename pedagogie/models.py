from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class Cours(models.Model):
    NIVEAUX = [('debutant', 'Débutant'), ('intermediaire', 'Intermédiaire'), ('avance', 'Avancé')]

    titre = models.CharField(max_length=200)
    description = models.TextField('Description courte')
    matiere = models.CharField('Matière', max_length=100)
    niveau = models.CharField(max_length=20, choices=NIVEAUX, default='debutant')
    contenu = models.TextField('Contenu du cours')
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
