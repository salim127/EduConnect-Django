from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse

from . import test_ai
from .grading import save_submission, SubmissionError
from .grade_views import mark_records
from .learning import exercise_revision
from .models import Exercice, TentativeExercice, ParticipationExercice, EntrainementChapitre


class GradingTests(TestCase):
    setUp = test_ai.ChapterAITests.setUp

    def exercise(self, kind='qcm', title='Évaluation'):
        return Exercice.objects.create(cours=self.course, chapitre_id=self.chapter['id'], titre=title, type_exercice=kind,
            question='Choisir HTML', propositions='HTML\nCSS', bonne_reponse='HTML',
            questions_supplementaires=[{'question': 'Choisir CSS', 'propositions': 'HTML\nCSS', 'bonne_reponse': 'CSS'}])

    def submit(self, exercise, answers=('HTML', 'HTML'), number=1):
        self.client.force_login(self.student)
        return self.client.post(exercise.get_absolute_url(), {'exercise_revision': exercise_revision(exercise), 'attempt_number': number,
            **{f'reponse_{i}': answer for i, answer in enumerate(answers)}})

    def authorize(self, attempt, action='allow'):
        self.client.force_login(self.teacher)
        return self.client.post(reverse('pedagogie:retake_permission', args=[attempt.pk]), {'action': action})

    def test_qcm_grade_is_saved_and_repeat_or_forged_grade_is_blocked(self):
        exercise = self.exercise()
        response = self.submit(exercise)
        self.assertEqual(response.context['tentative'].note, Decimal('10.00'))
        attempt = exercise.tentatives.get()
        self.assertEqual(attempt.points_obtenus, 1)
        self.assertEqual(attempt.points_possibles, 2)
        response = self.submit(exercise, ('HTML', 'CSS'))
        self.assertEqual(response.context['tentative'].pk, attempt.pk)
        self.assertFalse(response.context['can_submit'])
        self.client.post(exercise.get_absolute_url(), {'attempt_number': 999, 'note': '20', 'reponse_0': 'HTML', 'reponse_1': 'CSS'})
        attempt.refresh_from_db()
        self.assertEqual(attempt.note, Decimal('10'))
        self.assertEqual(exercise.tentatives.count(), 1)
        page = self.client.get(exercise.get_absolute_url())
        self.assertContains(page, 'Une nouvelle tentative nécessite')
        self.assertNotContains(page, 'Obtenir un indice')
        self.assertNotContains(page, 'Soumettre et enregistrer mes réponses')

    def test_permission_is_personal_single_use_and_stale_tabs_cannot_consume_it(self):
        exercise = self.exercise()
        self.submit(exercise)
        first = exercise.tentatives.get()
        self.authorize(first)
        self.authorize(first)  # Double click grants only one slot.
        state = ParticipationExercice.objects.get(exercice=exercise, eleve=self.student)
        self.assertEqual(state.tentatives_autorisees, 2)
        self.submit(exercise, ('CSS', 'HTML'), number=1)
        state.refresh_from_db()
        self.assertEqual(state.tentatives_utilisees, 1)
        response = self.submit(exercise, ('CSS', 'HTML'), number=2)
        self.assertEqual(response.context['tentative'].note, Decimal('0'))
        self.assertEqual(exercise.tentatives.count(), 2)
        self.authorize(first)  # An old permission form cannot grant a third attempt.
        state.refresh_from_db()
        self.assertEqual(state.tentatives_autorisees, 2)
        self.submit(exercise, ('HTML', 'CSS'), number=3)
        self.assertEqual(exercise.tentatives.count(), 2)
        self.client.force_login(self.other)
        self.assertTrue(self.client.get(exercise.get_absolute_url()).context['can_submit'])

    def test_teacher_can_withdraw_unused_permission(self):
        exercise = self.exercise()
        self.submit(exercise)
        attempt = exercise.tentatives.get()
        self.authorize(attempt)
        self.authorize(attempt, 'revoke')
        self.submit(exercise, ('HTML', 'CSS'), number=2)
        self.assertEqual(exercise.tentatives.count(), 1)

    def test_only_owner_teacher_or_admin_can_read_class_results_and_grant_permissions(self):
        exercise = self.exercise()
        self.submit(exercise)
        attempt = exercise.tentatives.get()
        result_url = reverse('pedagogie:attempt_result', args=[attempt.pk])
        grant_url = reverse('pedagogie:retake_permission', args=[attempt.pk])
        self.assertEqual(self.client.get(reverse('pedagogie:gradebook')).status_code, 403)
        self.assertEqual(self.client.post(grant_url, {'action': 'allow'}).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(result_url).status_code, 404)
        self.assertEqual(self.client.post(grant_url, {'action': 'allow'}).status_code, 404)
        self.assertEqual(self.client.get(reverse('pedagogie:gradebook')).context['records'], [])
        self.assertEqual(self.client.get(reverse('pedagogie:my_grades')).context['records'], [])
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(result_url), '10,00')
        self.assertEqual(len(self.client.get(reverse('pedagogie:gradebook')).context['records']), 1)

    def test_average_has_equal_weight_per_exercise_and_uses_latest_confirmed_mark(self):
        first, second = self.exercise(title='Premier'), self.exercise(title='Second')
        self.submit(first)  # 10
        initial = first.tentatives.get()
        self.submit(second, ('HTML', 'CSS'))  # 20
        self.assertEqual(self.client.get(reverse('pedagogie:my_grades')).context['overall_average'], Decimal('15'))
        self.authorize(initial)
        self.submit(first, ('CSS', 'HTML'), 2)  # 0 replaces 10; never average the retakes together.
        page = self.client.get(reverse('pedagogie:my_grades'))
        self.assertEqual(page.context['overall_average'], Decimal('10'))
        self.assertEqual(page.context['summaries'][0]['average'], Decimal('10'))
        self.assertEqual(len(page.context['records']), 2)
        EntrainementChapitre.objects.create(eleve=self.student, cours=self.course, chapitre_id=self.chapter['id'], revision='x', questions=[], reponses=['x'], resultats=[False])
        self.assertEqual(self.client.get(reverse('pedagogie:my_grades')).context['overall_average'], Decimal('10'))

    def test_open_grade_requires_teacher_confirmation_and_ignores_ai_grade(self):
        exercise = self.exercise('ouverte')
        self.submit(exercise, ('Réponse libre', 'Autre réponse'))
        attempt = exercise.tentatives.get()
        self.assertIsNone(attempt.note)
        attempt.corrections = {'0': {'score': 1, 'maximum': 2}, '1': {'score': 2, 'maximum': 2}}
        attempt.save(update_fields=['corrections'])
        url = reverse('pedagogie:attempt_result', args=[attempt.pk])
        self.assertEqual(self.client.post(url, {'note': '20'}).status_code, 403)
        self.assertIsNone(self.client.get(reverse('pedagogie:my_grades')).context['overall_average'])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).context['ai_suggestion'], Decimal('15'))
        for value in ('21', '-1', 'NaN'):
            self.assertEqual(self.client.post(url, {'note': value}).status_code, 200)
            attempt.refresh_from_db()
            self.assertIsNone(attempt.note)
        response = self.client.post(url, {'note': '14', 'commentaire': 'Un exemple manque.', 'version': ''})
        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.note, Decimal('14'))
        self.assertEqual(attempt.validee_par, self.teacher)
        self.client.post(url, {'note': '19', 'version': ''})  # stale editing form
        attempt.refresh_from_db()
        self.assertEqual(attempt.note, Decimal('14'))
        self.client.force_login(self.student)
        self.assertContains(self.client.get(url), 'Un exemple manque.')
        self.assertEqual(self.client.get(reverse('pedagogie:my_grades')).context['overall_average'], Decimal('14'))

    def test_pending_retake_keeps_previous_confirmed_open_mark_until_teacher_validates(self):
        exercise = self.exercise('ouverte')
        self.submit(exercise, ('A', 'B'))
        first = exercise.tentatives.get()
        self.client.force_login(self.teacher)
        self.client.post(reverse('pedagogie:attempt_result', args=[first.pk]), {'note': '16', 'version': ''})
        self.authorize(first)
        self.submit(exercise, ('C', 'D'), 2)
        page = self.client.get(reverse('pedagogie:my_grades'))
        self.assertEqual(page.context['overall_average'], Decimal('16'))
        self.assertEqual(page.context['summaries'][0]['pending'], 1)

    def test_question_edits_keep_original_copy_mark_and_lock(self):
        exercise = self.exercise()
        self.submit(exercise)
        attempt = exercise.tentatives.get()
        exercise.question = 'Question entièrement différente'
        exercise.type_exercice = 'ouverte'
        exercise.save()
        page = self.client.get(exercise.get_absolute_url())
        self.assertFalse(page.context['can_submit'])
        self.assertContains(page, 'Choisir HTML')
        self.assertEqual(page.context['tentative'].note, Decimal('10'))
        self.assertNotContains(self.client.get(reverse('pedagogie:attempt_result', args=[attempt.pk])), 'Question entièrement différente')

    def test_invalid_answers_and_stale_revision_do_not_consume_attempt(self):
        exercise = self.exercise()
        self.client.force_login(self.student)
        for data in ({'reponse_0': 'HTML'}, {'reponse_0': 'NO', 'reponse_1': 'CSS'}, {'reponse_0': 'HTML', 'reponse_1': 'CSS', 'exercise_revision': 'old'}):
            self.client.post(exercise.get_absolute_url(), data)
        self.assertFalse(exercise.tentatives.exists())
        self.assertFalse(ParticipationExercice.objects.filter(exercice=exercise).exists())
        self.submit(exercise)
        self.assertEqual(exercise.tentatives.count(), 1)

    def test_teacher_preview_and_removed_hints_never_create_marks_or_ai_requests(self):
        exercise = self.exercise()
        self.client.force_login(self.teacher)
        self.assertTrue(self.client.get(exercise.get_absolute_url()).context['teacher_preview'])
        self.assertEqual(self.client.post(exercise.get_absolute_url(), {'reponse_0': 'HTML', 'reponse_1': 'CSS'}).status_code, 403)
        self.client.force_login(self.student)
        with patch('pedagogie.ai.request_json') as model:
            self.assertEqual(self.client.post(reverse('pedagogie:exercise_help', args=[exercise.pk]), {'action': 'hint', 'index': 0, 'revision': exercise_revision(exercise)}).status_code, 400)
        model.assert_not_called()
        self.assertFalse(TentativeExercice.objects.exists())

    def test_csrf_and_database_constraints_protect_marks_and_permissions(self):
        exercise = self.exercise()
        self.submit(exercise)
        attempt = exercise.tentatives.get()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        self.assertEqual(client.post(reverse('pedagogie:retake_permission', args=[attempt.pk]), {'action': 'allow'}).status_code, 403)
        self.assertEqual(client.post(reverse('pedagogie:attempt_result', args=[attempt.pk]), {'note': '20'}).status_code, 403)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TentativeExercice.objects.create(eleve=self.student, exercice=exercise, revision='x', numero=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TentativeExercice.objects.create(eleve=self.student, exercice=exercise, revision='x', numero=2, note=21)

    def test_rounding_and_true_false_use_same_scale_and_notes_survive_ui_deletion(self):
        exercise = Exercice.objects.create(cours=self.course, type_exercice='vf', titre='Trois questions', question='A', bonne_reponse='Vrai',
            questions_supplementaires=[{'question': 'B', 'propositions': '', 'bonne_reponse': 'Vrai'}, {'question': 'C', 'propositions': '', 'bonne_reponse': 'Faux'}])
        self.submit(exercise, ('Vrai', 'Faux', 'Vrai'))
        self.assertEqual(exercise.tentatives.get().note, Decimal('6.67'))
        self.client.force_login(self.teacher)
        self.client.post(reverse('pedagogie:exercice_delete', args=[exercise.pk]))
        self.client.post(reverse('pedagogie:cours_delete', args=[self.course.pk]))
        self.assertTrue(Exercice.objects.filter(pk=exercise.pk).exists())
        self.assertTrue(TentativeExercice.objects.filter(exercice=exercise).exists())


from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyGradeMigrationTests(TransactionTestCase):
    def test_existing_attempts_keep_history_get_numbers_and_automatic_marks(self):
        old_target = [('pedagogie', '0009_exercice_bareme_entrainementchapitre_and_more')]
        new_target = [('pedagogie', '0010_participationexercice_and_more')]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            User = old.get_model(settings.AUTH_USER_MODEL)
            teacher = User.objects.create(username='migration-teacher')
            student = User.objects.create(username='migration-student')
            course = old.get_model('pedagogie', 'Cours').objects.create(titre='Migration', enseignant_id=teacher.pk)
            exercise = old.get_model('pedagogie', 'Exercice').objects.create(cours_id=course.pk, titre='QCM', question='Question', bonne_reponse='A')
            Attempt = old.get_model('pedagogie', 'TentativeExercice')
            Attempt.objects.create(eleve_id=student.pk, exercice_id=exercise.pk, revision='old1', reponses=['A', 'B'], resultats=[True, False])
            Attempt.objects.create(eleve_id=student.pk, exercice_id=exercise.pk, revision='old2', reponses=['A', 'A'], resultats=[True, True])
            opened = old.get_model('pedagogie', 'Exercice').objects.create(cours_id=course.pk, titre='Ouverte', type_exercice='ouverte')
            Attempt.objects.create(eleve_id=student.pk, exercice_id=opened.pk, revision='old', reponses=['Libre'], resultats=[None])
            executor = MigrationExecutor(connection)
            executor.migrate(new_target)
            new = executor.loader.project_state(new_target).apps
            migrated = list(new.get_model('pedagogie', 'TentativeExercice').objects.filter(exercice_id=exercise.pk).order_by('numero'))
            self.assertEqual([a.numero for a in migrated], [1, 2])
            self.assertEqual([a.note for a in migrated], [Decimal('10'), Decimal('20')])
            state = new.get_model('pedagogie', 'ParticipationExercice').objects.get(exercice_id=exercise.pk, eleve_id=student.pk)
            self.assertEqual((state.tentatives_utilisees, state.tentatives_autorisees), (2, 2))
            self.assertIsNone(new.get_model('pedagogie', 'TentativeExercice').objects.get(exercice_id=opened.pk).note)
        finally:
            MigrationExecutor(connection).migrate(new_target)
