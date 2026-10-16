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
        return dict(titre='Python', description='Bases', priorite='haute', niveau='debutant', critere_reussite='Réussir 8 questions sur 10', date_echeance='2027-06-01', apprenant=self.eleve.pk, **kwargs)

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
