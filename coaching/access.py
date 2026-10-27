"""Périmètres partagés par les vues et les choix de formulaires."""
from accounts.roles import LEARNER, TEACHER, is_admin

from .models import BookingRequest, CoachAvailability, CoachAvailabilityException, CoachingAction


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


def managed_availabilities(user, queryset=None):
    queryset = queryset if queryset is not None else CoachAvailability.objects.all()
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.groups.filter(name=TEACHER).exists():
        return queryset.filter(coach=user)
    return queryset.none()


def managed_exceptions(user, queryset=None):
    queryset = queryset if queryset is not None else CoachAvailabilityException.objects.all()
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.groups.filter(name=TEACHER).exists():
        return queryset.filter(coach=user)
    return queryset.none()


def visible_bookings(user, queryset=None):
    queryset = queryset if queryset is not None else BookingRequest.objects.all()
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.groups.filter(name=TEACHER).exists():
        return queryset.filter(coach=user)
    if user.groups.filter(name=LEARNER).exists():
        return queryset.filter(etudiant=user)
    return queryset.none()


def visible_actions(user, queryset=None):
    queryset = queryset if queryset is not None else CoachingAction.objects.all()
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.groups.filter(name=TEACHER).exists():
        return queryset.filter(session__coach=user)
    if user.groups.filter(name=LEARNER).exists():
        return queryset.filter(etudiant=user)
    return queryset.none()
