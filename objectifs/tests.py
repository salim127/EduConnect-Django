from datetime import date
from django.contrib.auth.models import User, Group, Permission
from django.test import TestCase
from django.urls import reverse
from accounts.roles import ensure_system_roles, LEARNER, TEACHER, ADMIN
from .forms import ObjectifForm, TacheForm
from .models import ObjectifApprentissage, TacheApprentissage


class AssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_system_roles()
        for name, role in [('prof', TEACHER), ('prof2', TEACHER), ('eleve', LEARNER), ('eleve2', LEARNER), ('admin', ADMIN)]:
            user = User.objects.create_user(name, password='test-password')
            user.groups.add(Group.objects.get(name=role))
            setattr(cls, name, user)
        cls.goal = ObjectifApprentissage.objects.create(titre='Python personnalisé', proprietaire=cls.prof, apprenant=cls.eleve, date_echeance=date(2027, 6, 1))
        cls.task = TacheApprentissage.objects.create(titre='Boucles personnalisées', objectif=cls.goal)

    def url(self, name, pk=None):
        return reverse('objectifs:' + name, args=[pk] if pk else [])

    def login(self, user):
        self.client.force_login(user)

    def goal_data(self, **kwargs):
        return dict(titre='Python', description='Bases', priorite='haute', niveau='debutant', decision='en_cours', critere_reussite='Réussir 8 questions sur 10', date_echeance='2027-06-01', apprenant=self.eleve.pk, **kwargs)

    def test_teacher_crud_and_assignment(self):
        self.login(self.prof)
        response = self.client.post(self.url('objectif_create'), self.goal_data())
        self.assertEqual(response.status_code, 302)
        goal = ObjectifApprentissage.objects.get(titre='Python')
        self.assertEqual(goal.proprietaire, self.prof)
        self.assertEqual(goal.apprenant, self.eleve)
        data = {'objectif': goal.pk, 'titre': 'Variables', 'description': '', 'statut': 'a_faire', 'date_echeance': '2027-05-01'}
        self.assertEqual(self.client.post(self.url('tache_create'), data).status_code, 302)
        task = goal.taches.get()
        data['statut'] = 'validee'
        self.assertEqual(self.client.post(self.url('tache_update', task.pk), data).status_code, 302)
        self.assertEqual(goal.progression, 0)  # Le formulaire général ne valide pas les tâches.
        data = self.goal_data()
        data['apprenant'] = self.eleve2.pk
        self.assertEqual(self.client.post(self.url('objectif_update', goal.pk), data).status_code, 302)
        goal.refresh_from_db()
        self.assertEqual(goal.apprenant, self.eleve2)
        self.assertEqual(self.client.post(self.url('objectif_delete', goal.pk)).status_code, 302)
        self.assertFalse(TacheApprentissage.objects.filter(pk=task.pk).exists())

    def test_teacher_pages_render(self):
        self.login(self.prof)
        for name, pk in [('objectif_list', None), ('tache_list', None), ('objectif_create', None), ('tache_create', None), ('objectif_detail', self.goal.pk), ('objectif_update', self.goal.pk), ('objectif_delete', self.goal.pk), ('tache_detail', self.task.pk), ('tache_update', self.task.pk), ('tache_delete', self.task.pk)]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name, pk)).status_code, 200)

    def test_learner_reads_assigned_goals_and_only_edits_status(self):
        self.login(self.eleve)
        self.assertContains(self.client.get(self.url('objectif_list')), self.goal.titre)
        response = self.client.get(self.task.get_absolute_url())
        self.assertContains(response, 'Rédiger mon travail')
        self.assertNotContains(response, self.url('tache_update', self.task.pk))
        self.assertNotContains(self.client.get(self.goal.get_absolute_url()), self.url('objectif_update', self.goal.pk))
        response = self.client.get(self.url('tache_statut', self.task.pk))
        self.assertEqual(set(response.context['form'].fields), {'reponse', 'action'})
        self.assertEqual(self.client.post(self.url('tache_statut', self.task.pk), {'action': 'soumettre', 'reponse': 'for i in range(1, 11): print(i)', 'statut': 'validee', 'titre': 'Piraté', 'objectif': 999, 'date_echeance': '2030-01-01'}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.titre, 'Boucles personnalisées')
        self.assertEqual(self.task.objectif, self.goal)
        self.assertIsNone(self.task.date_echeance)
        self.assertEqual(self.task.statut, 'soumise')
        self.assertEqual(self.goal.progression, 0)

    def test_learner_cannot_manage_even_with_extra_permissions(self):
        self.eleve.user_permissions.add(*Permission.objects.filter(content_type__app_label='objectifs'))
        self.login(self.eleve)
        for name, pk in [('objectif_create', None), ('tache_create', None), ('objectif_update', self.goal.pk), ('objectif_delete', self.goal.pk), ('tache_update', self.task.pk), ('tache_delete', self.task.pk)]:
            for method in [self.client.get, self.client.post]:
                with self.subTest(name=name, method=method):
                    self.assertEqual(method(self.url(name, pk)).status_code, 403)

    def test_other_learner_has_no_access(self):
        self.login(self.eleve2)
        self.assertNotContains(self.client.get(self.url('objectif_list')), self.goal.titre)
        self.assertNotContains(self.client.get(self.url('tache_list')), self.task.titre)
        for name, pk in [('objectif_detail', self.goal.pk), ('tache_detail', self.task.pk), ('tache_statut', self.task.pk)]:
            self.assertEqual(self.client.get(self.url(name, pk)).status_code, 404)
        self.assertEqual(self.client.post(self.url('tache_statut', self.task.pk), {'action': 'soumettre', 'reponse': 'Ma réponse complète'}).status_code, 404)

    def test_other_teacher_cannot_manage_or_link_tasks(self):
        self.login(self.prof2)
        self.assertNotContains(self.client.get(self.url('objectif_list')), self.goal.titre)
        for name, pk in [('objectif_detail', self.goal.pk), ('objectif_update', self.goal.pk), ('objectif_delete', self.goal.pk), ('tache_update', self.task.pk), ('tache_delete', self.task.pk)]:
            self.assertEqual(self.client.get(self.url(name, pk)).status_code, 404)
            if name != 'objectif_detail':
                self.assertEqual(self.client.post(self.url(name, pk)).status_code, 404)
        self.assertFalse(TacheForm(data={'objectif': self.goal.pk, 'titre': 'Interdit', 'statut': 'a_faire'}, user=self.prof2).is_valid())

    def test_admin_can_manage_all(self):
        self.login(self.admin)
        self.assertContains(self.client.get(self.url('objectif_list')), self.goal.titre)
        for name, pk in [('objectif_update', self.goal.pk), ('tache_update', self.task.pk), ('objectif_delete', self.goal.pk)]:
            self.assertEqual(self.client.get(self.url(name, pk)).status_code, 200)
        self.assertEqual(self.client.post(self.url('objectif_update', self.goal.pk), self.goal_data()).status_code, 302)

    def test_assignment_required_and_only_active_learners(self):
        for pk in ['', self.prof.pk, self.admin.pk]:
            data = self.goal_data()
            data['apprenant'] = pk
            form = ObjectifForm(data=data)
            self.assertFalse(form.is_valid())
            self.assertIn('apprenant', form.errors)
        self.eleve.is_active = False
        self.eleve.save()
        self.assertFalse(ObjectifForm(data=self.goal_data()).is_valid())

    def test_deadlines_and_invalid_status(self):
        form = TacheForm(data={'objectif': self.goal.pk, 'titre': 'Retard', 'statut': 'a_faire', 'date_echeance': '2027-07-01'}, user=self.prof)
        self.assertFalse(form.is_valid())
        self.assertIn('date_echeance', form.errors)
        self.task.date_echeance = date(2027, 5, 1)
        self.task.save()
        data = self.goal_data()
        data['date_echeance'] = '2027-04-01'
        self.assertFalse(ObjectifForm(data=data, instance=self.goal).is_valid())
        self.login(self.eleve)
        self.assertEqual(self.client.post(self.url('tache_statut', self.task.pk), {'statut': 'invalide'}).status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.statut, 'a_faire')

    def test_filters_anonymous_and_safe_delete(self):
        self.login(self.prof)
        self.assertContains(self.client.get(self.url('tache_list'), {'q': 'Boucles', 'statut': 'a_faire'}), self.task.titre)
        self.assertNotContains(self.client.get(self.url('tache_list'), {'statut': 'soumise'}), self.task.titre)
        self.client.get(self.url('objectif_delete', self.goal.pk))
        self.assertTrue(ObjectifApprentissage.objects.filter(pk=self.goal.pk).exists())
        self.client.logout()
        self.assertEqual(self.client.get(self.goal.get_absolute_url()).status_code, 302)

    def test_reassignment_revokes_previous_learner_access(self):
        self.goal.apprenant = self.eleve2
        self.goal.save()
        self.login(self.eleve)
        self.assertEqual(self.client.get(self.goal.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(self.url('tache_statut', self.task.pk), {'action': 'soumettre', 'reponse': 'Ma réponse complète'}).status_code, 404)
        self.login(self.eleve2)
        self.assertEqual(self.client.get(self.goal.get_absolute_url()).status_code, 200)

    def test_default_learner_permissions(self):
        self.assertTrue(self.eleve.has_perm('objectifs.view_objectifapprentissage'))
        self.assertTrue(self.eleve.has_perm('objectifs.update_statut_tacheapprentissage'))
        for code in ['add_objectifapprentissage', 'change_objectifapprentissage', 'delete_objectifapprentissage', 'add_tacheapprentissage', 'change_tacheapprentissage', 'delete_tacheapprentissage']:
            self.assertFalse(self.eleve.has_perm('objectifs.' + code))


    def test_django_admin_creates_assigned_goal(self):
        superuser = User.objects.create_superuser('root', password='test-password', email='root@example.com')
        self.login(superuser)
        response = self.client.post(reverse('admin:objectifs_objectifapprentissage_add'), self.goal_data())
        self.assertEqual(response.status_code, 302)
        goal = ObjectifApprentissage.objects.get(titre='Python')
        self.assertEqual(goal.proprietaire, superuser)
        self.assertEqual(goal.apprenant, self.eleve)


    def test_submission_review_rework_and_progress(self):
        self.login(self.eleve)
        url = self.url('tache_statut', self.task.pk)
        self.assertEqual(self.client.post(url, {'action': 'brouillon', 'reponse': 'Mon brouillon'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'action': 'soumettre', 'reponse': 'Ma réponse complète'}).status_code, 302)
        self.assertEqual(self.goal.progression, 0)
        self.assertEqual(self.client.post(url, {'statut': 'a_faire'}).status_code, 404)
        self.login(self.prof)
        review = self.url('tache_validation', self.task.pk)
        self.assertContains(self.client.get(self.task.get_absolute_url()), 'Valider ou demander une reprise')
        self.assertEqual(self.client.get(review).status_code, 200)
        self.assertEqual(self.client.post(review, {'statut': 'a_reprendre'}).status_code, 302)
        self.assertEqual(self.goal.progression, 0)
        self.login(self.eleve)
        self.assertContains(self.client.get(self.task.get_absolute_url()), 'Le professeur demande une reprise')
        self.assertEqual(self.client.post(url, {'action': 'soumettre', 'reponse': 'Ma réponse complète'}).status_code, 302)
        self.login(self.prof)
        self.assertEqual(self.client.post(review, {'statut': 'validee'}).status_code, 302)
        self.assertEqual(self.goal.progression, 100)
        self.assertEqual(self.client.post(review, {'statut': 'a_reprendre'}).status_code, 404)
        self.login(self.eleve)
        self.assertEqual(self.client.post(url, {'action': 'soumettre', 'reponse': 'Ma réponse complète'}).status_code, 404)
        self.assertNotContains(self.client.get(self.task.get_absolute_url()), 'Rédiger mon travail')

    def test_learner_cannot_self_validate_or_review(self):
        self.login(self.eleve)
        for status in ['validee', 'a_reprendre', 'terminee']:
            self.assertEqual(self.client.post(self.url('tache_statut', self.task.pk), {'statut': status}).status_code, 200)
            self.task.refresh_from_db()
            self.assertEqual(self.task.statut, 'a_faire')
        self.task.statut = 'soumise'
        self.task.save()
        self.assertEqual(self.client.post(self.url('tache_validation', self.task.pk), {'statut': 'validee'}).status_code, 403)
        self.assertEqual(self.goal.progression, 0)

    def test_review_requires_submission_and_ownership(self):
        url = self.url('tache_validation', self.task.pk)
        self.login(self.prof)
        self.assertEqual(self.client.post(url, {'statut': 'validee'}).status_code, 404)
        self.task.statut = 'soumise'
        self.task.save()
        self.login(self.prof2)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'statut': 'validee'}).status_code, 404)
        self.login(self.admin)
        self.assertEqual(self.client.post(url, {'statut': 'invalide'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'statut': 'validee'}).status_code, 302)
        self.assertEqual(self.goal.progression, 100)

    def test_new_fields_and_validation(self):
        data = self.goal_data()
        data['niveau'] = 'intermediaire'
        form = ObjectifForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        data['critere_reussite'] = ''
        self.assertFalse(ObjectifForm(data=data).is_valid())
        data['critere_reussite'] = 'Réussir le test'
        data['niveau'] = 'invalide'
        self.assertFalse(ObjectifForm(data=data).is_valid())
        for duration in [0, -10, 'invalide']:
            form = TacheForm(data={'objectif': self.goal.pk, 'titre': 'Test', 'duree_estimee': duration}, user=self.prof)
            self.assertFalse(form.is_valid())
            self.assertIn('duree_estimee', form.errors)
        self.login(self.prof)
        self.assertEqual(self.client.post(self.url('tache_update', self.task.pk), {'objectif': self.goal.pk, 'titre': self.task.titre, 'duree_estimee': 45}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.duree_estimee, 45)
        self.assertContains(self.client.get(self.task.get_absolute_url()), '45 minutes')

    def test_progress_counts_only_validated_tasks(self):
        self.task.statut = 'validee'
        self.task.save()
        TacheApprentissage.objects.create(titre='Deuxième', objectif=self.goal, statut='soumise')
        self.assertEqual(self.goal.progression, 50)


    def test_draft_persists_and_statut_is_never_accepted(self):
        self.login(self.eleve)
        url = self.url('tache_travail', self.task.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="statut"')
        self.assertContains(response, 'Enregistrer le brouillon')
        self.assertContains(response, 'Soumettre mon travail')
        text = 'for i in range(1, 11):\n    print(i)'
        self.assertEqual(self.client.post(url, {'action': 'brouillon', 'reponse': text, 'statut': 'validee'}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.reponse, text)
        self.assertEqual(self.task.statut, 'en_cours')
        self.assertIsNone(self.task.date_soumission)
        self.assertEqual(self.client.get(url).context['form'].initial['reponse'], text)
        self.assertEqual(self.client.post(url, {'action': 'soumettre', 'reponse': text, 'statut': 'validee'}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.statut, 'soumise')
        self.assertIsNotNone(self.task.date_soumission)
        self.assertEqual(self.client.post(url, {'action': 'brouillon', 'reponse': 'Modification tardive'}).status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.reponse, text)
        self.login(self.prof)
        self.assertContains(self.client.get(self.url('tache_validation', self.task.pk)), 'for i in range(1, 11):')

    def test_empty_work_and_invalid_action_are_rejected(self):
        self.login(self.eleve)
        url = self.url('tache_travail', self.task.pk)
        for data in [{'action': 'soumettre', 'reponse': ''}, {'action': 'soumettre', 'reponse': '   '}, {'action': 'valider', 'reponse': 'Test'}, {'reponse': 'Test'}, {'statut': 'validee'}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(url, data).status_code, 200)
                self.task.refresh_from_db()
                self.assertEqual(self.task.statut, 'a_faire')
                self.assertEqual(self.task.reponse, '')
                self.assertIsNone(self.task.date_soumission)

    def test_work_is_escaped_and_only_assignee_can_write(self):
        self.login(self.eleve)
        text = '<script>alert(1)</script>'
        self.client.post(self.url('tache_travail', self.task.pk), {'action': 'soumettre', 'reponse': text})
        self.assertContains(self.client.get(self.task.get_absolute_url()), '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(self.client.get(self.task.get_absolute_url()), text)
        self.login(self.prof)
        page = self.client.get(self.url('tache_validation', self.task.pk))
        self.assertContains(page, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(page, text)
        self.task.statut = 'a_reprendre'
        self.task.save()
        for user in [self.prof, self.eleve2]:
            self.login(user)
            self.assertEqual(self.client.post(self.url('tache_travail', self.task.pk), {'action': 'soumettre', 'reponse': 'Interdit'}).status_code, 403 if user == self.prof else 404)


    def test_statistics_roles_and_totals(self):
        from .models import TempsActivite
        from django.utils import timezone
        TempsActivite.objects.create(utilisateur=self.eleve, tache=self.task, jour=timezone.localdate(), secondes=120)
        for user in [self.prof, self.eleve, self.admin]:
            self.login(user)
            page = self.client.get(self.url('statistiques'))
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context['total_minutes'], 2.0)
            self.assertEqual(page.context['total_taches'], 1)
            self.assertEqual(len(page.context['jours']), 7)
        self.login(self.eleve2)
        page = self.client.get(self.url('statistiques'))
        self.assertEqual(page.context['total_minutes'], 0)
        self.assertNotContains(page, self.goal.titre)
        self.assertEqual(self.client.post(self.url('statistiques'), {'objectif': self.goal.pk}).status_code, 404)

    def test_activity_counts_server_time_and_ignores_client_duration(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import HorlogeActivite, TempsActivite
        self.login(self.eleve)
        url = self.url('activite', self.task.pk)
        first = self.client.post(url, {'active': 'true', 'secondes': 99999})
        self.assertEqual(first.json()['secondes_ajoutees'], 0)
        HorlogeActivite.objects.filter(utilisateur=self.eleve).update(dernier_signal=timezone.now()-timedelta(seconds=10))
        self.assertEqual(self.client.post(url, {'active': 'true', 'secondes': 99999}).json()['secondes_ajoutees'], 10)
        self.assertEqual(TempsActivite.objects.get().secondes, 10)
        self.assertEqual(self.client.post(url, {'active': 'true'}).json()['secondes_ajoutees'], 0)
        HorlogeActivite.objects.filter(utilisateur=self.eleve).update(dernier_signal=timezone.now()-timedelta(seconds=120))
        self.assertEqual(self.client.post(url, {'active': 'true'}).json()['secondes_ajoutees'], 0)

    def test_activity_pause_and_permissions(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import HorlogeActivite
        self.login(self.eleve)
        url = self.url('activite', self.task.pk)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'active': 'invalid'}).status_code, 400)
        self.client.post(url, {'active': 'false'})
        HorlogeActivite.objects.filter(utilisateur=self.eleve).update(dernier_signal=timezone.now()-timedelta(seconds=10))
        self.assertEqual(self.client.post(url, {'active': 'true'}).json()['secondes_ajoutees'], 0)
        self.login(self.eleve2)
        self.assertEqual(self.client.post(url, {'active': 'true'}).status_code, 404)
        self.login(self.prof)
        self.assertEqual(self.client.post(url, {'active': 'true'}).status_code, 403)
        self.login(self.eleve)
        self.task.statut = 'soumise'
        self.task.save()
        self.assertEqual(self.client.post(url, {'active': 'true'}).status_code, 404)

    def test_multiple_tasks_share_one_clock(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import HorlogeActivite, TempsActivite
        other = TacheApprentissage.objects.create(titre='Autre tâche', objectif=self.goal)
        self.login(self.eleve)
        self.client.post(self.url('activite', self.task.pk), {'active': 'true'})
        HorlogeActivite.objects.filter(utilisateur=self.eleve).update(dernier_signal=timezone.now()-timedelta(seconds=10))
        self.assertEqual(self.client.post(self.url('activite', other.pk), {'active': 'true'}).json()['secondes_ajoutees'], 0)
        self.assertEqual(HorlogeActivite.objects.filter(utilisateur=self.eleve).count(), 1)
        self.assertFalse(TempsActivite.objects.exists())

    def test_gemini_missing_key_and_mock_analysis(self):
        from django.test import override_settings
        from unittest.mock import patch
        self.login(self.prof)
        with override_settings(GEMINI_API_KEY=''):
            page = self.client.post(self.url('statistiques'), {'objectif': self.goal.pk})
            self.assertContains(page, 'Gemini n’est pas configuré')
        session = self.client.session
        session.pop('derniere_analyse', None)
        session.save()
        with override_settings(GEMINI_API_KEY='test-only'), patch('objectifs.statistiques.analyse_gemini', return_value='<script>test</script> Objectif partiellement atteint'):
            page = self.client.post(self.url('statistiques'), {'objectif': self.goal.pk})
            self.assertContains(page, '&lt;script&gt;test&lt;/script&gt;')
            self.assertNotContains(page, '<script>test</script>')
            self.goal.refresh_from_db()
            self.assertEqual(self.goal.decision, 'en_cours')
            self.task.refresh_from_db()
            self.assertEqual(self.task.statut, 'a_faire')
            self.assertContains(self.client.post(self.url('statistiques'), {'objectif': self.goal.pk}), 'Attendez 30 secondes')

    def test_gemini_transport_uses_header_and_no_user_names(self):
        import io
        import json
        from unittest.mock import patch
        from django.test import override_settings
        from .statistiques import analyse_gemini
        payload = {'candidates': [{'content': {'parts': [{'text': 'Données insuffisantes.'}]}}]}
        with override_settings(GEMINI_API_KEY='secret-test', GEMINI_MODEL='gemini-2.5-flash'), patch('config.gemini.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as mocked:
            self.assertEqual(analyse_gemini(self.goal, 60), 'Données insuffisantes.')
            req = mocked.call_args.args[0]
            self.assertNotIn('secret-test', req.full_url)
            self.assertEqual(req.get_header('X-goog-api-key'), 'secret-test')
            self.assertNotIn('username', req.data.decode())

    def test_statistics_csrf_and_goal_decision(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.eleve)
        self.assertEqual(strict.post(self.url('activite', self.task.pk), {'active': 'true'}).status_code, 403)
        self.login(self.prof)
        data = self.goal_data()
        data['decision'] = 'atteint'
        self.assertEqual(self.client.post(self.url('objectif_update', self.goal.pk), data).status_code, 302)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.decision, 'atteint')
        self.assertEqual(self.goal.progression, 0)


    def test_intelligence_pages_and_role_access(self):
        for user in [self.prof, self.eleve, self.admin]:
            self.login(user)
            for route in ['charge', 'recherche_sens']:
                self.assertEqual(self.client.get(self.url(route)).status_code, 200)
        self.login(self.eleve)
        self.assertEqual(self.client.get(self.url('besoins')).status_code, 403)
        self.assertEqual(self.client.post(self.url('besoins')).status_code, 403)
        self.assertEqual(self.client.get(self.url('disponibilite')).status_code, 200)
        self.login(self.prof)
        self.assertEqual(self.client.get(self.url('disponibilite')).status_code, 403)
        self.assertContains(self.client.get(self.url('besoins')), 'Données insuffisantes')
        self.client.logout()
        self.assertEqual(self.client.get(self.url('charge')).status_code, 302)

    def test_availability_changes_only_current_user(self):
        from .models import DisponibiliteApprenant
        self.login(self.eleve)
        self.assertEqual(self.client.post(self.url('disponibilite'), {'minutes_semaine': 180, 'utilisateur': self.eleve2.pk}).status_code, 302)
        self.assertEqual(DisponibiliteApprenant.objects.get(utilisateur=self.eleve).minutes_semaine, 180)
        self.assertFalse(DisponibiliteApprenant.objects.filter(utilisateur=self.eleve2).exists())
        for value in [-1, 10081, 'abc']:
            self.assertEqual(self.client.post(self.url('disponibilite'), {'minutes_semaine': value}).status_code, 200)
        self.assertEqual(self.client.post(self.url('disponibilite'), {'minutes_semaine': 0}).status_code, 302)
        self.assertEqual(self.client.post(self.url('disponibilite'), {'minutes_semaine': ''}).status_code, 302)
        self.assertIsNone(DisponibiliteApprenant.objects.get(utilisateur=self.eleve).minutes_semaine)

    def test_workload_capacity_cumulative_and_early_deadline(self):
        from .models import DisponibiliteApprenant
        from .intelligence import calcul_charges
        today = date(2027, 5, 26)
        self.task.duree_estimee = 100
        self.task.save()
        goals = [self.goal]
        self.assertIn('non renseignée', calcul_charges(goals, today)[self.goal.pk]['motif'])
        DisponibiliteApprenant.objects.create(utilisateur=self.eleve, minutes_semaine=120)
        row = calcul_charges(goals, today)[self.goal.pk]
        self.assertEqual(row['capacite'], 120)
        self.assertFalse(row['alerte'])
        other = ObjectifApprentissage.objects.create(titre='Autre objectif', proprietaire=self.prof, apprenant=self.eleve, date_echeance=self.goal.date_echeance)
        TacheApprentissage.objects.create(titre='Autre tâche', objectif=other, duree_estimee=50)
        row = calcul_charges([self.goal, other], today)[self.goal.pk]
        self.assertEqual(row['cumul'], 150)
        self.assertTrue(row['alerte'])
        self.task.statut = 'validee'
        self.task.save()
        self.assertEqual(calcul_charges([self.goal], today)[self.goal.pk]['restant'], 0)
        self.task.statut = 'a_faire'
        self.task.date_echeance = today
        self.task.save()
        self.assertTrue(calcul_charges([self.goal], today)[self.goal.pk]['alerte'])

    def test_workload_incomplete_past_and_no_deadline(self):
        from .models import DisponibiliteApprenant
        from .intelligence import calcul_charges
        DisponibiliteApprenant.objects.create(utilisateur=self.eleve, minutes_semaine=0)
        row = calcul_charges([self.goal], date(2027, 6, 2))[self.goal.pk]
        self.assertIn('incompl', row['motif'])
        self.task.duree_estimee = 20
        self.task.save()
        self.assertTrue(calcul_charges([self.goal], date(2027, 6, 2))[self.goal.pk]['alerte'])
        self.goal.date_echeance = None
        self.goal.save()
        self.assertIn('Échéance', calcul_charges([self.goal])[self.goal.pk]['motif'])

    def test_semantic_search_scope_json_validation_and_fallback(self):
        import json
        from unittest.mock import patch
        from .intelligence import recherche_sens, recherche_locale
        self.goal.titre = 'Maîtriser les boucles Python'
        self.goal.save()
        payload = {'resultats': [{'id': self.goal.pk, 'raison': 'Répétition avec for et while'}, {'id': 9999, 'raison': 'Interdit'}, {'id': self.goal.pk, 'raison': 'Doublon'}]}
        with patch('objectifs.intelligence.appel_gemini', return_value=json.dumps(payload)) as api:
            result = recherche_sens('répéter des instructions', [self.goal])
            self.assertEqual([r['goal'].pk for r in result], [self.goal.pk])
            self.assertNotIn('username', api.call_args.args[0])
        self.assertEqual(recherche_locale('je veux apprendre à répéter des instructions', [self.goal])[0]['goal'], self.goal)
        self.login(self.eleve)
        with patch('objectifs.intelligence.appel_gemini', side_effect=ValueError('Quota atteint')):
            page = self.client.post(self.url('recherche_sens'), {'q': 'répéter des instructions'})
            self.assertContains(page, self.goal.titre)
            self.assertContains(page, 'sans analyse IA')
        self.login(self.eleve2)
        with patch('objectifs.intelligence.appel_gemini') as api:
            page = self.client.post(self.url('recherche_sens'), {'q': 'répéter'})
            self.assertNotContains(page, self.goal.titre)
            api.assert_not_called()

    def test_semantic_get_does_not_call_ai_and_bad_json(self):
        from unittest.mock import patch
        from .intelligence import recherche_sens
        self.login(self.eleve)
        with patch('objectifs.intelligence.appel_gemini') as api:
            self.client.get(self.url('recherche_sens'), {'q': 'boucles'})
            api.assert_not_called()
        for response in ['oops', '[]', '{"resultats":42}']:
            with patch('objectifs.intelligence.appel_gemini', return_value=response):
                with self.assertRaises(ValueError):
                    recherche_sens('test', [self.goal])

    def needs_records(self):
        from .intelligence import donnees_besoins
        other = ObjectifApprentissage.objects.create(titre='Python 2', proprietaire=self.prof, apprenant=self.eleve2)
        task = TacheApprentissage.objects.create(titre='Boucles 2', objectif=other, statut='a_reprendre', reponse='while True: print(1)')
        self.task.statut = 'a_reprendre'
        self.task.reponse = 'while True: print(2)'
        self.task.save()
        return donnees_besoins([self.goal, other]), task

    def test_grouping_evidence_checked_and_no_drafts(self):
        import json
        from unittest.mock import patch
        from .intelligence import regrouper_besoins, donnees_besoins
        self.assertEqual(donnees_besoins([self.goal]), [])
        records, other_task = self.needs_records()
        payload = {'groupes': [{'besoin': 'Condition d’arrêt', 'accompagnement': 'Exercice guidé', 'membres': [
            {'apprenant': self.eleve.pk, 'preuves': [self.task.pk], 'raison': 'Pas de condition de sortie'},
            {'apprenant': self.eleve2.pk, 'preuves': [other_task.pk], 'raison': 'Boucle infinie'},
            {'apprenant': self.admin.pk, 'preuves': [other_task.pk], 'raison': 'Inventé'}]}]}
        with patch('objectifs.intelligence.appel_gemini', return_value=json.dumps(payload)) as api:
            groups = regrouper_besoins(records)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]['membres']), 2)
            self.assertNotIn('username', api.call_args.args[0])
        payload['groupes'][0]['membres'][1]['preuves'] = [self.task.pk]
        with patch('objectifs.intelligence.appel_gemini', return_value=json.dumps(payload)):
            self.assertEqual(regrouper_besoins(records), [])

    def test_grouping_views_no_hidden_students_and_insufficient_data(self):
        from unittest.mock import patch
        self.login(self.prof)
        with patch('objectifs.intelligence.appel_gemini') as api:
            self.assertContains(self.client.post(self.url('besoins')), 'Données insuffisantes')
            api.assert_not_called()
        records, other_task = self.needs_records()
        with patch('objectifs.intelligence.appel_gemini', return_value='{"groupes": []}'):
            self.assertContains(self.client.post(self.url('besoins')), 'Aucun besoin commun')
        self.login(self.prof2)
        page = self.client.get(self.url('besoins'))
        self.assertEqual(page.context['nombre_apprenants'], 0)

    def test_intelligence_csrf_invalid_form_and_escaped_ai(self):
        import json
        from unittest.mock import patch
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.prof)
        self.assertEqual(strict.post(self.url('besoins')).status_code, 403)
        self.login(self.eleve)
        self.assertEqual(self.client.post(self.url('recherche_sens'), {'q': ' '}).status_code, 200)
        payload = {'resultats': [{'id': self.goal.pk, 'raison': '<script>alert(1)</script>'}]}
        with patch('objectifs.intelligence.appel_gemini', return_value=json.dumps(payload)):
            page = self.client.post(self.url('recherche_sens'), {'q': 'python'})
            self.assertContains(page, '&lt;script&gt;alert(1)&lt;/script&gt;')
            self.assertNotContains(page, '<script>alert(1)</script>')


    def test_gemini_json_mode_and_truncation_error(self):
        import io
        import json
        from unittest.mock import patch
        from django.test import override_settings
        from .statistiques import appel_gemini
        payload = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"groupes": []}'}]}}]}
        with override_settings(GEMINI_API_KEY='test', GEMINI_MODEL='gemini-2.5-flash'), patch('config.gemini.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as api:
            self.assertEqual(appel_gemini('test', json_mode=True), '{"groupes": []}')
            config = json.loads(api.call_args.args[0].data)['generationConfig']
            self.assertEqual(config['responseMimeType'], 'application/json')
            self.assertEqual(config['thinkingConfig']['thinkingBudget'], 0)
        payload['candidates'][0]['finishReason'] = 'MAX_TOKENS'
        with override_settings(GEMINI_API_KEY='test'), patch('config.gemini.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesMessage(ValueError, 'interrompue'):
                appel_gemini('test', json_mode=True)
