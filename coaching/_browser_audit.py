"""Temporary browser audit runner using synthetic data and a separate SQLite file."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.conf import settings

ARTIFACTS = Path(tempfile.mkdtemp(prefix='educonnect-coaching-browser-'))
settings.DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(ARTIFACTS / 'audit.sqlite3')}
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
settings.DEBUG = True
settings.GEMINI_API_KEY = ''
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
from accounts.roles import ADMIN, TEACHER, LEARNER, ensure_system_roles
from coaching.models import SessionCoaching, ConseilPedagogique, CoachAvailability, CoachAvailabilityException, BookingRequest, CoachingAction
from playwright.sync_api import sync_playwright

call_command('migrate', verbosity=0)
ensure_system_roles()
users = {}
for role, label in [('coach', TEACHER), ('learner', LEARNER), ('admin', ADMIN), ('othercoach', TEACHER), ('otherlearner', LEARNER)]:
    user = get_user_model().objects.create_user(username=f'audit-{role}', first_name=role.capitalize(), last_name='Démonstration')
    user.groups.add(Group.objects.get(name=label))
    users[role] = user
day = timezone.localdate() + timedelta(days=1)
def at(day, hour):
    return timezone.make_aware(datetime.combine(day, time(hour)))
sessions = []
for title, start, status in [('Révisions et méthodes de travail', at(day, 10), 'planifiee'), ('Bilan de la semaine', at(day - timedelta(days=2), 10), 'terminee'), ('Préparation du prochain projet', at(day, 14), 'annulee')]:
    obj = SessionCoaching(titre=title, coach=users['coach'], etudiant=users['learner'], date_session=start, duree=60, statut=status, notes='Notes synthétiques privées du coach.')
    obj.full_clean(); obj.save(); sessions.append(obj)
foreign = SessionCoaching.objects.create(titre='Séance confidentielle étrangère', coach=users['othercoach'], etudiant=users['otherlearner'], date_session=at(day, 11), duree=60)
advice = ConseilPedagogique.objects.create(titre='Organiser les révisions', description='Préparer trois exercices et vérifier les réponses.', type_conseil='organisation', session=sessions[0])
for weekday in range(7):
    CoachAvailability.objects.create(coach=users['coach'], weekday=weekday, start_time=time(8), end_time=time(17))
CoachAvailabilityException.objects.create(coach=users['coach'], start_datetime=at(day, 15), end_datetime=at(day, 16), reason='Motif privé synthétique')
booking = BookingRequest.objects.create(coach=users['coach'], etudiant=users['learner'], requested_start=at(day, 12), duration=60, topic='Approfondissement des fractions')
for i, status in enumerate(['todo', 'in_progress', 'completed']):
    CoachingAction.objects.create(session=sessions[0], etudiant=users['learner'], title=['Comparer les fractions', 'Lire la ressource conseillée', 'Préparer une fiche de révision'][i], description='Consigne synthétique pour la vérification du parcours.', status=status, priority=['high', 'medium', 'low'][i], action_type='exercise', due_date=day + timedelta(days=i), completed_at=timezone.now() if status == 'completed' else None, feedback='Retour pédagogique de démonstration.', resource_url='https://example.org/ressource')
cookies = {}
for role, user in users.items():
    client = Client(); client.force_login(user)
    cookies[role] = client.cookies[settings.SESSION_COOKIE_NAME].value

class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass

server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=QuietHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{server.server_port}'
report = {'artifacts': str(ARTIFACTS), 'synthetic_database': True, 'pages': [], 'calendar': [], 'flows': [], 'errors': []}
database_executor = ThreadPoolExecutor(max_workers=1)
def db(operation):
    return database_executor.submit(operation).result()
print('ARTIFACTS=' + str(ARTIFACTS), flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    report['browser'] = browser.version
    for size, dimensions in ([] if '--flows-only' in sys.argv else [('desktop', {'width': 1440, 'height': 1000}), ('mobile', {'width': 390, 'height': 844})]):
        for role in (['coach'] if '--probe' in sys.argv else ['coach', 'learner', 'admin']):
            context = browser.new_context(viewport=dimensions, timezone_id='America/New_York', ignore_https_errors=False, is_mobile=size=='mobile', has_touch=size=='mobile')
            context.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cookies[role], 'url': BASE}])
            page = context.new_page()
            issues = []
            page.on('pageerror', lambda error: issues.append({'type': 'javascript', 'message': str(error)}))
            page.on('console', lambda message: issues.append({'type': 'console', 'message': message.text}) if message.type == 'error' else None)
            page.on('requestfailed', lambda request: issues.append({'type': 'network', 'url': request.url, 'error': request.failure}))
            paths = [('dashboard', '/coaching/tableau-de-bord/'), ('calendar', '/coaching/sessions/'), ('sessions', '/coaching/'), ('session-detail', sessions[0].get_absolute_url()), ('bookings', '/coaching/reservations/mes-demandes/'), ('booking-detail', booking.get_absolute_url()), ('learning-path', '/coaching/parcours/'), ('advice-list', '/coaching/conseils/liste/'), ('advice-detail', advice.get_absolute_url())]
            if role == 'learner': paths.append(('booking-search', '/coaching/reservations/'))
            else: paths.extend([('availability', '/coaching/disponibilites/'), ('session-form', '/coaching/ajouter/'), ('action-form', f'/coaching/{sessions[0].pk}/actions/ajouter/')])
            if '--probe' in sys.argv: paths = [item for item in paths if item[0] in ['calendar', 'session-detail', 'availability', 'action-form']]
            for name, path in paths:
                issues.clear()
                response = page.goto(BASE + path, wait_until='networkidle', timeout=45000)
                page.wait_for_timeout(250)
                metrics = page.evaluate('''() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth, mojibake: /[ÃÂ]/.test(document.querySelector('main')?.innerText || ''), title: document.querySelector('h1')?.innerText, privateNotes: document.querySelector('main')?.innerText.includes('Notes synthétiques privées du coach.'), foreignSession: document.querySelector('main')?.innerText.includes('Séance confidentielle étrangère')})''')
                page.screenshot(path=str(ARTIFACTS / f'{size}-{role}-{name}.png'), full_page=True)
                item = {'size': size, 'role': role, 'page': name, 'status': response.status, 'metrics': metrics, 'errors': list(issues)}
                report['pages'].append(item)
                if metrics['scrollWidth'] > metrics['width']:
                    item['overflow_elements'] = page.evaluate('''() => [...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,80)}))''')
                (ARTIFACTS / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                if name == 'calendar':
                    if page.locator('[data-calendar-view="dayGridMonth"]').is_disabled():
                        print('CALENDAR_UNAVAILABLE=' + json.dumps(issues), flush=True)
                        continue
                    for view in ['dayGridMonth', 'timeGridWeek', 'timeGridDay', 'listWeek']:
                        issues.clear()
                        page.locator(f'[data-calendar-view="{view}"]').click()
                        if view == 'timeGridDay':
                            page.locator('[data-calendar-nav="next"]').click()
                        page.wait_for_timeout(500)
                        events = page.locator('#coaching-calendar').inner_text()
                        calendar_info = page.evaluate('''() => ({title: document.querySelector('#calendar-title').innerText, error: !document.querySelector('#calendar-error').classList.contains('d-none'), buttons: [...document.querySelectorAll('[data-calendar-view]')].filter(x=>x.getAttribute('aria-pressed')==='true').map(x=>x.dataset.calendarView), rootClass: document.querySelector('#coaching-calendar').className, eventCount: document.querySelectorAll('#coaching-calendar .coaching-calendar-event').length, width: document.documentElement.scrollWidth, bodyWidth:innerWidth})''')
                        calendar_info['event_nodes'] = page.locator('#coaching-calendar').evaluate('''el => [...el.querySelectorAll('.coaching-calendar-event, [class*="coaching-event"], [class*="coaching-avail"], [class*="coaching-unavail"]')].map(e=>({html:e.outerHTML.slice(0,1800), color:getComputedStyle(e).color, background:getComputedStyle(e).backgroundColor}))''')
                        page.screenshot(path=str(ARTIFACTS / f'{size}-{role}-{view}.png'), full_page=True)
                        report['calendar'].append({'size':size, 'role': role, 'view': view, 'metrics':calendar_info, 'text':events[:2500], 'errors':list(issues)})
                print(f'{size} {role} {name}: {response.status} overflow={metrics["scrollWidth"] > metrics["width"]} errors={len(item["errors"])}', flush=True)
            context.close()
    if '--probe' not in sys.argv:
        for size, dimensions in [('desktop', {'width':1440,'height':1000}), ('mobile', {'width':390,'height':844})]:
            contexts = {}
            pages = {}
            for role in ['coach', 'learner', 'admin', 'othercoach', 'otherlearner']:
                contexts[role] = browser.new_context(viewport=dimensions, timezone_id='America/New_York', is_mobile=size=='mobile', has_touch=size=='mobile')
                contexts[role].add_cookies([{'name':settings.SESSION_COOKIE_NAME,'value':cookies[role],'url':BASE}])
                pages[role] = contexts[role].new_page()
            coach, learner, admin = pages['coach'], pages['learner'], pages['admin']
            def go(page, path):
                return page.goto(BASE+path, wait_until='networkidle')
            def record(name, operation):
                try:
                    operation()
                    report['flows'].append({'size':size,'name':name,'passed':True})
                    print(f'FLOW {size} {name}: PASS', flush=True)
                except Exception as error:
                    report['flows'].append({'size':size,'name':name,'passed':False,'error':traceback.format_exc()[-2200:]})
                    print(f'FLOW {size} {name}: FAIL {str(error)[:200]}', flush=True)
                (ARTIFACTS/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            def request_slot(topic):
                go(learner, '/coaching/reservations/')
                learner.locator('#id_coach').select_option(str(users['coach'].pk))
                learner.locator('#id_day').fill((day+timedelta(days=2)).isoformat())
                learner.locator('#id_duration').select_option('60')
                learner.get_by_role('button',name='Rechercher les créneaux').click()
                learner.wait_for_load_state('networkidle')
                form=learner.locator('.coaching-slot').first
                assert form.count(), 'No available slot displayed'
                form.locator('[name="topic"]').fill(topic)
                form.get_by_role('button',name='Demander ce créneau').click()
                learner.wait_for_url('**/reservations/mes-demandes/')
                result=db(lambda: BookingRequest.objects.get(topic=topic))
                assert result.status=='pending' and result.session_id is None
                return result
            def booking_flow():
                result=request_slot(f'Demande navigateur {size}')
                go(coach,result.get_absolute_url())
                coach.get_by_role('button',name='Approuver',exact=True).click()
                coach.wait_for_load_state('networkidle')
                db(result.refresh_from_db)
                assert result.status=='approved' and result.session_id
                assert coach.url.endswith(db(lambda: result.session.get_absolute_url()))
                go(learner,result.get_absolute_url())
                assert learner.get_by_role('link',name='Ouvrir la séance confirmée').count()==1
                learner.screenshot(path=str(ARTIFACTS/f'{size}-booking-approved.png'),full_page=True)
            record('booking_request_and_approval',booking_flow)
            def cancellation_flow():
                result=request_slot(f'Annulation navigateur {size}')
                go(learner,result.get_absolute_url())
                learner.get_by_role('button',name='Annuler ma demande').click()
                learner.wait_for_load_state('networkidle')
                db(result.refresh_from_db); assert result.status=='cancelled' and result.session_id is None
            record('booking_cancellation',cancellation_flow)
            def rejection_flow():
                result=request_slot(f'Refus navigateur {size}')
                go(coach,result.get_absolute_url())
                coach.get_by_role('button',name='Refuser',exact=True).click()
                coach.wait_for_load_state('networkidle')
                db(result.refresh_from_db); assert result.status=='rejected' and result.session_id is None
            record('booking_rejection',rejection_flow)
            def availability_flow():
                go(coach,'/coaching/disponibilites/')
                form=coach.locator('form[action="/coaching/disponibilites/ajouter/"]')
                form.locator('[name="weekday"]').select_option('0' if size=='desktop' else '1')
                form.locator('[name="start_time"]').fill('18:00')
                form.locator('[name="end_time"]').fill('19:00')
                form.get_by_role('button').click(); coach.wait_for_load_state('networkidle')
                item=db(lambda: CoachAvailability.objects.filter(coach=users['coach'],start_time=time(18)).latest('pk'))
                go(coach,f'/coaching/disponibilites/{item.pk}/modifier/')
                assert coach.locator('[name="start_time"]').input_value().startswith('18:00')
                coach.locator('[name="start_time"]').fill('18:15')
                coach.locator('[name="end_time"]').fill('19:15')
                coach.get_by_role('button',name='Enregistrer',exact=True).click(); coach.wait_for_load_state('networkidle')
                db(item.refresh_from_db); assert item.start_time==time(18,15)
                form=coach.locator('form[action="/coaching/disponibilites/exception/ajouter/"]')
                block_day=day+timedelta(days=3 if size=='desktop' else 4)
                form.locator('[name="start_datetime"]').fill(f'{block_day}T13:00')
                form.locator('[name="end_datetime"]').fill(f'{block_day}T14:00')
                form.locator('[name="reason"]').fill(f'Blocage navigateur {size}')
                form.get_by_role('button').click(); coach.wait_for_load_state('networkidle')
                assert db(lambda: CoachAvailabilityException.objects.filter(reason=f'Blocage navigateur {size}').exists())
                coach.screenshot(path=str(ARTIFACTS/f'{size}-availability-saved.png'),full_page=True)
                coach.locator(f'form[action="/coaching/disponibilites/window/{item.pk}/supprimer/"] button').click()
                coach.wait_for_load_state('networkidle')
                assert not db(lambda: CoachAvailability.objects.filter(pk=item.pk).exists())
            record('availability_create_edit_block_delete',availability_flow)
            def actions_flow():
                go(coach,f'/coaching/{sessions[0].pk}/actions/ajouter/')
                title=f'Action navigateur {size}'
                coach.locator('#id_title').fill(title)
                coach.locator('#id_description').fill('Exercice fictif de validation du navigateur.')
                coach.locator('#id_priority').select_option('high')
                coach.locator('#id_due_date').fill((day+timedelta(days=6)).isoformat())
                coach.get_by_role('button',name='Enregistrer l’action').click(); coach.wait_for_load_state('networkidle')
                action=db(lambda: CoachingAction.objects.get(title=title))
                assert action.etudiant_id==users['learner'].pk
                go(coach,f'/coaching/actions/{action.pk}/modifier/')
                coach.locator('#id_feedback').fill('Retour du coach après vérification.')
                coach.get_by_role('button',name='Enregistrer l’action').click(); coach.wait_for_load_state('networkidle')
                go(learner,'/coaching/parcours/')
                card=learner.locator('article').filter(has=learner.get_by_role('heading',name=title,exact=True))
                card.locator('select').select_option('in_progress'); card.get_by_role('button',name='Enregistrer',exact=True).click(); learner.wait_for_load_state('networkidle')
                db(action.refresh_from_db); assert action.status=='in_progress'
                card=learner.locator('article').filter(has=learner.get_by_role('heading',name=title,exact=True))
                card.locator('select').select_option('completed'); card.get_by_role('button',name='Enregistrer',exact=True).click(); learner.wait_for_load_state('networkidle')
                db(action.refresh_from_db); assert action.status=='completed' and action.completed_at
                assert learner.get_by_role('progressbar').get_attribute('aria-valuenow')==str(db(lambda: round(CoachingAction.objects.filter(etudiant=users['learner'],status='completed').count()*100/CoachingAction.objects.filter(etudiant=users['learner']).count())))
                learner.screenshot(path=str(ARTIFACTS/f'{size}-learning-action-completed.png'),full_page=True)
            record('learning_action_create_feedback_progress',actions_flow)
            def access_flow():
                assert go(pages['othercoach'],sessions[0].get_absolute_url()).status==404
                assert go(pages['otherlearner'],booking.get_absolute_url()).status==404
                assert go(learner,'/coaching/disponibilites/').status==403
                assert go(learner,f'/coaching/{sessions[0].pk}/actions/ajouter/').status==403
                assert go(admin,foreign.get_absolute_url()).status==200
            record('object_and_role_access',access_flow)
            def calendar_flow():
                go(coach,'/coaching/sessions/')
                coach.wait_for_selector('.coaching-calendar-event')
                assert coach.locator('.coaching-calendar-event').count()>0
                colors=coach.locator('.coaching-calendar-event').evaluate_all('(els)=>[...new Set(els.map(e=>getComputedStyle(e).getPropertyValue("--fc-event-color")))]')
                assert len(colors)>1, 'Session statuses must use distinct colors'
                coach.locator('[data-calendar-view="timeGridDay"]').click()
                coach.locator('[data-calendar-nav="next"]').click(); coach.wait_for_timeout(600)
                assert '10:00' in coach.locator('#coaching-calendar').inner_text()
                coach.locator(f'#coaching-calendar a[href="{sessions[0].get_absolute_url()}"]').first.click()
                coach.wait_for_url('**'+sessions[0].get_absolute_url())
                go(coach,'/coaching/sessions/')
                coach.locator('[data-calendar-nav="next"]').click(); coach.locator('[data-calendar-nav="next"]').click(); coach.wait_for_timeout(600)
                assert coach.locator('#calendar-empty').is_visible()
                if size=='mobile':
                    coach.locator('[data-sidebar-toggle]').click()
                    coach.locator('aside').get_by_role('link',name='Vue d’ensemble').click()
                    coach.wait_for_url('**/coaching/tableau-de-bord/')
            record('calendar_colors_timezone_click_empty_navigation',calendar_flow)
            def retry_flow():
                coach.route('**/coaching/sessions/evenements/**',lambda route:route.fulfill(status=503,body='Unavailable'))
                go(coach,'/coaching/sessions/')
                coach.locator('#calendar-error').wait_for(state='visible')
                coach.unroute('**/coaching/sessions/evenements/**')
                coach.locator('#calendar-retry').click()
                coach.locator('#calendar-error').wait_for(state='hidden')
                coach.wait_for_selector('.coaching-calendar-event')
            record('calendar_network_error_and_retry',retry_flow)
            for context in contexts.values(): context.close()
    browser.close()
server.shutdown()
(ARTIFACTS / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('REPORT=' + str(ARTIFACTS / 'report.json'), flush=True)
