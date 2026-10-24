from io import BytesIO
import json
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.roles import ensure_system_roles, TEACHER, LEARNER
from .ai import AIError, generate_questions, answer_question, request_json, ai_request_limit
from .models import Cours, Exercice


class ChapterAITests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_system_roles()
        self.teacher = get_user_model().objects.create_user(username='teacher')
        self.teacher.groups.add(Group.objects.get(name=TEACHER))
        self.student = get_user_model().objects.create_user(username='student')
        self.student.groups.add(Group.objects.get(name=LEARNER))
        self.other = get_user_model().objects.create_user(username='other')
        self.other.groups.add(Group.objects.get(name=TEACHER))
        self.chapter = {'id': str(uuid4()), 'titre': 'Le Web', 'contenu': '<p>HTML structure les pages web.</p><p>CSS définit les couleurs et les polices.</p>'}
        self.course = Cours.objects.create(titre='Web', enseignant=self.teacher, contenu='Introduction', chapitres=[self.chapter])
        self.generate_url = reverse('pedagogie:ai_generate', args=[self.course.pk, self.chapter['id']])
        self.chat_url = reverse('pedagogie:chapter_assistant', args=[self.course.pk, self.chapter['id']])
        self.rows = [{'question': 'Quel langage structure une page ?', 'propositions': 'HTML\nCSS\nSQL\nPython', 'bonne_reponse': 'HTML', 'explication': 'HTML structure les pages web.'},
                     {'question': 'Quel langage définit les couleurs ?', 'propositions': 'HTML\nCSS\nSQL\nPython', 'bonne_reponse': 'CSS', 'explication': 'CSS définit les couleurs et les polices.'}]
        self.client.force_login(self.teacher)

    def generate(self):
        with patch('pedagogie.ai_views.generate_questions', return_value=(self.rows, False)):
            return self.client.post(self.generate_url, {'nombre': 2, 'type_exercice': 'qcm', 'difficulte': 'moyen'})

    def save_payload(self, response):
        data = {'action': 'save', 'draft_id': response.context['draft_id'], 'titre': 'Quiz du Web',
                'questions-TOTAL_FORMS': '2', 'questions-INITIAL_FORMS': '2'}
        for index, row in enumerate(self.rows):
            data.update({f'questions-{index}-{key}': value for key, value in row.items()})
        return data

    def test_preview_does_not_publish_and_teacher_can_edit_then_save(self):
        response = self.generate()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Valider et enregistrer')
        self.assertFalse(Exercice.objects.exists())
        payload = self.save_payload(response)
        payload['questions-0-question'] = 'Question modifiée par le professeur'
        self.assertEqual(self.client.post(self.generate_url, payload).status_code, 302)
        exercise = Exercice.objects.get()
        self.assertEqual(exercise.question, payload['questions-0-question'])
        self.assertEqual(exercise.chapitre_id, self.chapter['id'])
        self.assertEqual(exercise.explication, self.rows[0]['explication'])
        self.assertEqual(exercise.questions_supplementaires[0]['explication'], self.rows[1]['explication'])
        self.assertEqual(self.client.post(self.generate_url, payload).status_code, 302)
        self.assertEqual(Exercice.objects.count(), 1)

    def test_invalid_preview_does_not_save(self):
        response = self.generate()
        payload = self.save_payload(response)
        payload['questions-0-bonne_reponse'] = 'Wrong option'
        response = self.client.post(self.generate_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['questions_formset'].errors)
        self.assertFalse(Exercice.objects.exists())

    def test_stale_chapter_draft_is_rejected(self):
        response = self.generate()
        payload = self.save_payload(response)
        self.chapter['contenu'] = 'Updated course material'
        self.course.chapitres = [self.chapter]
        self.course.save()
        response = self.client.post(self.generate_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['title_form'].non_field_errors())
        self.assertFalse(Exercice.objects.exists())

    def test_only_course_owner_or_admin_can_generate(self):
        for user in (self.student, self.other):
            self.client.force_login(user)
            with patch('pedagogie.ai_views.generate_questions') as call:
                self.assertEqual(self.client.post(self.generate_url, {'nombre': 2, 'type_exercice': 'qcm', 'difficulte': 'moyen'}).status_code, 403)
                call.assert_not_called()

    def test_hidden_chapter_has_no_student_chat_access(self):
        self.chapter['masque'] = True
        self.course.chapitres = [self.chapter]
        self.course.save()
        self.client.force_login(self.student)
        with patch('pedagogie.ai_views.answer_question') as call:
            self.assertEqual(self.client.post(self.chat_url, {'question': 'HTML ?'}).status_code, 404)
            call.assert_not_called()

    def test_chat_history_is_session_scoped_and_resettable(self):
        self.client.force_login(self.student)
        answer = {'answer': 'HTML structure le contenu.', 'citations': [{'label': 'Le Web', 'quote': 'HTML structure les pages web.', 'url': ''}], 'truncated': False}
        with patch('pedagogie.ai_views.answer_question', return_value=answer) as call:
            response = self.client.post(self.chat_url, {'question': 'À quoi sert HTML ?', 'historique': 'fake privileged history'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(call.call_args.args[-1], [])
        history = self.client.post(self.chat_url, {'action': 'history'}).json()['history']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['answer'], answer['answer'])
        other_session = Client()
        other_session.force_login(self.student)
        self.assertEqual(other_session.post(self.chat_url, {'action': 'history'}).json()['history'], [])
        self.assertEqual(self.client.post(self.chat_url, {'action': 'reset'}).json()['history'], [])
        self.assertEqual(self.client.post(self.chat_url, {'action': 'history'}).json()['history'], [])

    def test_updated_sources_clear_old_chat_context(self):
        self.client.force_login(self.student)
        with patch('pedagogie.ai_views.answer_question', return_value={'answer': 'Old answer', 'citations': [], 'truncated': False}):
            self.client.post(self.chat_url, {'question': 'HTML ?'})
        self.chapter['contenu'] = 'New text'
        self.course.chapitres = [self.chapter]
        self.course.save()
        self.assertEqual(self.client.post(self.chat_url, {'action': 'history'}).json()['history'], [])

    def test_csrf_and_input_limits_apply_to_chat(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student)
        self.assertEqual(client.post(self.chat_url, {'question': 'HTML ?'}).status_code, 403)
        for question in ('', 'a' * 1501):
            self.assertEqual(self.client.post(self.chat_url, {'question': question}).status_code, 400)

    def test_citations_are_verified_and_answer_keys_not_sent(self):
        Exercice.objects.create(cours=self.course, chapitre_id=self.chapter['id'], titre='Secret', question='Question', type_exercice='ouverte', bonne_reponse='SECRET_CORRECTION')
        self.client.force_login(self.student)
        data = {'dans_chapitre': True, 'reponse': 'HTML structure les pages.', 'citations': [{'source_id': 'S1', 'extrait': 'HTML structure les pages web.'}]}
        with patch('pedagogie.ai.request_json', return_value=data) as model:
            answer = answer_question(self.course, self.chapter, self.student, 'HTML ?', [])
            self.assertEqual(len(answer['citations']), 1)
            self.assertNotIn('SECRET_CORRECTION', json.dumps(model.call_args.args[1]))
        data['citations'][0]['extrait'] = 'Invented passage not in the chapter'
        with patch('pedagogie.ai.request_json', return_value=data):
            with self.assertRaises(AIError):
                answer_question(self.course, self.chapter, self.student, 'HTML ?', [])

    def test_out_of_scope_reply_is_not_presented_as_grounded(self):
        with patch('pedagogie.ai.request_json', return_value={'dans_chapitre': False, 'reponse': 'Unsupported answer', 'citations': []}):
            answer = answer_question(self.course, self.chapter, self.student, 'Autre sujet ?', [])
        self.assertNotIn('Unsupported answer', answer['answer'])
        self.assertEqual(answer['citations'], [])

    def test_bad_generated_questions_are_rejected(self):
        rows = [{'question': 'Q', 'propositions': ['A', 'B', 'C', 'D'], 'bonne_reponse': 'Z', 'explication': 'E'}]
        with patch('pedagogie.ai.request_json', return_value={'questions': rows}):
            with self.assertRaises(AIError):
                generate_questions(self.course, self.chapter, self.teacher, 1, 'qcm', 'facile')
        self.assertFalse(Exercice.objects.exists())

    def test_model_failure_keeps_generation_form_and_no_records(self):
        with patch('pedagogie.ai_views.generate_questions', side_effect=AIError('Quota atteint')):
            response = self.client.post(self.generate_url, {'nombre': 2, 'type_exercice': 'qcm', 'difficulte': 'moyen'})
        self.assertContains(response, 'Quota atteint')
        self.assertFalse(Exercice.objects.exists())

    def test_student_only_sees_explanations_after_answering(self):
        exercise = Exercice.objects.create(cours=self.course, titre='Quiz', question='HTML ?', type_exercice='vf', bonne_reponse='Vrai', explication='EXPLANATION_SECRET')
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(exercise.get_absolute_url()), 'EXPLANATION_SECRET')
        self.assertContains(self.client.post(exercise.get_absolute_url(), {'reponse_0': 'Vrai'}), 'EXPLANATION_SECRET')

    @override_settings(GEMINI_API_KEY='test-private-key', PEDAGOGIE_GEMINI_MODEL='gemini-3.1-flash-lite')
    def test_transport_keeps_key_in_header_and_handles_quotas(self):
        fake = BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"ok":true}'}]}}]}).encode())
        with patch('pedagogie.ai.urlopen', return_value=fake) as call:
            self.assertEqual(request_json('System', {'sources': []}, {'type': 'object'}), {'ok': True})
            request = call.call_args.args[0]
            self.assertNotIn('test-private-key', request.full_url)
            self.assertEqual(request.get_header('X-goog-api-key'), 'test-private-key')
            payload = json.loads(request.data)
            self.assertIn('systemInstruction', payload)
            self.assertIn('responseJsonSchema', payload['generationConfig'])
        with patch('pedagogie.ai.urlopen', side_effect=HTTPError('https://example.com', 429, 'Quota', {}, None)):
            with self.assertRaisesRegex(AIError, 'quota'):
                request_json('System', {}, {})

    def test_parallel_ai_requests_are_limited(self):
        with ai_request_limit(self.teacher):
            with self.assertRaises(AIError):
                with ai_request_limit(self.teacher):
                    pass
