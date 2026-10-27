# FullCalendar in Coaching

The calendar uses FullCalendar **7.1.3**, the standard browser-global bundle. The bundle includes the free day-grid, time-grid, and list views used here; no premium Scheduler or resource-timeline features are used. The French locale bundle is pinned to the same version. The Monarch theme JavaScript, theme stylesheet, and purple palette are required in addition to `skeleton.css`; the skeleton alone leaves controls and the grid unstyled. Calendar controls and responsive presentation are scoped to `.coaching-agenda` in `static/css/coaching.css`, with behavior in `static/js/coaching-calendar.js`.

The calendar is configured for `Africa/Tunis`. Events are fetched from the authenticated Django endpoint and returned with ISO 8601 offsets. The browser timezone therefore does not change the displayed appointment time. The booking service also calculates and validates slots in that timezone.

References: [script-tag installation and standard bundle](https://fullcalendar.io/docs/vanilla-js), [named timezone behavior](https://fullcalendar.io/docs/timeZone), [locale loading](https://fullcalendar.io/docs/locale).
