from django import forms
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from .ai import (AIError, ai_request_limit, chapter_revision, study_material,
                 correct_open_answer, generate_questions)
from .ai_views import ChapterScopeMixin
from .learning import exercise_questions, exercise_revision, exercise_chapter, personal_weaknesses
from .models import EntrainementChapitre, TentativeExercice
from .visibility import visible_exercises


class ChapterStudyView(PermissionRequiredMixin, ChapterScopeMixin, View):
    permission_required = 'pedagogie.view_cours'

    def page(self, error=''):
        course, chapter = self.chapter_scope()
        revision = chapter_revision(course, chapter, self.request.user)
        key = f'{course.pk}:{chapter["id"]}'
        stored = self.request.session.get('pedagogie_study', {}).get(key, {})
        material = stored.get('material', {}) if stored.get('revision') == revision else {}
        return render(self.request, 'pedagogie/chapter_study.html',
                      {'cours': course, 'chapitre': chapter, 'material': material, 'error': error})

    def get(self, request, *args, **kwargs):
        return self.page()

    def post(self, request, *args, **kwargs):
        course, chapter = self.chapter_scope()
        action = request.POST.get('action')
        if action not in ('summary', 'cards'):
            return self.page('Choisissez un résumé ou des fiches de révision.')
        revision = chapter_revision(course, chapter, request.user)
        key = f'{course.pk}:{chapter["id"]}'
        stored = request.session.get('pedagogie_study', {})
        current = stored.get(key, {})
        material = current.get('material', {}) if current.get('revision') == revision else {}
        if action not in material:
            try:
                with ai_request_limit(request.user):
                    material[action] = study_material(course, chapter, request.user, action)
            except AIError as error:
                return self.page(str(error))
            if key not in stored and len(stored) >= 8:
                stored.pop(next(iter(stored)))
            stored[key] = {'revision': revision, 'material': material}
            request.session['pedagogie_study'] = stored
        return self.page()


class ExerciseHelpView(PermissionRequiredMixin, View):
    permission_required = 'pedagogie.view_exercice'

    def post(self, request, pk):
        exercise = get_object_or_404(visible_exercises(request.user).select_related('cours'), pk=pk)
        try:
            index = int(request.POST.get('index', ''))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Question invalide.'}, status=400)
        rows = exercise_questions(exercise)
        if not 0 <= index < len(rows):
            return JsonResponse({'error': 'Question invalide.'}, status=400)
        revision = exercise_revision(exercise)
        if request.POST.get('revision') != revision:
            return JsonResponse({'error': 'L’exercice a changé. Rechargez la page.'}, status=409)
        chapter = exercise_chapter(exercise)
        action = request.POST.get('action')
        try:
            if action == 'correct' and exercise.type_exercice == 'ouverte':
                identity = request.POST.get('attempt', '')
                if not identity.isdigit():
                    return JsonResponse({'error': 'Soumettez votre réponse avant de demander une correction.'}, status=400)
                attempt = get_object_or_404(TentativeExercice, pk=identity, exercice=exercise, eleve=request.user)
                if attempt.revision != revision:
                    return JsonResponse({'error': 'Cette tentative correspond à une ancienne version de l’exercice.'}, status=409)
                feedback = attempt.corrections.get(str(index))
                if feedback is None:
                    with ai_request_limit(request.user):
                        feedback = correct_open_answer(exercise, chapter, request.user, rows[index], attempt.reponses[index])
                    # Save only this question's feedback without losing a previously corrected question.
                    from django.db import transaction
                    with transaction.atomic():
                        current = TentativeExercice.objects.select_for_update().get(pk=attempt.pk)
                        current.corrections[str(index)] = feedback
                        current.save(update_fields=['corrections'])
                return JsonResponse({'correction': feedback})
            return JsonResponse({'error': 'Cette aide n’est pas disponible pour cette question.'}, status=400)
        except (AIError, ValidationError) as error:
            message = ' '.join(error.messages) if isinstance(error, ValidationError) else str(error)
            return JsonResponse({'error': message}, status=400)


class PracticeForm(forms.Form):
    nombre = forms.IntegerField(label='Nombre de questions', min_value=1, max_value=5, initial=3,
                                widget=forms.NumberInput(attrs={'class': 'form-control'}))


class ChapterPracticeView(PermissionRequiredMixin, ChapterScopeMixin, View):
    permission_required = 'pedagogie.view_exercice'

    def page(self, course, chapter, practice=None, error='', form=None):
        revision = chapter_revision(course, chapter, self.request.user)
        if practice is None:
            practice = EntrainementChapitre.objects.filter(eleve=self.request.user, cours=course,
                chapitre_id=chapter['id'], revision=revision).first()
        rows = []
        if practice:
            for index, question in enumerate(practice.questions):
                answer = practice.reponses[index] if practice.reponses else ''
                rows.append({**question, 'propositions': question['propositions'].splitlines(), 'reponse': answer,
                             'juste': practice.resultats[index] if practice.resultats else None})
        return render(self.request, 'pedagogie/chapter_practice.html', {'cours': course, 'chapitre': chapter,
            'practice': practice, 'rows': rows, 'error': error, 'form': form if form is not None else PracticeForm(),
            'weaknesses': personal_weaknesses(self.request.user, course, chapter)})

    def get(self, request, *args, **kwargs):
        return self.page(*self.chapter_scope())

    def post(self, request, *args, **kwargs):
        course, chapter = self.chapter_scope()
        revision = chapter_revision(course, chapter, request.user)
        action = request.POST.get('action')
        if action == 'answer':
            identity = request.POST.get('practice', '')
            if not identity.isdigit():
                raise Http404
            practice = get_object_or_404(EntrainementChapitre, pk=identity, eleve=request.user, cours=course, chapitre_id=chapter['id'])
            if practice.revision != revision:
                return self.page(course, chapter, error='Le chapitre a changé. Générez un nouvel entraînement.')
            if not practice.reponses:
                answers = [request.POST.get(f'reponse_{i}', '').strip() for i in range(len(practice.questions))]
                if any(answer not in q['propositions'].splitlines() for answer, q in zip(answers, practice.questions)):
                    return self.page(course, chapter, practice, error='Choisissez une réponse pour chaque question.')
                practice.reponses = answers
                practice.resultats = [answer == q['bonne_reponse'] for answer, q in zip(answers, practice.questions)]
                practice.save(update_fields=['reponses', 'resultats'])
            return self.page(course, chapter, practice)
        form = PracticeForm(request.POST)
        if action != 'generate' or not form.is_valid():
            return self.page(course, chapter, form=form, error='Choisissez entre 1 et 5 questions.')
        weaknesses = personal_weaknesses(request.user, course, chapter)
        try:
            with ai_request_limit(request.user):
                rows, truncated = generate_questions(course, chapter, request.user, form.cleaned_data['nombre'],
                    'qcm', 'moyen', weaknesses=weaknesses)
        except AIError as error:
            return self.page(course, chapter, error=str(error), form=form)
        practice = EntrainementChapitre.objects.create(eleve=request.user, cours=course, chapitre_id=chapter['id'],
            revision=revision, questions=rows, contenu_tronque=truncated)
        return self.page(course, chapter, practice)
