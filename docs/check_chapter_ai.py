"""Two small live API smoke checks using synthetic public lesson text; creates no exercises."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from pedagogie.ai import generate_questions, answer_question, AIError
from pedagogie.models import Cours
from uuid import uuid4

course = Cours.objects.select_related('enseignant').first()
if not course:
    raise SystemExit('Aucun cours disponible pour le contrôle.')
chapter = {'id': str(uuid4()), 'titre': 'Notions du Web', 'contenu': '<p>HTML définit la structure d’une page web : titres, paragraphes et liens.</p><p>CSS définit la présentation visuelle : couleurs, polices et disposition.</p><p>JavaScript ajoute des interactions, par exemple un bouton qui affiche un message.</p>'}
try:
    questions, _ = generate_questions(course, chapter, course.enseignant, 2, 'qcm', 'moyen')
    print('Questions valides:', len(questions))
    reply = answer_question(course, chapter, course.enseignant, 'Quelle est la différence entre HTML et CSS ?', [])
    print('Réponse reçue:', bool(reply['answer']), 'Citations vérifiées:', len(reply['citations']))
except AIError as error:
    print('Test Gemini:', str(error))
    raise SystemExit(1)
