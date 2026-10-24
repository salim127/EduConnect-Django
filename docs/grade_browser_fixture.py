"""Create or remove only isolated grading browser-test records. No AI/network calls."""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.urls import reverse
from accounts.roles import ensure_system_roles, TEACHER, LEARNER
from pedagogie.models import Cours, Exercice

path = Path(tempfile.gettempdir()) / 'hub-grade-browser-fixture.json'
if sys.argv[1:] == ['cleanup']:
    data = json.loads(path.read_text())
    with transaction.atomic():
        course = Cours.objects.get(pk=data['course_id'], titre=data['title'], enseignant__username=data['teacher']['username'])
        if not data['teacher']['username'].startswith('grades_test_') or not data['student']['username'].startswith('grades_test_'):
            raise SystemExit('Fixture identity mismatch')
        course.delete()
        get_user_model().objects.filter(username__in=[data['teacher']['username'], data['student']['username']]).delete()
    path.unlink()
    print('Isolated browser fixture removed.')
else:
    if path.exists():
        raise SystemExit('Remove the previous test fixture before creating another one.')
    ensure_system_roles()
    identity = uuid4().hex[:10]
    data = {'title': 'Test notes navigateur ' + identity}
    with transaction.atomic():
        users = {}
        for key, role in [('teacher', TEACHER), ('student', LEARNER)]:
            password = secrets.token_urlsafe(24)
            username = f'grades_test_{identity}_{key}'
            user = get_user_model().objects.create_user(username=username, password=password)
            user.groups.add(Group.objects.get(name=role))
            users[key] = user
            data[key] = {'username': username, 'password': password}
        chapter = {'id': str(uuid4()), 'titre': 'Test', 'contenu': '<p>HTML structure le contenu.</p>'}
        course = Cours.objects.create(titre=data['title'], enseignant=users['teacher'], contenu='Test', chapitres=[chapter])
        exercise = Exercice.objects.create(cours=course, chapitre_id=chapter['id'], titre='QCM de test', question='Structure ?',
            propositions='HTML\nCSS', bonne_reponse='HTML', questions_supplementaires=[{'question': 'Présentation ?', 'propositions': 'HTML\nCSS', 'bonne_reponse': 'CSS'}])
        opened = Exercice.objects.create(cours=course, chapitre_id=chapter['id'], titre='Question ouverte de test', type_exercice='ouverte',
            question='Définir HTML', bonne_reponse='Il structure le contenu.', bareme='Définition | 2')
        data.update(course_id=course.pk, exercise_url=exercise.get_absolute_url(), open_url=opened.get_absolute_url(),
            teacher_url=reverse('pedagogie:gradebook') + f'?cours={course.pk}', student_url=reverse('pedagogie:my_grades'),
            logout_url=reverse('accounts:logout'))
        path.write_text(json.dumps(data), encoding='utf-8')
    print('Isolated browser fixture ready; credentials remain in the temporary file.')
