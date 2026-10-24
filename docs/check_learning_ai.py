"""Four small live API checks on synthetic text. No database writes."""
import os
from pathlib import Path
import sys
from uuid import uuid4
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from pedagogie.ai import study_material, correct_open_answer, generate_questions, AIError
from pedagogie.models import Cours, Exercice

course = Cours(titre='Cours fictif pour le test Gemini')
user = None
chapter = {'id': str(uuid4()), 'titre': 'Notions du Web', 'contenu': '<p>HTML définit la structure d’une page web : titres, paragraphes et liens.</p><p>CSS définit la présentation visuelle : couleurs, polices et disposition.</p><p>JavaScript ajoute des interactions, par exemple un bouton qui affiche un message.</p>'}
sources = [{'id': 'S1', 'label': 'Notions du Web', 'url': '', 'text': 'HTML définit la structure d’une page web : titres, paragraphes et liens.'},
           {'id': 'S2', 'label': 'Notions du Web', 'url': '', 'text': 'CSS définit la présentation visuelle : couleurs, polices et disposition.'},
           {'id': 'S3', 'label': 'Notions du Web', 'url': '', 'text': 'JavaScript ajoute des interactions, par exemple un bouton qui affiche un message.'}]
exercise = Exercice(cours=course, type_exercice='ouverte', chapitre_id=chapter['id'], question='Expliquez les rôles de HTML et CSS avec un exemple.',
                    bonne_reponse='HTML structure le contenu, par exemple un titre. CSS définit son apparence, par exemple une couleur.',
                    bareme='Rôle de HTML | 2\nRôle de CSS | 2\nExemple | 1')
question = {key: getattr(exercise, key) for key in ('question', 'bonne_reponse', 'bareme')}
try:
    # A literal fixture replaces document access. This script never queries the database.
    fixture = patch('pedagogie.ai.chapter_sources', return_value=(sources, False))
    fixture.start()
    summary = study_material(course, chapter, user, 'summary')
    print('Résumé :', len(summary['notions']), 'notions,', len(summary['citations']), 'citations vérifiées', flush=True)
    cards = study_material(course, chapter, user, 'cards')
    print('Fiches :', len(cards['cartes']), 'cartes avec citations vérifiées', flush=True)
    feedback = correct_open_answer(exercise, chapter, user, question, 'HTML structure le contenu. CSS choisit les couleurs et les polices.')
    print('Correction :', len(feedback['criteres']), 'critères respectés, score', feedback['score'], '/', feedback['maximum'], flush=True)
    questions, _ = generate_questions(course, chapter, user, 2, 'qcm', 'moyen',
        weaknesses=[{'question': 'À quoi sert CSS ?', 'reponse_eleve': 'À structurer la page', 'frequence_erreurs': 2}])
    print('Entraînement adapté :', len(questions), 'QCM valides', flush=True)
except AIError as error:
    raise SystemExit('Contrôle Gemini : ' + str(error))
finally:
    fixture.stop()
