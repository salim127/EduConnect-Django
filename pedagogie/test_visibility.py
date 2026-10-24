from pathlib import Path
import tempfile
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document

from accounts.roles import ensure_system_roles, TEACHER, LEARNER
from .models import Cours, Exercice, SupportCours


class VisibilityTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = override_settings(MEDIA_ROOT=self.directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        ensure_system_roles()
        self.teacher = get_user_model().objects.create_user(username='teacher')
        self.teacher.groups.add(Group.objects.get(name=TEACHER))
        self.other = get_user_model().objects.create_user(username='other')
        self.other.groups.add(Group.objects.get(name=TEACHER))
        self.student = get_user_model().objects.create_user(username='student')
        self.student.groups.add(Group.objects.get(name=LEARNER))
        self.chapter_id = str(uuid4())
        self.course = Cours.objects.create(titre='My course', enseignant=self.teacher, contenu='Introduction',
            chapitres=[{'id': self.chapter_id, 'titre': 'Secret chapter', 'contenu': '<p>Secret body</p>'}])
        self.exercise = Exercice.objects.create(cours=self.course, chapitre_id=self.chapter_id,
            titre='Secret exercise', question='Question', type_exercice='vf', bonne_reponse='Vrai')
        self.support = SupportCours.objects.create(cours=self.course, chapitre_id=self.chapter_id,
            nom='Document.pdf', fichier=SimpleUploadedFile('Document.pdf', b'PDF content'))
        self.client.force_login(self.teacher)

    def payload(self):
        return {'titre': 'My course', 'description': 'Description', 'matiere': 'English', 'niveau': 'debutant', 'contenu': 'Introduction',
            'chapitres-TOTAL_FORMS': '1', 'chapitres-INITIAL_FORMS': '1', 'chapitres-0-id': self.chapter_id,
            'chapitres-0-titre': 'Secret chapter', 'chapitres-0-contenu': '<p>Secret body</p>'}

    def update(self, payload):
        return self.client.post(reverse('pedagogie:cours_update', args=[self.course.pk]), payload)

    def test_hide_and_show_document_protects_direct_download(self):
        payload = self.payload()
        payload[f'support_action_{self.support.pk}'] = 'hide'
        self.assertEqual(self.update(payload).status_code, 302)
        self.support.refresh_from_db()
        self.assertTrue(self.support.masque)
        self.assertTrue(Path(self.support.fichier.path).exists())
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(self.course.get_absolute_url(), {'chapitre': self.chapter_id}), 'Document.pdf')
        self.assertEqual(self.client.get(reverse('pedagogie:support_download', args=[self.support.pk])).status_code, 404)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('pedagogie:support_download', args=[self.support.pk])).status_code, 404)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('pedagogie:support_download', args=[self.support.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()
        payload[f'support_action_{self.support.pk}'] = 'show'
        self.assertEqual(self.update(payload).status_code, 302)
        self.client.force_login(self.student)
        response = self.client.get(reverse('pedagogie:support_download', args=[self.support.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_delete_document_removes_record_and_stored_file(self):
        payload = self.payload()
        payload[f'support_action_{self.support.pk}'] = 'delete'
        path = Path(self.support.fichier.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.update(payload).status_code, 302)
        self.assertFalse(SupportCours.objects.filter(pk=self.support.pk).exists())
        self.assertFalse(path.exists())
        self.assertTrue(Cours.objects.filter(pk=self.course.pk).exists())

    def test_invalid_form_does_not_delete_documents(self):
        payload = self.payload()
        payload['titre'] = ''
        payload[f'support_action_{self.support.pk}'] = 'delete'
        self.assertEqual(self.update(payload).status_code, 200)
        self.assertTrue(SupportCours.objects.filter(pk=self.support.pk).exists())
        self.assertTrue(Path(self.support.fichier.path).exists())

    def test_foreign_documents_cannot_be_modified(self):
        foreign = Cours.objects.create(titre='Other course', enseignant=self.other)
        document = SupportCours.objects.create(cours=foreign, nom='Other.pdf', fichier=SimpleUploadedFile('Other.pdf', b'PDF'))
        payload = self.payload()
        payload[f'support_action_{document.pk}'] = 'delete'
        self.assertEqual(self.update(payload).status_code, 200)
        self.assertTrue(SupportCours.objects.filter(pk=document.pk).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.update(self.payload()).status_code, 403)

    def test_hidden_chapter_is_excluded_from_reading_exercises_and_exports(self):
        payload = self.payload()
        payload['chapitres-0-masque'] = 'on'
        self.assertEqual(self.update(payload).status_code, 302)
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(self.course.get_absolute_url()), 'Secret chapter')
        self.assertEqual(self.client.get(self.course.get_absolute_url(), {'chapitre': self.chapter_id}).status_code, 404)
        self.assertEqual(self.client.get(self.exercise.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('pedagogie:exercice_list')), 'Secret exercise')
        self.assertEqual(self.client.get(reverse('pedagogie:support_download', args=[self.support.pk])).status_code, 404)
        response = self.client.get(reverse('pedagogie:cours_export', args=[self.course.pk, 'docx']))
        from io import BytesIO
        document = Document(BytesIO(b''.join(response.streaming_content)))
        self.assertNotIn('Secret', '\n'.join(p.text for p in document.paragraphs))
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(self.course.get_absolute_url(), {'chapitre': self.chapter_id}), 'Secret chapter')
        payload['chapitres-0-masque'] = ''
        self.assertEqual(self.update(payload).status_code, 302)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(self.course.get_absolute_url(), {'chapitre': self.chapter_id}), 'Secret body')

    def test_course_can_be_hidden_without_losing_it(self):
        payload = self.payload()
        payload['masque'] = 'on'
        self.assertEqual(self.update(payload).status_code, 302)
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('pedagogie:cours_list')), 'My course')
        self.assertEqual(self.client.get(self.course.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.exercise.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse('pedagogie:cours_export', args=[self.course.pk, 'pdf'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('pedagogie:support_download', args=[self.support.pk])).status_code, 404)
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('pedagogie:cours_list')), 'My course')
        self.assertEqual(self.client.get(self.course.get_absolute_url()).status_code, 200)

    def test_deleting_course_also_deletes_its_uploaded_files(self):
        file_path = Path(self.support.fichier.path)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('pedagogie:cours_delete', args=[self.course.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Cours.objects.filter(pk=self.course.pk).exists())
        self.assertFalse(file_path.exists())
