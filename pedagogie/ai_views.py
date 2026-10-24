import time
from uuid import uuid4, UUID

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .ai import AIError, ai_request_limit, generate_questions, answer_question, chapter_revision
from .forms import AIGenerateForm, AIExerciseTitleForm, AIPreviewFormSet
from .models import Exercice
from .visibility import visible_courses, visible_chapters, manages_course


class ChapterScopeMixin:
    def chapter_scope(self):
        course = get_object_or_404(visible_courses(self.request.user), pk=self.kwargs['pk'])
        chapter = next((c for c in visible_chapters(self.request.user, course) if c['id'] == str(self.kwargs['chapter_id'])), None)
        if chapter is None:
            raise Http404
        return course, chapter


class GenerateChapterExercisesView(PermissionRequiredMixin, ChapterScopeMixin, View):
    permission_required = 'pedagogie.add_exercice'
    template_name = 'pedagogie/ai_generate.html'

    def scope(self):
        course, chapter = self.chapter_scope()
        if not manages_course(self.request.user, course):
            raise PermissionDenied
        return course, chapter

    def page(self, course, chapter, **context):
        return render(self.request, self.template_name, {'cours': course, 'chapitre': chapter, **context})

    def get(self, request, *args, **kwargs):
        course, chapter = self.scope()
        return self.page(course, chapter, form=AIGenerateForm())

    def post(self, request, *args, **kwargs):
        course, chapter = self.scope()
        if request.POST.get('action') == 'save':
            return self.save_draft(course, chapter)
        form = AIGenerateForm(request.POST)
        if not form.is_valid():
            return self.page(course, chapter, form=form)
        try:
            with ai_request_limit(request.user):
                questions, truncated = generate_questions(course, chapter, request.user, form.cleaned_data['nombre'],
                    form.cleaned_data['type_exercice'], form.cleaned_data['difficulte'])
        except AIError as error:
            form.add_error(None, str(error))
            return self.page(course, chapter, form=form)
        identity = str(uuid4())
        drafts = request.session.get('pedagogie_ai_drafts', {})
        drafts = {key: value for key, value in drafts.items() if time.time() - value['created'] < 1800}
        while len(drafts) >= 3:
            del drafts[next(iter(drafts))]
        draft = {'course': course.pk, 'chapter': chapter['id'], 'revision': chapter_revision(course, chapter, request.user),
                 'created': time.time(), 'type': form.cleaned_data['type_exercice'], 'difficulty': form.cleaned_data['difficulte'],
                 'questions': questions, 'truncated': truncated}
        drafts[identity] = draft
        request.session['pedagogie_ai_drafts'] = drafts
        title = f'{dict(Exercice.TYPES)[draft["type"]]} — {chapter["titre"]}'[:200]
        return self.preview(course, chapter, identity, draft, AIExerciseTitleForm(initial={'titre': title}),
            AIPreviewFormSet(initial=questions, prefix='questions', form_kwargs={'type_exercice': draft['type']}))

    def preview(self, course, chapter, identity, draft, title_form, questions):
        return self.page(course, chapter, draft_id=identity, draft=draft, title_form=title_form, questions_formset=questions,
                         type_label=dict(Exercice.TYPES)[draft['type']], difficulty_label=dict(Exercice.DIFFICULTES)[draft['difficulty']])

    def save_draft(self, course, chapter):
        identity = self.request.POST.get('draft_id', '')
        try:
            UUID(identity)
        except (ValueError, TypeError):
            raise Http404 from None
        existing = Exercice.objects.filter(ai_generation_id=identity, cours=course, chapitre_id=chapter['id']).first()
        if existing:
            return redirect(existing)
        drafts = self.request.session.get('pedagogie_ai_drafts', {})
        draft = drafts.get(identity)
        if not draft or draft['course'] != course.pk or draft['chapter'] != chapter['id'] or time.time() - draft['created'] > 1800:
            messages.warning(self.request, 'Cet aperçu a expiré ou n’est plus disponible. Générez de nouvelles questions.')
            return redirect('pedagogie:ai_generate', pk=course.pk, chapter_id=chapter['id'])
        title_form = AIExerciseTitleForm(self.request.POST)
        questions = AIPreviewFormSet(self.request.POST, prefix='questions', initial=draft['questions'], form_kwargs={'type_exercice': draft['type']})
        title_valid, questions_valid = title_form.is_valid(), questions.is_valid()
        if draft['revision'] != chapter_revision(course, chapter, self.request.user):
            title_form.add_error(None, 'Le chapitre ou ses documents ont changé. Générez un nouvel aperçu avant d’enregistrer.')
            title_valid = False
        if not title_valid or not questions_valid:
            return self.preview(course, chapter, identity, draft, title_form, questions)
        rows = [{key: row[key] for key in ('question', 'propositions', 'bonne_reponse', 'explication', 'bareme')}
                for row in questions.cleaned_data if row and not row.get('DELETE')]
        first = rows[0]
        candidate = Exercice(titre=title_form.cleaned_data['titre'], cours=course, chapitre_id=chapter['id'],
            type_exercice=draft['type'], difficulte=draft['difficulty'], questions_supplementaires=rows[1:], **first)
        try:
            candidate.full_clean(exclude=['ai_generation_id'])
        except ValidationError:
            title_form.add_error(None, 'Vérifiez les questions et les bonnes réponses avant l’enregistrement.')
            return self.preview(course, chapter, identity, draft, title_form, questions)
        defaults = {name: getattr(candidate, name) for name in ('titre', 'cours', 'chapitre_id', 'type_exercice', 'difficulte',
                    'question', 'propositions', 'bonne_reponse', 'explication', 'bareme', 'questions_supplementaires')}
        with transaction.atomic():
            exercise, _ = Exercice.objects.get_or_create(ai_generation_id=identity, defaults=defaults)
        drafts.pop(identity, None)
        self.request.session['pedagogie_ai_drafts'] = drafts
        messages.success(self.request, 'L’exercice et ses explications ont été enregistrés dans ce chapitre.')
        return redirect(exercise)


class ChapterAssistantView(PermissionRequiredMixin, ChapterScopeMixin, View):
    permission_required = 'pedagogie.view_cours'

    def post(self, request, *args, **kwargs):
        course, chapter = self.chapter_scope()
        revision = chapter_revision(course, chapter, request.user)
        key = f'{course.pk}:{chapter["id"]}'
        conversations = request.session.get('pedagogie_ai_chats', {})
        conversation = conversations.get(key, {})
        history = conversation.get('history', []) if conversation.get('revision') == revision else []
        action = request.POST.get('action', 'ask')
        if action == 'reset':
            conversations.pop(key, None)
            request.session['pedagogie_ai_chats'] = conversations
            return JsonResponse({'history': []})
        if action == 'history':
            return JsonResponse({'history': history})
        question = request.POST.get('question', '').strip()
        if not question or len(question) > 1500:
            return JsonResponse({'error': 'Saisissez une question de 1 à 1 500 caractères.'}, status=400)
        try:
            with ai_request_limit(request.user):
                reply = answer_question(course, chapter, request.user, question, history)
        except AIError as error:
            return JsonResponse({'error': str(error)}, status=400)
        turn = {'question': question, **reply}
        if key not in conversations and len(conversations) >= 12:
            conversations.pop(next(iter(conversations)))
        conversations[key] = {'revision': revision, 'history': (history + [turn])[-6:]}
        request.session['pedagogie_ai_chats'] = conversations
        return JsonResponse(turn)
