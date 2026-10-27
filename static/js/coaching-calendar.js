/* FullCalendar 7: standard views, Monarch theme, and Tunis timezone. */
document.addEventListener('DOMContentLoaded', () => {
  const element = document.getElementById('coaching-calendar');
  if (!element) return;
  const loading = document.getElementById('calendar-loading');
  const error = document.getElementById('calendar-error');
  const empty = document.getElementById('calendar-empty');
  const counter = document.getElementById('calendar-count');
  const buttons = document.querySelectorAll('[data-calendar-view], [data-calendar-nav]');
  const showError = () => {
    loading.classList.add('d-none'); empty.classList.add('d-none');
    error.classList.remove('d-none'); counter.textContent = 'Chargement indisponible';
  };
  if (!window.FullCalendar) { buttons.forEach(button => { button.disabled = true; }); showError(); return; }
  let calendar;
  const dateFormat = new Intl.DateTimeFormat('fr-FR', {
    timeZone: 'Africa/Tunis', weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit'
  });
  try {
    calendar = new FullCalendar.Calendar(element, {
      initialView: 'dayGridMonth', locale: 'fr', firstDay: 1, timeZone: 'Africa/Tunis',
      headerToolbar: false, height: 650, nowIndicator: true, dayMaxEvents: 3,
      fixedWeekCount: false, editable: false, selectable: false,
      eventClass: 'coaching-calendar-event',
      eventTimeClass: 'coaching-calendar-event-time',
      eventTitleClass: 'coaching-calendar-event-title',
      dayHeaderClass: 'coaching-calendar-day-header',
      dayCellClass: info => ['coaching-calendar-day', info.isToday ? 'coaching-calendar-today' : ''],
      allDayText: 'Journée', noEventsText: 'Aucune séance sur cette période',
      slotMinTime: '07:00:00', slotMaxTime: '22:00:00', scrollTime: '08:00:00',
      eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
      events: { url: element.dataset.eventsUrl, failure: showError },
      loading: active => {
        loading.classList.toggle('d-none', !active); element.setAttribute('aria-busy', String(active));
        if (active) { error.classList.add('d-none'); empty.classList.add('d-none'); }
      },
      datesSet: info => {
        document.getElementById('calendar-title').textContent = info.view.title;
        document.querySelectorAll('[data-calendar-view]').forEach(button => {
          button.setAttribute('aria-pressed', String(button.dataset.calendarView === info.view.type));
        });
      },
      eventsSet: events => {
        if (!calendar || !error.classList.contains('d-none')) return;
        const start = calendar.view.activeStart; const end = calendar.view.activeEnd;
        const count = events.filter(event => event.display !== 'background' && event.start < end && (event.end || event.start) >= start).length;
        counter.textContent = `${count} rendez-vous sur cette période`;
        empty.classList.toggle('d-none', count > 0);
      },
      eventClick: info => { if (info.event.url) { info.jsEvent.preventDefault(); window.location.assign(info.event.url); } },
      eventDidMount: info => {
        const date = info.event.start ? dateFormat.format(info.event.start) : '';
        const details = [info.event.title, date, info.event.extendedProps.status || ''].filter(Boolean);
        info.el.setAttribute('title', details.join(' · ')); info.el.setAttribute('aria-label', details.join(', '));
      }
    });
    buttons.forEach(button => button.addEventListener('click', () => {
      if (button.dataset.calendarView) calendar.changeView(button.dataset.calendarView);
      else calendar[button.dataset.calendarNav]();
    }));
    document.getElementById('calendar-retry').addEventListener('click', () => calendar.refetchEvents());
    calendar.render();
  } catch (exception) { showError(); }
});
