from django.contrib import admin

from .models import (BookingRequest, CoachAvailability, CoachAvailabilityException,
                     CoachingAction, ConseilPedagogique, SessionCoaching)


@admin.register(SessionCoaching)
class SessionCoachingAdmin(admin.ModelAdmin):
    list_display = ['titre', 'date_session', 'duree', 'statut', 'coach', 'etudiant']
    list_filter = ['statut', 'date_session']
    search_fields = ['titre', 'coach__username', 'coach__first_name', 'coach__last_name', 'etudiant__username', 'etudiant__first_name', 'etudiant__last_name']
    ordering = ['date_session', 'pk']
    readonly_fields = ['id']
    list_select_related = ['coach', 'etudiant']


@admin.register(ConseilPedagogique)
class ConseilPedagogiqueAdmin(admin.ModelAdmin):
    list_display = ['titre', 'type_conseil', 'session', 'date_creation']
    list_filter = ['type_conseil', 'date_creation']
    search_fields = ['titre', 'description', 'session__titre']
    ordering = ['-date_creation', '-pk']
    readonly_fields = ['id', 'date_creation']
    list_select_related = ['session']


@admin.register(CoachAvailability)
class CoachAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['coach', 'weekday', 'start_time', 'end_time', 'is_active']
    list_filter = ['weekday', 'is_active']
    list_select_related = ['coach']


@admin.register(CoachAvailabilityException)
class CoachAvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ['coach', 'start_datetime', 'end_datetime', 'reason']
    list_select_related = ['coach']


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ['topic', 'coach', 'etudiant', 'requested_start', 'duration', 'status']
    list_filter = ['status']
    list_select_related = ['coach', 'etudiant', 'session']


@admin.register(CoachingAction)
class CoachingActionAdmin(admin.ModelAdmin):
    list_display = ['title', 'session', 'etudiant', 'priority', 'status', 'due_date']
    list_filter = ['status', 'priority', 'action_type']
    list_select_related = ['session', 'etudiant']
