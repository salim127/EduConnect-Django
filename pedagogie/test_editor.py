from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from . import tests as base
from django.test import TestCase
from .models import Cours
from .richtext import clean_content


class ChapterDocumentTests(TestCase):
    setUp = base.CourseImportTests.setUp
    word = base.CourseImportTests.word
    def pdf(self):
        from pypdf import PdfWriter
        stream = BytesIO()
        document = PdfWriter()
        document.add_blank_page(width=100, height=100)
        document.write(stream)
        return SimpleUploadedFile('Chapter.pdf', stream.getvalue(), content_type='application/pdf')

    def test_chapter_documents_survive_edit_and_are_scoped(self):
        course = Cours.objects.create(titre='Course', enseignant=self.teacher)
        payload = {'titre': 'Course', 'description': 'Description', 'matiere': 'English', 'niveau': 'debutant', 'contenu': 'Intro',
            'chapitres-TOTAL_FORMS': '2', 'chapitres-INITIAL_FORMS': '0',
            'chapitres-0-titre': 'Documents', 'chapitres-0-contenu': '',
            'chapitres-0-fichiers': [self.pdf(), self.word()],
            'chapitres-1-titre': 'Other', 'chapitres-1-contenu': 'Other body'}
        response = self.client.post(reverse('pedagogie:cours_update', args=[course.pk]), payload)
        self.assertEqual(response.status_code, 302)
        course.refresh_from_db()
        first, second = [c['id'] for c in course.chapitres]
        self.assertEqual(course.supports.filter(chapitre_id=first).count(), 2)
        response = self.client.get(course.get_absolute_url(), {'chapitre': first})
        self.assertContains(response, 'Chapter.pdf')
        response = self.client.get(course.get_absolute_url(), {'chapitre': second})
        self.assertNotContains(response, 'Chapter.pdf')
        response = self.client.get(reverse('pedagogie:cours_update', args=[course.pk]))
        self.assertContains(response, 'Chapter.pdf')
        payload.pop('chapitres-0-fichiers')
        payload.update({'chapitres-INITIAL_FORMS': '2', 'chapitres-0-id': first, 'chapitres-1-id': second})
        self.assertEqual(self.client.post(reverse('pedagogie:cours_update', args=[course.pk]), payload).status_code, 302)
        self.assertEqual(course.supports.filter(chapitre_id=first).count(), 2)
        payload['chapitres-0-DELETE'] = 'on'
        self.client.post(reverse('pedagogie:cours_update', args=[course.pk]), payload)
        self.assertEqual(course.supports.filter(chapitre_id='').count(), 2)

    def test_invalid_chapter_pdf_does_not_save_anything(self):
        course = Cours.objects.create(titre='Course', enseignant=self.teacher)
        response = self.client.post(reverse('pedagogie:cours_update', args=[course.pk]), {
            'titre': 'Modified', 'description': 'Description', 'matiere': 'English', 'niveau': 'debutant', 'contenu': 'Intro',
            'chapitres-TOTAL_FORMS': '1', 'chapitres-INITIAL_FORMS': '0',
            'chapitres-0-titre': 'Bad file', 'chapitres-0-contenu': 'Text',
            'chapitres-0-fichiers': SimpleUploadedFile('bad.pdf', b'invalid')})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['chapitres_formset'].errors)
        course.refresh_from_db()
        self.assertEqual(course.titre, 'Course')
        self.assertFalse(course.supports.exists())

    def test_hugerte_formatting_is_saved_and_rendered_safely(self):
        content = '<p style="text-align:center;font-family:Arial;font-size:24pt"><strong>Title</strong></p><table style="width:100%"><tbody><tr><td colspan="2" style="background-color:#ffaa00">Cell</td></tr></tbody></table><a href="https://example.com">Link</a>'
        safe = clean_content(content)
        for part in ('text-align:center', 'font-family:Arial', 'font-size:24pt', '<table', 'colspan="2"', 'background-color:#ffaa00', 'href="https://example.com"'):
            self.assertIn(part, safe)
        for bad in ('javascript:alert(1)', 'java\nscript:alert(1)', 'data:text/html,hello'):
            safe = clean_content(f'<a href="{bad}" onclick="alert(1)">Test</a><img src="{bad}" onerror="bad()">')
            self.assertNotIn('href=', safe)
            self.assertNotIn('src=', safe)
            self.assertNotIn('onclick', safe)
        response = self.client.post(reverse('pedagogie:cours_create'), {
            'titre': 'Formatted', 'contenu': content, 'description': 'Description', 'matiere': 'English', 'niveau': 'debutant',
            'chapitres-TOTAL_FORMS': '0', 'chapitres-INITIAL_FORMS': '0'})
        self.assertEqual(response.status_code, 302)
        course = Cours.objects.get(titre='Formatted')
        self.assertIn('font-size:24pt', course.contenu)
        self.assertIn('colspan="2"', course.contenu)
        self.assertContains(self.client.get(course.get_absolute_url()), '<strong>Title</strong>', html=True)
        self.assertContains(self.client.get(reverse('pedagogie:cours_update', args=[course.pk])), 'vendor/hugerte/hugerte.min.js')
