from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.roles import ensure_system_roles, TEACHER, LEARNER, ADMIN
from ressources.models import Categorie, Ressource


class RessourcesPermissionsAndAITests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_system_roles()
        User = get_user_model()

        self.teacher = User.objects.create_user(username='test_teacher', password='password123')
        self.teacher.groups.add(Group.objects.get(name=TEACHER))

        self.student = User.objects.create_user(username='test_student', password='password123')
        self.student.groups.add(Group.objects.get(name=LEARNER))

        self.admin = User.objects.create_user(username='test_admin', password='password123')
        self.admin.groups.add(Group.objects.get(name=ADMIN))

        self.cat_maths = Categorie.objects.create(nom='Mathématiques', icone='bi-calculator', couleur='primary')
        self.cat_info = Categorie.objects.create(nom='Informatique', icone='bi-code-slash', couleur='teal')

        self.res1 = Ressource.objects.create(
            titre='Cours Python Débutant',
            categorie=self.cat_info,
            type_ressource='pdf',
            info='45 pages',
        )
        self.res2 = Ressource.objects.create(
            titre='Algèbre Linéaire',
            categorie=self.cat_maths,
            type_ressource='support',
            info='Chapitre 1',
        )

    def test_bibliotheque_accessible_by_student_and_teacher(self):
        url = reverse('ressources:bibliotheque')

        # Student should access without 403
        self.client.force_login(self.student)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Bibliothèque de ressources')
        self.assertContains(resp, 'Trouve-moi une ressource')

        # Teacher should access without 403
        self.client.force_login(self.teacher)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Bibliothèque de ressources')
        self.assertContains(resp, 'Assistant IA — Trouver des ressources pour mes cours')

    def test_assistant_ia_for_student(self):
        url = reverse('ressources:assistant_ia')
        self.client.force_login(self.student)

        fake_ai_response = {
            'message': 'Voici des ressources adaptées :',
            'recommandations': [{'ressource_id': self.res1.pk, 'explication': 'Parfait pour débuter en Python'}],
            'conseil': 'Pratique chaque jour.',
        }
        with patch('ressources.ai_views.assistant_trouve_ressource', return_value=fake_ai_response):
            resp = self.client.post(url, {'besoin': 'Je veux apprendre Python'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data['message'], 'Voici des ressources adaptées :')
            self.assertEqual(len(data['recommandations']), 1)
            self.assertEqual(data['recommandations'][0]['titre'], 'Cours Python Débutant')

    def test_assistant_ia_with_matiere_filter(self):
        url = reverse('ressources:assistant_ia')
        self.client.force_login(self.teacher)

        fake_ai_response = {
            'message': 'Supports recommandés pour votre cours :',
            'recommandations': [{'ressource_id': self.res2.pk, 'explication': 'Support d algèbre complet'}],
            'conseil': 'Vous pouvez distribuer ces slides avant la séance.',
        }
        with patch('ressources.ai_views.assistant_trouve_ressource', return_value=fake_ai_response):
            resp = self.client.post(url, {'besoin': 'Préparer TD algèbre', 'categorie': str(self.cat_maths.pk)})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(len(data['recommandations']), 1)
            self.assertEqual(data['recommandations'][0]['titre'], 'Algèbre Linéaire')

    def test_fiche_pedagogique_permissions(self):
        url = reverse('ressources:fiche_ia', args=[self.res1.pk])

        # Student is forbidden (403)
        self.client.force_login(self.student)
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

        # Teacher is allowed
        self.client.force_login(self.teacher)
        fake_fiche = {
            'objectifs': ['Comprendre les boucles'],
            'public_cible': 'L1 Informatique',
            'prerequis': 'Aucun',
            'duree_estimee': '2 heures',
            'comment_utiliser': ['En travaux pratiques'],
            'conseils': ['Insister sur l indentation'],
        }
        with patch('ressources.ai_views.generer_fiche_pedagogique', return_value=fake_fiche):
            resp = self.client.post(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('fiche', resp.json())
