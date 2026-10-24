import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from .ai import AIError, study_material, correct_open_answer
from .forms import ExerciceForm, QuestionQCMForm
from .learning import exercise_revision, parse_rubric, personal_weaknesses
from .models import Exercice, TentativeExercice, EntrainementChapitre
from . import test_ai


class LearningTests(TestCase):
    setUp = test_ai.ChapterAITests.setUp

    def urls(self, name):
        return reverse(f'pedagogie:{name}', args=[self.course.pk, self.chapter['id']])

    def exercise(self, kind='qcm'):
        return Exercice.objects.create(cours=self.course, chapitre_id=self.chapter['id'], titre='Pratique',
            question='Quel langage structure une page ?', propositions='HTML\nCSS' if kind == 'qcm' else '',
            type_exercice=kind, bonne_reponse='HTML', bareme='Définition | 2\nExemple | 1' if kind == 'ouverte' else '')

    def help_data(self, exercise, action, **kwargs):
        return {'action': action, 'index': 0, 'revision': exercise_revision(exercise), **kwargs}

    def submit(self, exercise, answer='CSS', number=1):
        self.client.post(exercise.get_absolute_url(), {'reponse_0': answer, 'attempt_number': number})
        return TentativeExercice.objects.filter(exercice=exercise).latest('pk')

    def feedback(self):
        return {'criteres': [{'id': 'C1', 'critere': 'Définition', 'maximum': 2, 'points': 1, 'commentaire': 'À préciser'},
                             {'id': 'C2', 'critere': 'Exemple', 'maximum': 1, 'points': 0, 'commentaire': 'Absent'}],
                'score': 1, 'maximum': 3, 'corrects': ['Bonne idée'], 'manquants': ['Un exemple'], 'conseil': 'Ajoutez un exemple.', 'truncated': False}

    def test_study_get_is_free_and_generated_material_is_reused_then_invalidated(self):
        url = self.urls('chapter_study')
        self.client.force_login(self.student)
        summary = {'notions': ['HTML', 'CSS', 'Le Web'], 'exemples': ['Une page HTML'], 'citations': [], 'truncated': False}
        with patch('pedagogie.learning_views.study_material', return_value=summary) as model:
            self.assertEqual(self.client.get(url).status_code, 200)
            model.assert_not_called()
            self.assertContains(self.client.post(url, {'action': 'summary'}), 'Une page HTML')
            self.client.post(url, {'action': 'summary'})
            self.assertEqual(model.call_count, 1)
            self.chapter['contenu'] += '<p>Une notion ajoutée.</p>'
            self.course.chapitres = [self.chapter]
            self.course.save()
            self.assertNotContains(self.client.get(url), 'Une page HTML')
            self.client.post(url, {'action': 'summary'})
            self.assertEqual(model.call_count, 2)

    def test_study_validates_citations_and_escapes_flashcards(self):
        quote = [{'source_id': 'S1', 'extrait': 'HTML structure les pages web.'}]
        summary = {'notions': ['A', 'B', 'C'], 'exemples': ['Exemple'], 'citations': quote}
        with patch('pedagogie.ai.request_json', return_value=summary):
            result = study_material(self.course, self.chapter, self.student, 'summary')
            self.assertEqual(len(result['citations']), 1)
        summary['citations'] = [{'source_id': 'S1', 'extrait': 'Passage totalement inventé.'}]
        with patch('pedagogie.ai.request_json', return_value=summary), self.assertRaises(AIError):
            study_material(self.course, self.chapter, self.student, 'summary')
        cards = {'cartes': [{'question': '<script>alert(1)</script>', 'reponse': 'HTML', 'citations': quote} for _ in range(6)]}
        self.client.force_login(self.student)
        with patch('pedagogie.ai.request_json', return_value=cards):
            response = self.client.post(self.urls('chapter_study'), {'action': 'cards'})
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;', count=6)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, 'Voir la réponse', count=6)

    def test_hidden_chapter_blocks_all_learning_endpoints_before_model(self):
        exercise = self.exercise()
        self.chapter['masque'] = True
        self.course.chapitres = [self.chapter]
        self.course.save()
        self.client.force_login(self.student)
        with patch('pedagogie.ai.request_json') as model:
            for name in ('chapter_study', 'chapter_practice'):
                self.assertEqual(self.client.get(self.urls(name)).status_code, 404)
                self.assertEqual(self.client.post(self.urls(name), {'action': 'summary'}).status_code, 404)
            self.assertEqual(self.client.post(reverse('pedagogie:exercise_help', args=[exercise.pk]), self.help_data(exercise, 'hint')).status_code, 404)
            model.assert_not_called()

    def test_csrf_required_for_all_learning_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        exercise = self.exercise()
        for url in (self.urls('chapter_study'), self.urls('chapter_practice'), reverse('pedagogie:exercise_help', args=[exercise.pk])):
            self.assertEqual(client.post(url, {}).status_code, 403)

    def test_only_complete_valid_attempts_are_saved_and_open_answers_are_not_exact_matched(self):
        exercise = self.exercise()
        self.client.force_login(self.student)
        for answer in ('', 'invented option', 'a' * 5001):
            response = self.client.post(exercise.get_absolute_url(), {'reponse_0': answer})
            self.assertFalse(response.context.get('corrige', False))
        self.assertFalse(TentativeExercice.objects.exists())
        attempt = self.submit(exercise)
        self.assertEqual(attempt.resultats, [False])
        self.submit(exercise)
        self.assertEqual(TentativeExercice.objects.count(), 1)
        opened = self.exercise('ouverte')
        response = self.client.post(opened.get_absolute_url(), {'reponse_0': 'HTML organise le contenu.'})
        self.assertIsNone(response.context['score'])
        self.assertEqual(TentativeExercice.objects.filter(exercice=opened).get().resultats, [None])

    def test_attempt_history_and_open_correction_are_private(self):
        exercise = self.exercise('ouverte')
        self.client.force_login(self.student)
        attempt = self.submit(exercise, 'HTML structure une page.')
        url = reverse('pedagogie:exercise_help', args=[exercise.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(exercise.get_absolute_url() + f'?tentative={attempt.pk}').status_code, 404)
        with patch('pedagogie.learning_views.correct_open_answer') as model:
            self.assertEqual(self.client.post(url, self.help_data(exercise, 'correct', attempt=str(attempt.pk))).status_code, 404)
            model.assert_not_called()

    def test_open_correction_requires_submission_and_is_saved_and_cached(self):
        exercise = self.exercise('ouverte')
        self.client.force_login(self.student)
        url = reverse('pedagogie:exercise_help', args=[exercise.pk])
        self.assertEqual(self.client.post(url, self.help_data(exercise, 'correct')).status_code, 400)
        attempt = self.submit(exercise, 'HTML structure la page.')
        with patch('pedagogie.learning_views.correct_open_answer', return_value=self.feedback()) as model:
            for _ in range(2):
                response = self.client.post(url, self.help_data(exercise, 'correct', attempt=str(attempt.pk)))
                self.assertEqual(response.json()['correction']['score'], 1)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(model.call_args.args[-1], 'HTML structure la page.')
        attempt.refresh_from_db()
        self.assertIn('0', attempt.corrections)
        self.assertContains(self.client.get(exercise.get_absolute_url() + f'?tentative={attempt.pk}'), 'Ajoutez un exemple.')
        self.assertTrue(personal_weaknesses(self.student, self.course, self.chapter))
        exercise.question += ' Mise à jour'
        exercise.save()
        self.assertEqual(self.client.post(url, self.help_data(exercise, 'correct', attempt=str(attempt.pk))).status_code, 409)

    def test_rubric_limits_are_enforced_and_score_is_computed_by_server(self):
        self.assertEqual(parse_rubric('Définition | 2,5')[0]['maximum'], 2.5)
        for text in ('Pas de points', 'Critère | 0', 'Critère | 21', 'Critère | -1', '\n'.join(f'C{i} | 10' for i in range(11))):
            with self.assertRaises(ValidationError):
                parse_rubric(text)
        exercise = self.exercise('ouverte')
        question = {'question': exercise.question, 'bonne_reponse': 'HTML', 'bareme': exercise.bareme}
        data = {'criteres': [{'id': 'C1', 'points': 1.5, 'commentaire': 'Juste mais incomplet'}, {'id': 'C2', 'points': 0, 'commentaire': 'Absent'}],
                'corrects': ['Structure'], 'manquants': ['Exemple'], 'conseil': 'Précisez.'}
        with patch('pedagogie.ai.request_json', return_value=data):
            result = correct_open_answer(exercise, self.chapter, self.student, question, 'Une réponse')
        self.assertEqual(result['score'], 1.5)
        self.assertEqual(result['maximum'], 3)
        for invalid in (3, -1, True, float('nan')):
            data['criteres'][0]['points'] = invalid
            with patch('pedagogie.ai.request_json', return_value=data), self.assertRaises(AIError):
                correct_open_answer(exercise, self.chapter, self.student, question, 'Une réponse')
        data['criteres'] = [data['criteres'][1], data['criteres'][1]]
        with patch('pedagogie.ai.request_json', return_value=data), self.assertRaises(AIError):
            correct_open_answer(exercise, self.chapter, self.student, question, 'Une réponse')

    def test_teacher_can_define_first_and_additional_question_rubrics(self):
        data = {'titre': 'Question', 'cours': self.course.pk, 'chapitre_id': self.chapter['id'], 'type_exercice': 'ouverte', 'difficulte': 'moyen',
                'question': 'HTML ?', 'bonne_reponse': 'Structure', 'bareme': 'Définition | 2'}
        form = ExerciceForm(data, user=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().bareme, 'Définition | 2')
        row = QuestionQCMForm({'question': 'CSS ?', 'bonne_reponse': 'Présentation', 'bareme': 'Exemple | 1'}, type_exercice='ouverte')
        self.assertTrue(row.is_valid(), row.errors)
        row = QuestionQCMForm({'question': 'CSS ?', 'bonne_reponse': 'Présentation', 'bareme': 'Un barème sans points'}, type_exercice='ouverte')
        self.assertFalse(row.is_valid())
        self.assertIn('bareme', row.errors)

    def test_adaptive_practice_uses_only_current_users_latest_wrong_answers(self):
        exercise = self.exercise()
        self.client.force_login(self.student)
        url = self.urls('chapter_practice')
        self.submit(exercise)
        with patch('pedagogie.learning_views.generate_questions', return_value=(self.rows, False)) as model:
            response = self.client.post(url, {'action': 'generate', 'nombre': 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(model.call_args.kwargs['weaknesses'][0]['reponse_eleve'], 'CSS')
        self.assertEqual(Exercice.objects.count(), 1)
        self.assertEqual(EntrainementChapitre.objects.count(), 1)
        self.assertNotContains(response, 'HTML structure les pages web.')  # Explanations stay hidden before answering.
        practice = EntrainementChapitre.objects.get()
        response = self.client.post(url, {'action': 'answer', 'practice': practice.pk, 'reponse_0': 'HTML', 'reponse_1': 'HTML'})
        self.assertContains(response, 'Réponse attendue : CSS')
        practice.refresh_from_db()
        self.assertEqual(practice.resultats, [True, False])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {'action': 'answer', 'practice': practice.pk}).status_code, 404)
        self.assertEqual(personal_weaknesses(self.other, self.course, self.chapter), [])
        self.client.force_login(self.teacher)
        self.client.post(reverse('pedagogie:retake_permission', args=[exercise.tentatives.first().pk]), {'action': 'allow'})
        self.client.force_login(self.student)
        self.submit(exercise, 'HTML', number=2)
        weaknesses = personal_weaknesses(self.student, self.course, self.chapter)
        self.assertEqual([item['question'] for item in weaknesses], [self.rows[1]['question']])

    def test_first_practice_can_be_generated_without_attempts_or_teacher_exercises(self):
        from bs4 import BeautifulSoup
        self.client.force_login(self.student)
        url = self.urls('chapter_practice')
        with patch('pedagogie.learning_views.generate_questions', return_value=(self.rows, False)) as model:
            page = self.client.get(url)
            button = BeautifulSoup(page.content, 'html.parser').select_one('form[data-ai-wait] button')
            self.assertIsNotNone(button)
            self.assertFalse(button.has_attr('disabled'))
            model.assert_not_called()
            response = self.client.post(url, {'action': 'generate', 'nombre': 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(model.call_args.kwargs['weaknesses'], [])
        practice = EntrainementChapitre.objects.get(eleve=self.student)
        self.assertEqual(len(practice.questions), 2)
        self.assertFalse(Exercice.objects.exists())
        self.assertFalse(TentativeExercice.objects.exists())

    def test_personal_practice_errors_guide_next_generation_and_clear_when_corrected(self):
        self.client.force_login(self.student)
        url = self.urls('chapter_practice')
        with patch('pedagogie.learning_views.generate_questions', return_value=(self.rows, False)) as model:
            for _ in range(2):
                self.client.post(url, {'action': 'generate', 'nombre': 2})
                practice = EntrainementChapitre.objects.latest('pk')
                self.client.post(url, {'action': 'answer', 'practice': practice.pk, 'reponse_0': 'CSS', 'reponse_1': 'CSS'})
            weaknesses = personal_weaknesses(self.student, self.course, self.chapter)
            self.assertEqual(len(weaknesses), 1)
            self.assertEqual(weaknesses[0]['frequence_erreurs'], 2)
            self.assertEqual(personal_weaknesses(self.other, self.course, self.chapter), [])
            self.client.post(url, {'action': 'generate', 'nombre': 2})
            self.assertEqual(model.call_args.kwargs['weaknesses'][0]['question'], self.rows[0]['question'])
            practice = EntrainementChapitre.objects.latest('pk')
            self.client.post(url, {'action': 'answer', 'practice': practice.pk, 'reponse_0': 'HTML', 'reponse_1': 'CSS'})
        self.assertEqual(personal_weaknesses(self.student, self.course, self.chapter), [])

    def test_adaptive_failure_or_invalid_count_creates_no_practice(self):
        exercise = self.exercise()
        self.client.force_login(self.student)
        self.submit(exercise)
        url = self.urls('chapter_practice')
        with patch('pedagogie.learning_views.generate_questions', side_effect=AIError('Quota atteint')) as model:
            for count in (0, 6):
                self.client.post(url, {'action': 'generate', 'nombre': count})
            model.assert_not_called()
            self.assertContains(self.client.post(url, {'action': 'generate', 'nombre': 2}), 'Quota atteint')
        self.assertFalse(EntrainementChapitre.objects.exists())

    def test_missing_teacher_rubric_does_not_call_model(self):
        exercise = self.exercise('ouverte')
        with patch('pedagogie.ai.request_json') as model, self.assertRaises(AIError):
            correct_open_answer(exercise, self.chapter, self.student, {'question': 'Q', 'bonne_reponse': 'A', 'bareme': ''}, 'Réponse')
        model.assert_not_called()
