"""Fonctions IA pour le module Ressources (Gemini)."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


class AIError(ValueError):
    pass


def _ai_request_limit(user):
    """Limite : 1 requête simultanée + 30 requêtes/heure par utilisateur."""
    key = f'ressources-ai-busy:{user.pk}'
    if not cache.add(key, True, timeout=45):
        raise AIError('Une demande IA est déjà en cours. Patientez quelques secondes.')
    bucket = f'ressources-ai-hour:{user.pk}'
    cache.add(bucket, 0, timeout=3600)
    if cache.incr(bucket) > 30:
        cache.delete(key)
        raise AIError('Limite de 30 demandes IA/heure atteinte. Réessayez plus tard.')
    return key


def _call_gemini(instruction, prompt, schema=None):
    """Appelle l'API Gemini et retourne le texte ou le JSON parsé."""
    if not settings.GEMINI_API_KEY:
        raise AIError('La clé Gemini doit être configurée sur le serveur.')
    model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash')
    if not re.fullmatch(r'[a-zA-Z0-9._-]+', model):
        raise AIError('Le modèle Gemini configuré est invalide.')

    gen_config = {'maxOutputTokens': 4096, 'temperature': 0.4}
    if schema:
        gen_config.update({'responseMimeType': 'application/json', 'responseJsonSchema': schema})
    else:
        gen_config['responseMimeType'] = 'text/plain'

    body = {
        'systemInstruction': {'parts': [{'text': instruction}]},
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': gen_config,
    }
    req = Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': settings.GEMINI_API_KEY},
        method='POST',
    )
    try:
        with urlopen(req, timeout=60) as resp:
            result = json.load(resp)
        candidate = result.get('candidates', [{}])[0]
        text = ''.join(
            part.get('text', '')
            for part in candidate.get('content', {}).get('parts', [])
            if not part.get('thought')
        )
        if not text:
            raise AIError("L'IA n'a pas fourni de réponse. Réessayez.")
        return json.loads(text) if schema else text
    except HTTPError as e:
        if e.code in (400, 401, 403):
            raise AIError('Clé Gemini invalide ou non autorisée.') from None
        if e.code == 429:
            raise AIError('Quota Gemini atteint. Réessayez plus tard.') from None
        if e.code == 404:
            raise AIError('Modèle Gemini introuvable. Vérifiez la configuration.') from None
        raise AIError('Gemini est surchargé en ce moment (trop de demandes). Réessayez dans 1-2 minutes.') from None
    except (URLError, TimeoutError):
        raise AIError('Gemini ne répond pas. Vérifiez la connexion.') from None
    except (json.JSONDecodeError, KeyError, IndexError, AttributeError, TypeError):
        raise AIError('La réponse de Gemini est invalide.') from None


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fiche Pédagogique IA (Enseignant / Admin)
# ─────────────────────────────────────────────────────────────────────────────

FICHE_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'objectifs': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'public_cible': {'type': 'STRING'},
        'prerequis': {'type': 'STRING'},
        'duree_estimee': {'type': 'STRING'},
        'comment_utiliser': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'conseils': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
        'ressources_complementaires': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
    },
    'required': ['objectifs', 'public_cible', 'prerequis', 'duree_estimee', 'comment_utiliser', 'conseils'],
}

FICHE_INSTRUCTION = (
    "Tu es un expert en ingénierie pédagogique pour une plateforme éducative. "
    "Tu génères des fiches pédagogiques détaillées et pratiques en français. "
    "Sois précis, concret et adapté au contexte scolaire ou universitaire."
)


def generer_fiche_pedagogique(ressource, user):
    """Génère une fiche pédagogique complète pour une ressource donnée."""
    cache_key = f'ressources-fiche:{ressource.pk}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    limit_key = _ai_request_limit(user)
    try:
        prompt = (
            f"Génère une fiche pédagogique complète pour la ressource suivante :\n"
            f"- Titre : {ressource.titre}\n"
            f"- Type : {ressource.get_type_ressource_display()}\n"
            f"- Catégorie : {ressource.categorie.nom}\n"
            f"- Information : {ressource.info or 'non précisée'}\n\n"
            f"La fiche doit être utile pour un enseignant qui veut intégrer cette ressource dans son cours."
        )
        result = _call_gemini(FICHE_INSTRUCTION, prompt, FICHE_SCHEMA)
        # Cache 24h pour éviter de re-générer à chaque visite
        cache.set(cache_key, result, timeout=86400)
        return result
    finally:
        cache.delete(limit_key)


def invalider_fiche(ressource_pk):
    """Invalide le cache de la fiche quand la ressource est modifiée."""
    cache.delete(f'ressources-fiche:{ressource_pk}')


# ─────────────────────────────────────────────────────────────────────────────
# 2. Assistant "Trouve-moi une ressource" (Élève & Enseignant)
# ─────────────────────────────────────────────────────────────────────────────

ASSISTANT_STUDENT_INSTRUCTION = (
    "Tu es un assistant pédagogique bienveillant sur une plateforme éducative. "
    "Tu aides les élèves et étudiants à trouver les meilleures ressources selon leurs besoins d'apprentissage. "
    "Réponds en français de manière chaleureuse, motivante et encourageante. "
    "Tu dois UNIQUEMENT recommander des ressources de la liste fournie (ne pas inventer). "
    "Si aucune ressource ne correspond, dis-le gentiment et suggère de chercher autrement."
)

ASSISTANT_TEACHER_INSTRUCTION = (
    "Tu es un conseiller pédagogique expert sur une plateforme éducative. "
    "Tu aides les enseignants et formateurs à trouver les meilleures ressources pour préparer leurs cours, "
    "illustrer leurs séances ou fournir des exercices et supports complémentaires à leurs étudiants. "
    "Réponds en français de manière professionnelle, claire et structurée. "
    "Tu dois UNIQUEMENT recommander des ressources de la liste fournie (ne pas inventer). "
    "Si aucune ressource ne correspond, mentionne-le et propose une alternative."
)

ASSISTANT_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'message': {'type': 'STRING'},
        'recommandations': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'ressource_id': {'type': 'INTEGER'},
                    'explication': {'type': 'STRING'},
                },
                'required': ['ressource_id', 'explication'],
            },
        },
        'conseil': {'type': 'STRING'},
    },
    'required': ['message', 'recommandations'],
}


def assistant_trouve_ressource(besoin, ressources_disponibles, user):
    """
    L'IA analyse le besoin (étudiant ou enseignant) et recommande des ressources.
    ressources_disponibles : queryset ou liste de Ressource
    """
    limit_key = _ai_request_limit(user)
    try:
        is_teacher = (
            user.is_superuser or
            user.groups.filter(name__in=['Enseignant / Coach', 'Administrateur']).exists() or
            user.has_perm('ressources.change_ressource')
        )
        instruction = ASSISTANT_TEACHER_INSTRUCTION if is_teacher else ASSISTANT_STUDENT_INSTRUCTION
        role_context = (
            "Un enseignant prépare un cours ou cherche des supports pédagogiques avec cette demande"
            if is_teacher else
            "Un élève / apprenant exprime ce besoin d'apprentissage ou de révision"
        )

        catalogue = [
            {
                'id': r.pk,
                'titre': r.titre,
                'type': r.get_type_ressource_display(),
                'categorie': r.categorie.nom,
                'info': r.info,
            }
            for r in ressources_disponibles
        ]

        prompt = (
            f"{role_context} : \"{besoin}\"\n\n"
            f"Voici le catalogue des ressources disponibles (JSON) :\n"
            f"{json.dumps(catalogue, ensure_ascii=False, indent=2)}\n\n"
            f"Recommande les 1 à 3 ressources les plus adaptées. "
            f"Utilise uniquement les ressources de cette liste (via leur id). "
            f"Explique brièvement pourquoi chaque ressource est pertinente pour cette demande."
        )
        return _call_gemini(instruction, prompt, ASSISTANT_SCHEMA)
    finally:
        cache.delete(limit_key)
