"""Périmètres partagés par les vues et les choix de formulaires."""
from accounts.roles import LEARNER, TEACHER, is_admin


def is_manager(user):
    return user.is_authenticated and user.is_active and (
        is_admin(user) or user.groups.filter(name=TEACHER).exists()
    )


def visible_sessions(user, queryset):
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.groups.filter(name=TEACHER).exists():
        return queryset.filter(coach=user)
    if user.groups.filter(name=LEARNER).exists():
        return queryset.filter(etudiant=user)
    return queryset.none()


def managed_sessions(user, queryset):
    return visible_sessions(user, queryset) if is_manager(user) else queryset.none()
