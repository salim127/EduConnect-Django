from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator
from django.urls import reverse


class ObjectifApprentissage(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    proprietaire = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Créateur', on_delete=models.CASCADE, related_name='objectifs')
    apprenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='objectifs_attribues', null=True, blank=True, verbose_name='Apprenant')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateField('Échéance', null=True, blank=True)
    niveau = models.CharField(max_length=15, choices=[('debutant', 'Débutant'), ('intermediaire', 'Intermédiaire'), ('avance', 'Avancé')], default='debutant')
    critere_reussite = models.TextField('Critère de réussite', blank=True, default='')
    priorite = models.CharField('Priorité', max_length=10, choices=[('basse', 'Basse'), ('normale', 'Normale'), ('haute', 'Haute')], default='normale')

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "objectif d’apprentissage"
        verbose_name_plural = "objectifs d’apprentissage"

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('objectifs:objectif_detail', args=[self.pk])

    @property
    def progression(self):
        taches = list(self.taches.all())
        return round(100 * sum(t.statut == 'validee' for t in taches) / len(taches)) if taches else 0


class TacheApprentissage(models.Model):
    STATUTS = [('a_faire', 'À faire'), ('en_cours', 'En cours'), ('soumise', 'Soumise'), ('validee', 'Validée'), ('a_reprendre', 'À reprendre')]
    objectif = models.ForeignKey(ObjectifApprentissage, on_delete=models.CASCADE, related_name='taches')
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    reponse = models.TextField('Mon travail', blank=True, default='')
    date_soumission = models.DateTimeField('Date de soumission', null=True, blank=True)
    duree_estimee = models.PositiveIntegerField('Durée estimée (minutes)', null=True, blank=True, validators=[MinValueValidator(1)])
    statut = models.CharField(max_length=15, choices=STATUTS, default='a_faire')
    date_echeance = models.DateField('Échéance', null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        permissions = [("update_statut_tacheapprentissage", "Rédiger et soumettre son travail")]
        verbose_name = "tâche d’apprentissage"
        verbose_name_plural = "tâches d’apprentissage"

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('objectifs:tache_detail', args=[self.pk])

    def clean(self):
        if self.objectif_id and self.date_echeance and self.objectif.date_echeance and self.date_echeance > self.objectif.date_echeance:
            raise ValidationError({'date_echeance': "La tâche doit se terminer au plus tard à l’échéance de l’objectif."})
