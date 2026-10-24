"""Official exercise submissions, saved marks and equal-weight course averages."""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .learning import exercise_questions, exercise_revision
from .models import Exercice, ParticipationExercice, TentativeExercice


class SubmissionError(ValueError):
    pass


def on_twenty(points, maximum):
    return (Decimal(str(points)) * 20 / Decimal(str(maximum))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def save_submission(user, exercise, answers, revision, number):
    """Consume exactly one allowed slot, even for double submissions or stale tabs."""
    with transaction.atomic():
        exercise = Exercice.objects.select_for_update().select_related('cours').get(pk=exercise.pk)
        if revision != exercise_revision(exercise):
            raise SubmissionError('L’exercice a changé. Rechargez la page avant de répondre.')
        state, _ = ParticipationExercice.objects.get_or_create(eleve=user, exercice=exercise)
        expected = state.tentatives_utilisees + 1
        if number != expected or state.tentatives_utilisees >= state.tentatives_autorisees:
            raise SubmissionError('Votre réponse est déjà enregistrée. Seul le professeur peut autoriser une nouvelle tentative.')
        questions = exercise_questions(exercise)
        if len(answers) != len(questions) or any(not answer or len(answer) > 5000 for answer in answers):
            raise SubmissionError('Répondez à toutes les questions (5 000 caractères maximum par réponse).')
        if exercise.type_exercice != 'ouverte':
            for answer, question in zip(answers, questions):
                choices = ['Vrai', 'Faux'] if exercise.type_exercice == 'vf' else [p.strip() for p in question['propositions'].splitlines() if p.strip()]
                if answer not in choices:
                    raise SubmissionError('Choisissez une des propositions de chaque question.')
        consumed = ParticipationExercice.objects.filter(pk=state.pk, tentatives_utilisees=expected - 1,
            tentatives_autorisees__gte=expected).update(tentatives_utilisees=F('tentatives_utilisees') + 1)
        if not consumed:
            raise SubmissionError('Cette tentative a déjà été soumise. Rechargez la page.')
        results = [None if exercise.type_exercice == 'ouverte' else answer.casefold() == question['bonne_reponse'].casefold()
                   for answer, question in zip(answers, questions)]
        points = sum(result is True for result in results) if exercise.type_exercice != 'ouverte' else None
        return TentativeExercice.objects.create(eleve=user, exercice=exercise, revision=revision, numero=expected,
            reponses=answers, resultats=results, enonce={'titre': exercise.titre, 'type': exercise.type_exercice, 'questions': questions},
            points_obtenus=points, points_possibles=len(questions) if points is not None else None,
            note=on_twenty(points, len(questions)) if points is not None else None,
            date_validation=timezone.now() if points is not None else None)


def active_mark(attempts):
    """Newest confirmed mark for one student/exercise; pending work never becomes zero."""
    return next((attempt for attempt in attempts if attempt.note is not None), None)


def average(marks):
    values = [mark.note for mark in marks if mark is not None and mark.note is not None]
    return (sum(values) / len(values)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if values else None


def ai_suggested_mark(attempt):
    if not attempt.enonce or attempt.enonce.get('type') != 'ouverte':
        return None
    if len(attempt.corrections) != len(attempt.reponses):
        return None
    rows = [attempt.corrections.get(str(i)) for i in range(len(attempt.reponses))]
    if not all(row and row.get('maximum', 0) > 0 for row in rows):
        return None
    return on_twenty(sum(Decimal(str(row['score'])) for row in rows), sum(Decimal(str(row['maximum'])) for row in rows))
