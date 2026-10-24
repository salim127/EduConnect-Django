from collections import defaultdict

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.roles import is_admin
from config.forms import BootstrapFormMixin
from .grading import active_mark, average, ai_suggested_mark
from .learning import exercise_questions, exercise_revision
from .models import Cours, TentativeExercice, ParticipationExercice
from .visibility import manages_course, visible_exercises


def teacher_courses(user):
    return Cours.objects.all() if is_admin(user) else Cours.objects.filter(enseignant=user)


class GradebookView(PermissionRequiredMixin, View):
    permission_required = 'pedagogie.change_exercice'

    def get(self, request):
        courses = teacher_courses(request.user).order_by('titre')
        attempts = TentativeExercice.objects.filter(exercice__cours__in=courses)
        students = get_user_model().objects.filter(pk__in=attempts.values('eleve_id')).order_by('last_name', 'first_name', 'username')
        selected = request.GET.get('cours', '')
        if selected:
            if not selected.isdigit():
                raise Http404
            course = get_object_or_404(courses, pk=selected)
            attempts = attempts.filter(exercice__cours=course)
        student = request.GET.get('eleve', '')
        if student:
            if not student.isdigit():
                raise Http404
            attempts = attempts.filter(eleve_id=student)
        records, summaries = mark_records(attempts)
        page = Paginator(records, 20).get_page(request.GET.get('page'))
        return render(request, 'pedagogie/gradebook.html', {'records': page.object_list, 'page_obj': page, 'summaries': summaries,
            'courses': courses, 'students': students, 'selected_course': selected, 'selected_student': student})


class MyGradesView(PermissionRequiredMixin, View):
    permission_required = 'pedagogie.view_exercice'

    def get(self, request):
        records, summaries = mark_records(TentativeExercice.objects.filter(eleve=request.user))
        visible = set(visible_exercises(request.user).values_list('pk', flat=True))
        for row in records:
            row['can_open'] = row['latest'].exercice_id in visible
        page = Paginator(records, 20).get_page(request.GET.get('page'))
        return render(request, 'pedagogie/my_grades.html', {'records': page.object_list, 'page_obj': page, 'summaries': summaries,
            'overall_average': average([row['mark'] for row in records])})


def mark_records(queryset):
    groups = defaultdict(list)
    for attempt in queryset.select_related('exercice__cours', 'eleve', 'validee_par'):
        groups[(attempt.eleve_id, attempt.exercice_id)].append(attempt)
    states = {(s.eleve_id, s.exercice_id): s for s in ParticipationExercice.objects.filter(
        eleve_id__in={key[0] for key in groups}, exercice_id__in={key[1] for key in groups})}
    records, student_courses = [], {}
    for key, history in groups.items():
        latest, mark = history[0], active_mark(history)
        state = states.get(key)
        records.append({'latest': latest, 'mark': mark, 'history': history,
            'retake_available': state is not None and state.tentatives_utilisees < state.tentatives_autorisees})
        course_key = (latest.eleve_id, latest.exercice.cours_id)
        summary = student_courses.setdefault(course_key, {'eleve': latest.eleve, 'cours': latest.exercice.cours, 'marks': [], 'submitted': 0, 'pending': 0})
        summary['submitted'] += 1
        summary['pending'] += latest.note is None
        if mark:
            summary['marks'].append(mark)
    for summary in student_courses.values():
        summary['average'] = average(summary['marks'])
        summary['graded'] = len(summary['marks'])
    return records, list(student_courses.values())


class TeacherMarkForm(BootstrapFormMixin, forms.Form):
    note = forms.DecimalField(label='Note définitive sur 20', min_value=0, max_value=20, max_digits=4, decimal_places=2)
    commentaire = forms.CharField(label='Commentaire du professeur', required=False, max_length=3000, widget=forms.Textarea(attrs={'rows': 3}))
    version = forms.CharField(required=False, widget=forms.HiddenInput())


class AttemptResultView(PermissionRequiredMixin, View):
    permission_required = 'pedagogie.view_exercice'

    def scope(self, pk):
        attempt = get_object_or_404(TentativeExercice.objects.select_related('exercice__cours', 'eleve', 'validee_par'), pk=pk)
        teacher = self.request.user.has_perm('pedagogie.change_exercice') and manages_course(self.request.user, attempt.exercice.cours)
        if not teacher and (attempt.eleve_id != self.request.user.pk or not visible_exercises(self.request.user).filter(pk=attempt.exercice_id).exists()):
            raise Http404
        return attempt, teacher

    def page(self, attempt, teacher, form=None):
        questions = attempt.enonce.get('questions')
        if not questions and attempt.revision == exercise_revision(attempt.exercice):
            questions = exercise_questions(attempt.exercice)
        rows = []
        for index, answer in enumerate(attempt.reponses):
            question = questions[index] if questions and index < len(questions) else {'question': f'Question {index + 1} — ancienne version'}
            rows.append({**question, 'reponse': answer, 'juste': attempt.resultats[index], 'correction': attempt.corrections.get(str(index))})
        kind = attempt.enonce.get('type', attempt.exercice.type_exercice)
        if form is None:
            form = TeacherMarkForm(initial={'note': attempt.note if attempt.note is not None else ai_suggested_mark(attempt),
                'commentaire': attempt.commentaire_prof, 'version': attempt.date_validation.isoformat() if attempt.date_validation else ''})
        return render(self.request, 'pedagogie/attempt_result.html', {'attempt': attempt, 'teacher': teacher,
            'rows': rows, 'open_question': kind == 'ouverte', 'form': form, 'ai_suggestion': ai_suggested_mark(attempt)})

    def get(self, request, pk):
        return self.page(*self.scope(pk))

    def post(self, request, pk):
        attempt, teacher = self.scope(pk)
        if not teacher:
            raise PermissionDenied
        if attempt.enonce.get('type', attempt.exercice.type_exercice) != 'ouverte':
            raise PermissionDenied('Le QCM est noté automatiquement.')
        form = TeacherMarkForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                current = TentativeExercice.objects.select_for_update().get(pk=attempt.pk)
                version = current.date_validation.isoformat() if current.date_validation else ''
                if form.cleaned_data['version'] != version:
                    form.add_error(None, 'Cette note a été modifiée entre-temps. Rechargez la page.')
                else:
                    current.note = form.cleaned_data['note']
                    current.commentaire_prof = form.cleaned_data['commentaire']
                    current.validee_par = request.user
                    current.date_validation = timezone.now()
                    current.save(update_fields=['note', 'commentaire_prof', 'validee_par', 'date_validation'])
                    messages.success(request, 'La note est enregistrée et la moyenne a été recalculée.')
                    return redirect('pedagogie:attempt_result', pk=pk)
        return self.page(attempt, teacher, form)


class RetakePermissionView(PermissionRequiredMixin, View):
    permission_required = 'pedagogie.change_exercice'

    def post(self, request, pk):
        attempt = get_object_or_404(TentativeExercice.objects.select_related('exercice__cours'), pk=pk,
                                   exercice__cours__in=teacher_courses(request.user))
        if not manages_course(request.user, attempt.exercice.cours):
            raise PermissionDenied
        with transaction.atomic():
            state = get_object_or_404(ParticipationExercice.objects.select_for_update(), exercice=attempt.exercice, eleve_id=attempt.eleve_id)
            latest = TentativeExercice.objects.filter(eleve_id=attempt.eleve_id, exercice_id=attempt.exercice_id).first()
            action = request.POST.get('action')
            if latest.pk != attempt.pk:
                messages.warning(request, 'Une nouvelle tentative existe déjà. Rechargez les résultats.')
            elif action == 'allow':
                ParticipationExercice.objects.filter(pk=state.pk, tentatives_autorisees=state.tentatives_utilisees).update(
                    tentatives_autorisees=state.tentatives_utilisees + 1)
                messages.success(request, 'Une nouvelle tentative est autorisée pour cet élève et cet exercice.')
            elif action == 'revoke':
                ParticipationExercice.objects.filter(pk=state.pk, tentatives_utilisees=state.tentatives_utilisees).update(
                    tentatives_autorisees=state.tentatives_utilisees)
                messages.success(request, 'L’autorisation de nouvelle tentative a été retirée.')
            else:
                raise Http404
        return redirect('pedagogie:gradebook')
