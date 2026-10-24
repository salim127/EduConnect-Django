"""Check the configured Gemini key without printing the key or response content."""
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings

request = Request('https://generativelanguage.googleapis.com/v1beta/models/' + settings.PEDAGOGIE_GEMINI_MODEL,
                  headers={'x-goog-api-key': settings.GEMINI_API_KEY})
try:
    with urlopen(request, timeout=15) as response:
        print('Gemini model access HTTP:', response.status)
except HTTPError as error:
    try:
        details = json.load(error).get('error', {})
        status = details.get('status', '')
        reasons = [d.get('reason', '') for d in details.get('details', []) if isinstance(d, dict)]
        print('Gemini access HTTP:', error.code, 'status:', status, 'reasons:', ','.join(reasons))
    except (ValueError, AttributeError):
        print('Gemini access HTTP:', error.code)
except (URLError, TimeoutError):
    print('Gemini network unavailable')
