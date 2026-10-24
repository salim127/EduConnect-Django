from django.db.models import Q
from accounts.roles import is_admin
from .models import Cours, Exercice


def manages_course(user, course):
    return user.has_perm('pedagogie.change_cours') and (is_admin(user) or course.enseignant_id == user.pk)


def visible_courses(user):
    courses = Cours.objects.all()
    if is_admin(user) and user.has_perm('pedagogie.change_cours'):
        return courses
    allowed = Q(masque=False)
    if user.has_perm('pedagogie.change_cours'):
        allowed |= Q(enseignant=user)
    return courses.filter(allowed)


def visible_chapters(user, course):
    return course.chapitres if manages_course(user, course) else [c for c in course.chapitres if not c.get('masque', False)]


def visible_exercises(user, queryset=None):
    qs = queryset if queryset is not None else Exercice.objects.all()
    courses = visible_courses(user)
    qs = qs.filter(cours__in=courses)
    for course in courses.only('pk', 'enseignant_id', 'chapitres'):
        if manages_course(user, course):
            continue
        hidden = [c['id'] for c in course.chapitres if c.get('masque', False)]
        if hidden:
            qs = qs.exclude(cours_id=course.pk, chapitre_id__in=hidden)
    return qs


def can_read_support(user, support):
    if manages_course(user, support.cours):
        return True
    return not support.masque and not support.cours.masque and (
        not support.chapitre_id or support.chapitre_id in [c['id'] for c in visible_chapters(user, support.cours)])
