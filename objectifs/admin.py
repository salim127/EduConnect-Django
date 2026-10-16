from django.contrib import admin
from .forms import ObjectifForm
from .models import ObjectifApprentissage, TacheApprentissage

@admin.register(ObjectifApprentissage)
class ObjectifAdmin(admin.ModelAdmin):
    form = ObjectifForm
    readonly_fields = ['proprietaire']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.proprietaire = request.user
        super().save_model(request, obj, form, change)

    list_display = ['titre', 'proprietaire', 'apprenant', 'priorite', 'date_echeance']
    search_fields = ['titre', 'description']
    list_filter = ['priorite']

@admin.register(TacheApprentissage)
class TacheAdmin(admin.ModelAdmin):
    readonly_fields = ['statut', 'reponse', 'date_soumission']
    list_display = ['titre', 'objectif', 'statut', 'duree_estimee', 'date_echeance']
    search_fields = ['titre']
    list_filter = ['statut']
