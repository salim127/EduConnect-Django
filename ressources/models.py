from django.db import models
from django.urls import reverse


COULEURS = [
    ('primary', 'Bleu (primary)'),
    ('teal', 'Vert (teal)'),
    ('amber', 'Jaune (amber)'),
]

ICONES = [
    ('bi-code-slash', 'Programmation'),
    ('bi-calculator', 'Mathématiques'),
    ('bi-translate', 'Langues'),
    ('bi-flask', 'Sciences'),
    ('bi-journal-check', 'Méthodologie'),
    ('bi-globe2', 'Culture générale'),
    ('bi-book', 'Livre'),
    ('bi-camera-video', 'Vidéo'),
    ('bi-file-earmark-text', 'Document'),
    ('bi-stars', 'Autre'),
]

TYPE_RESSOURCE = [
    ('pdf', 'PDF'),
    ('video', 'Vidéo'),
    ('support', 'Support / Présentation'),
]


class Categorie(models.Model):
    nom = models.CharField('Nom', max_length=100, unique=True)
    icone = models.CharField('Icône Bootstrap', max_length=50, choices=ICONES, default='bi-book')
    couleur = models.CharField('Couleur', max_length=20, choices=COULEURS, default='primary')

    class Meta:
        ordering = ['nom']
        verbose_name = 'catégorie'
        verbose_name_plural = 'catégories'

    def __str__(self):
        return self.nom

    def get_absolute_url(self):
        return reverse('ressources:categories')

    @property
    def nb_ressources(self):
        return self.ressources.count()


class Ressource(models.Model):
    titre = models.CharField('Titre', max_length=200)
    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.PROTECT,
        related_name='ressources',
        verbose_name='Catégorie',
    )
    type_ressource = models.CharField('Type', max_length=20, choices=TYPE_RESSOURCE, default='pdf')
    info = models.CharField('Information complémentaire', max_length=200, blank=True,
                            help_text='Ex : « 42 pages », « 12 min »')
    url = models.URLField('Lien / URL', blank=True,
                          help_text='Lien vers le document ou la vidéo (facultatif)')
    date_ajout = models.DateTimeField('Date d\'ajout', auto_now_add=True)

    class Meta:
        ordering = ['categorie__nom', 'titre']
        verbose_name = 'ressource'

    def __str__(self):
        return self.titre

    def get_absolute_url(self):
        return reverse('ressources:ressource_detail', args=[self.pk])

    @property
    def type(self):
        """Alias pour rester compatible avec les templates existants."""
        return self.type_ressource
