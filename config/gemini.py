"""Shared, credential-safe Gemini REST client for first-party Django apps."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


def appel_gemini(prompt, json_mode=False):
    if not settings.GEMINI_API_KEY:
        raise ValueError('Gemini n’est pas configuré. Ajoutez GEMINI_API_KEY dans le fichier .env, puis redémarrez le serveur.')
    model = settings.GEMINI_MODEL
    if not re.fullmatch(r'[a-zA-Z0-9._-]+', model):
        raise ValueError('Configuration du modèle Gemini invalide.')
    generation_config = {'maxOutputTokens': 4096}
    if model.startswith('gemini-2.5-flash'):
        generation_config['thinkingConfig'] = {'thinkingBudget': 0}
    if json_mode:
        generation_config['responseMimeType'] = 'application/json'
    request = Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps({'contents': [{'parts': [{'text': prompt}]}],
                         'generationConfig': generation_config}).encode(),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': settings.GEMINI_API_KEY}, method='POST',
    )
    try:
        with urlopen(request, timeout=35) as response:
            result = json.load(response)
        candidate = result.get('candidates', [{}])[0]
        if candidate.get('finishReason') == 'MAX_TOKENS':
            raise ValueError('La réponse Gemini a été interrompue. Réduisez le contenu puis réessayez.')
        parts = candidate.get('content', {}).get('parts', [])
        text = '\n'.join(part.get('text', '') for part in parts if not part.get('thought')).strip()
        if not text:
            raise ValueError('Gemini n’a pas fourni de réponse. Réessayez plus tard.')
        if len(text) > 24000:
            raise ValueError('La réponse Gemini est trop longue. Réduisez le contenu puis réessayez.')
        return text
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError('La clé Gemini est refusée. Vérifiez sa configuration et ses autorisations.') from None
        if error.code == 429:
            raise ValueError('Quota Gemini atteint. Réessayez plus tard.') from None
        raise ValueError('Gemini est momentanément indisponible. Vérifiez le modèle puis réessayez.') from None
    except (URLError, TimeoutError, json.JSONDecodeError, IndexError, AttributeError, TypeError):
        raise ValueError('Impossible de récupérer une réponse Gemini. Réessayez plus tard.') from None
