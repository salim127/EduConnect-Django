import calendar
from datetime import date

from django.views.generic import TemplateView

from . import demo

MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


class SessionsView(TemplateView):
    template_name = 'coaching/sessions.html'

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        today = date.today()
        events = {s['jour']: s for s in demo.SESSIONS}
        ctx['sessions'] = demo.SESSIONS
        ctx['mois'] = f'{MOIS[today.month]} {today.year}'
        ctx['today'] = today.day
        # semaines -> jours {n, event} ; n=0 = case vide
        ctx['weeks'] = [[{'n': d, 'event': events.get(d)} for d in week]
                        for week in calendar.Calendar().monthdayscalendar(today.year, today.month)]
        return ctx


class ConseilsView(TemplateView):
    template_name = 'coaching/conseils.html'
    extra_context = {'conseils': demo.CONSEILS}
