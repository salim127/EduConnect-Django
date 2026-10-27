from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from accounts.roles import TEACHER, ADMIN
from .ai import AIError, generer_fiche_pedagogique, assistant_trouve_ressource, invalider_fiche
from .models import Ressource, Categorie


def _is_teacher_or_admin(user):
    """Vérifie si l'utilisateur est enseignant ou admin."""
    return user.is_superuser or user.groups.filter(name__in=[TEACHER, ADMIN]).exists()


class FichePedagogiqueView(LoginRequiredMixin, View):
    """
    POST /ressources/bibliotheque/<pk>/fiche-ia/
    Génère la fiche pédagogique IA — Enseignants et Admins uniquement.
    """

    def post(self, request, pk, *args, **kwargs):
        if not _is_teacher_or_admin(request.user):
            return JsonResponse(
                {'error': 'Réservé aux enseignants et administrateurs.'},
                status=403,
            )
        ressource = get_object_or_404(Ressource, pk=pk)
        try:
            fiche = generer_fiche_pedagogique(ressource, request.user)
        except AIError as e:
            return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'fiche': fiche})


class AssistantRessourceView(LoginRequiredMixin, View):
    """
    POST /ressources/bibliotheque/assistant-ia/
    L'IA recommande des ressources — accessible à tous les utilisateurs connectés.
    Filtre optionnel par catégorie (matière).
    """

    def post(self, request, *args, **kwargs):
        besoin = request.POST.get('besoin', '').strip()
        if not besoin or len(besoin) > 500:
            return JsonResponse(
                {'error': 'Décrivez votre besoin (1 à 500 caractères).'},
                status=400,
            )

        # Filtre par catégorie si l'utilisateur choisit une matière
        cat_id = request.POST.get('categorie', '').strip()
        ressources = Ressource.objects.select_related('categorie').all()
        if cat_id:
            try:
                ressources = ressources.filter(categorie__id=int(cat_id))
            except (ValueError, TypeError):
                pass

        if not ressources.exists():
            return JsonResponse(
                {'error': 'Aucune ressource disponible dans cette matière pour l\'instant.'},
                status=400,
            )

        try:
            result = assistant_trouve_ressource(besoin, ressources, request.user)
        except AIError as e:
            return JsonResponse({'error': str(e)}, status=400)

        # Enrichir les recommandations avec les détails des ressources
        ids = [r['ressource_id'] for r in result.get('recommandations', [])]
        ressources_map = {r.pk: r for r in Ressource.objects.filter(pk__in=ids).select_related('categorie')}
        for rec in result.get('recommandations', []):
            r = ressources_map.get(rec['ressource_id'])
            if r:
                rec['titre'] = r.titre
                rec['type'] = r.get_type_ressource_display()
                rec['categorie'] = r.categorie.nom
                rec['info'] = r.info
                rec['url'] = r.url
                rec['detail_url'] = r.get_absolute_url()
            else:
                rec['titre'] = '?'

        # Ajouter les catégories disponibles pour le filtre
        result['categories'] = list(
            Categorie.objects.values('id', 'nom').order_by('nom')
        )
        return JsonResponse(result)

