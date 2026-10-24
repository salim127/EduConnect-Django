from django.contrib import admin

from .models import ConseilPedagogique, SessionCoaching


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
