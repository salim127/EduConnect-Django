"""Question snapshots, teacher rubrics and personal learning history."""
import hashlib
import json
import re

from django.core.exceptions import ValidationError

from .models import TentativeExercice, EntrainementChapitre
from .visibility import visible_exercises


def parse_rubric(text):
    criteria = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'\s*(.{1,180}?)\s*\|\s*(\d{1,2}(?:[.,]\d)?)\s*', line)
        if not match:
            raise ValidationError('Utilisez une ligne par critère : Description | points. Exemple : Définition correcte | 2')
        points = float(match[2].replace(',', '.'))
        if not 0 < points <= 20:
            raise ValidationError('Chaque critère doit valoir entre 0,1 et 20 points.')
        criteria.append({'id': f'C{len(criteria) + 1}', 'critere': match[1].strip(), 'maximum': points})
    if len(criteria) > 10 or sum(c['maximum'] for c in criteria) > 100:
        raise ValidationError('Le barème accepte au maximum 10 critères et 100 points au total.')
    return criteria


def exercise_questions(exercise):
    first = {key: getattr(exercise, key) for key in ('question', 'propositions', 'bonne_reponse', 'explication', 'bareme')}
    return [first] + [dict(row, bareme=row.get('bareme', '')) for row in exercise.questions_supplementaires]


def exercise_revision(exercise):
    chapter = next((c for c in exercise.cours.chapitres if c['id'] == exercise.chapitre_id), None)
    documents = list(exercise.cours.supports.filter(chapitre_id=exercise.chapitre_id).values('pk', 'fichier', 'masque'))
    data = {'type': exercise.type_exercice, 'chapter': chapter, 'documents': documents, 'introduction': exercise.cours.contenu,
            'questions': exercise_questions(exercise)}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def exercise_chapter(exercise):
    if exercise.chapitre_id:
        return next(c for c in exercise.cours.chapitres if c['id'] == exercise.chapitre_id)
    return {'id': '', 'titre': exercise.cours.titre, 'contenu': exercise.cours.contenu}


def personal_weaknesses(user, course, chapter):
    exercises = visible_exercises(user).filter(cours=course, chapitre_id=chapter['id'])
    attempts = TentativeExercice.objects.filter(eleve=user, exercice__in=exercises).select_related('exercice__cours')[:200]
    latest, revisions, frequencies = {}, {}, {}
    for attempt in attempts:
        identity = attempt.exercice_id
        if identity not in revisions:
            revisions[identity] = exercise_revision(attempt.exercice)
        if attempt.revision != revisions[identity]:
            continue
        if identity not in latest and len(latest) >= 20:
            continue
        latest.setdefault(identity, attempt)
        for index, result in enumerate(attempt.resultats):
            feedback = attempt.corrections.get(str(index))
            if result is False or (feedback and feedback['score'] < feedback['maximum']):
                key = (identity, index)
                frequencies[key] = frequencies.get(key, 0) + 1
    weaknesses = []
    for identity, attempt in latest.items():
        rows = exercise_questions(attempt.exercice)
        for index, result in enumerate(attempt.resultats):
            feedback = attempt.corrections.get(str(index))
            wrong = result is False or (feedback and feedback['score'] < feedback['maximum'])
            if wrong and index < len(rows):
                weaknesses.append({'question': rows[index]['question'][:1500],
                    'reponse_eleve': attempt.reponses[index][:1500],
                    'frequence_erreurs': frequencies.get((identity, index), 1),
                    'points_a_revoir': feedback.get('manquants', []) if feedback else []})
    # A student can start with a personal practice even if the teacher has not
    # published exercises yet. These answers also inform subsequent generations.
    from .ai import chapter_revision
    practice_latest, practice_counts = {}, {}
    practices = EntrainementChapitre.objects.filter(eleve=user, cours=course, chapitre_id=chapter['id'],
        revision=chapter_revision(course, chapter, user)).exclude(resultats=[])[:20]
    for practice in practices:
        for question, answer, correct in zip(practice.questions, practice.reponses, practice.resultats):
            key = ' '.join(question['question'].split()).casefold()
            practice_latest.setdefault(key, (question, answer, correct))
            if correct is False:
                practice_counts[key] = practice_counts.get(key, 0) + 1
    for key, (question, answer, correct) in practice_latest.items():
        if correct is False:
            weaknesses.append({'question': question['question'][:1500], 'reponse_eleve': answer[:1500],
                'frequence_erreurs': practice_counts[key], 'points_a_revoir': []})
    return sorted(weaknesses, key=lambda item: item['frequence_erreurs'], reverse=True)[:15]
