from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from accounts.roles import ADMIN, LEARNER, TEACHER, ensure_system_roles
from pedagogie.models import Cours, Exercice

USERS = [  # (username, prénom, nom, rôle, mot de passe) — comptes de démonstration
    ('admin', 'Amel', 'Admin', ADMIN, 'Admin1234!'),
    ('prof', 'Karim', 'Enseignant', TEACHER, 'Prof1234!'),
    ('eleve', 'Sarra', 'Apprenante', LEARNER, 'Eleve1234!'),
]

COURS = [
    ('Introduction à Python', 'Les bases du langage : variables, types et boucles.', 'Informatique', 'debutant',
     'Python est un langage simple et lisible.\n\n1. Variables et types\n2. Conditions\n3. Boucles for et while'),
    ('Bases des mathématiques', 'Fractions, proportions et calcul mental.', 'Mathématiques', 'debutant',
     'Une fraction représente une part d\'un tout : a/b.\n\nPour additionner deux fractions, on les met au même dénominateur.'),
    ('Anglais débutant', 'Vocabulaire et phrases essentielles du quotidien.', 'Langues', 'debutant',
     'Greetings: Hello, Good morning, Goodbye.\nIntroductions: My name is..., I am from...'),
]

EXERCICES = [
    ('Variables Python', 0, 'qcm', 'facile', 'Quelle instruction crée une variable x valant 5 ?', 'x = 5', 'x := 5\nx = 5\nint x = 5\nlet x == 5'),
    ('Boucles Python', 0, 'vf', 'moyen', 'Une boucle while s\'exécute au moins une fois.', 'Faux', ''),
    ('Calcul de fractions', 1, 'ouverte', 'moyen', 'Calculez 1/2 + 1/3.', '5/6', ''),
    ('Vocabulaire anglais', 2, 'qcm', 'facile', 'Comment dit-on « Bonjour » en anglais ?', 'Hello', 'Hello\nGoodbye\nThanks\nSorry'),
]


class Command(BaseCommand):
    help = 'Crée les rôles, 3 comptes et quelques cours/exercices de démonstration.'

    def handle(self, *args, **opts):
        ensure_system_roles()
        for username, first, last, role, pwd in USERS:
            u, created = User.objects.get_or_create(username=username, defaults={
                'first_name': first, 'last_name': last, 'email': f'{username}@hub.local',
                'is_staff': role == ADMIN, 'is_superuser': role == ADMIN})
            if created:
                u.set_password(pwd)
                u.save()
            u.groups.set([Group.objects.get(name=role)])
        prof = User.objects.get(username='prof')
        cours = [Cours.objects.get_or_create(titre=t, defaults=dict(
            description=d, matiere=m, niveau=n, contenu=c, enseignant=prof))[0] for t, d, m, n, c in COURS]
        for titre, ci, typ, diff, q, rep, props in EXERCICES:
            ex, created = Exercice.objects.get_or_create(titre=titre, cours=cours[ci], defaults=dict(
                type_exercice=typ, difficulte=diff, question=q, bonne_reponse=rep, propositions=props))
        self.stdout.write(self.style.SUCCESS('Données de démonstration prêtes.'))
