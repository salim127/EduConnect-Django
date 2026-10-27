from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.views.generic import TemplateView
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from accounts.roles import LEARNER, is_admin
from config.mixins import QueryStringMixin

from .access import (is_manager, managed_sessions, visible_sessions, managed_availabilities,
                     managed_exceptions, visible_bookings, visible_actions)
from . import demo
from .forms import (ConseilPedagogiqueForm, GeneratedAdviceReviewForm, SessionCoachingForm, SessionNotesForm,
                    CoachAvailabilityForm, AvailabilityExceptionForm, BookingSearchForm,
                    BookingRequestForm, CoachingActionForm, CoachingActionUpdateForm,
                    CoachingActionProgressForm)
from .intelligence import SCHEMAS, generer_brouillon, proposition_en_texte
from .models import (ConseilPedagogique, SessionCoaching, BookingRequest, CoachAvailability,
                     CoachAvailabilityException, CoachingAction)
from .scheduling import TUNIS, available_slots, reserve_booking

MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _parse_month(value):
    try:
        parsed = date.fromisoformat(value + '-01') if value else timezone.localdate().replace(day=1)
        return parsed.replace(day=1) if parsed.isoformat()[:7] == value or not value else None
    except (TypeError, ValueError):
        return None


def _month_window(first_day):
    next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(first_day, time.min), zone)
    end = timezone.make_aware(datetime.combine(next_month, time.min), zone)
    return start, end


def _local_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _month_url(month):
    return f'?month={month:%Y-%m}'


class SessionsView(TemplateView):
    template_name = 'coaching/sessions.html'
    permission_required = 'coaching.view_sessioncoaching'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.has_perm(self.permission_required):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class CalendarEventsView(View):
    permission_required = 'coaching.view_sessioncoaching'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.has_perm(self.permission_required):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        start, end = parse_datetime(request.GET.get('start', '')), parse_datetime(request.GET.get('end', ''))
        if not start or not end or timezone.is_naive(start) or timezone.is_naive(end) or start >= end or end - start > timedelta(days=93):
            return JsonResponse({'error': 'Plage de dates invalide.'}, status=400)
        sessions = visible_sessions(request.user, SessionCoaching.objects.select_related('coach', 'etudiant')).filter(
            date_session__lt=end, date_session__gte=start - timedelta(days=2)
        )
        events = []
        for session in sessions:
            local_start = timezone.localtime(session.date_session, TUNIS)
            if local_start + timedelta(minutes=session.duree) <= start:
                continue
            events.append({'id': f'session-{session.pk}', 'title': session.titre,
                           'start': session.date_session.isoformat(),
                           'end': (session.date_session + timedelta(minutes=session.duree)).isoformat(),
                           'url': session.get_absolute_url(), 'className': [f'coaching-event-{session.statut}'],
                           'color': {'planifiee': '#6a56bd', 'terminee': '#218c6a', 'annulee': '#797288'}[session.statut],
                           'contrastColor': '#ffffff',
                           'extendedProps': {'kind': 'session', 'status': session.get_statut_display(),
                                             'duration': session.duree}})
        bookings = visible_bookings(request.user, BookingRequest.objects.select_related('coach', 'etudiant')).filter(
            status=BookingRequest.Status.PENDING, requested_start__gte=start - timedelta(days=1), requested_start__lt=end
        )
        for item in bookings:
            events.append({'id': f'booking-{item.pk}', 'title': f'Demande · {item.topic}',
                           'start': item.requested_start.isoformat(),
                           'end': (item.requested_start + timedelta(minutes=item.duration)).isoformat(),
                           'url': reverse('coaching:booking_detail', args=[item.pk]),
                           'className': ['coaching-event-pending'], 'color': '#946500', 'contrastColor': '#ffffff',
                           'extendedProps': {'kind': 'booking', 'status': item.get_status_display(),
                                             'duration': item.duration}})
        # Recurring availability and exceptions are only visible to their owner/admin.
        if is_manager(request.user):
            coaches = [request.user] if not is_admin(request.user) else []
            windows = CoachAvailability.objects.filter(is_active=True)
            exceptions = CoachAvailabilityException.objects.all()
            if coaches:
                windows, exceptions = windows.filter(coach=request.user), exceptions.filter(coach=request.user)
            cursor_day = timezone.localtime(start, TUNIS).date()
            stop_day = timezone.localtime(end, TUNIS).date() + timedelta(days=1)
            while cursor_day < stop_day:
                for window in windows.filter(weekday=cursor_day.weekday()):
                    slot_start = datetime.combine(cursor_day, window.start_time, tzinfo=TUNIS)
                    slot_end = datetime.combine(cursor_day, window.end_time, tzinfo=TUNIS)
                    events.append({'id': f'avail-{window.pk}-{cursor_day}', 'title': 'Disponibilité',
                                   'start': slot_start.isoformat(), 'end': slot_end.isoformat(),
                                   'display': 'background', 'className': ['coaching-availability'], 'color': '#e7f6f0'})
                cursor_day += timedelta(days=1)
            for exception in exceptions.filter(start_datetime__lt=end, end_datetime__gt=start):
                events.append({'id': f'exception-{exception.pk}', 'title': 'Indisponible',
                               'start': exception.start_datetime.isoformat(), 'end': exception.end_datetime.isoformat(),
                               'display': 'background', 'className': ['coaching-unavailable'], 'color': '#f8dfe4'})
        return JsonResponse(events, safe=False)


class ConseilsView(TemplateView):
    template_name = 'coaching/conseils.html'
    extra_context = {'conseils': demo.CONSEILS}


class CoachingPermissionMixin(PermissionRequiredMixin):
    """Ajoute la vérification de rôle aux permissions Django."""

    def has_permission(self):
        return self.request.user.is_authenticated and self.request.user.is_active and super().has_permission()


class CoachingManagerMixin(CoachingPermissionMixin):
    def has_permission(self):
        return is_manager(self.request.user) and super().has_permission()


class SafeCoachingPaginationMixin:
    """Use Django's forgiving page parser so malformed page numbers stay usable."""

    def paginate_queryset(self, queryset, page_size):
        paginator = self.get_paginator(queryset, page_size, allow_empty_first_page=self.get_allow_empty())
        page = paginator.get_page(self.request.GET.get('page'))
        return paginator, page, page.object_list, page.has_other_pages()


class SessionVisibleMixin:
    def get_queryset(self):
        return visible_sessions(
            self.request.user,
            SessionCoaching.objects.select_related('coach', 'etudiant').prefetch_related('conseils'),
        )


class SessionManagedMixin:
    def get_queryset(self):
        return managed_sessions(
            self.request.user,
            SessionCoaching.objects.select_related('coach', 'etudiant').prefetch_related('conseils'),
        )


class SessionListView(CoachingPermissionMixin, SafeCoachingPaginationMixin, QueryStringMixin, ListView):
    permission_required = 'coaching.view_sessioncoaching'
    template_name = 'coaching/session_list.html'
    paginate_by = 9

    def get_queryset(self):
        qs = visible_sessions(self.request.user, SessionCoaching.objects.select_related('coach', 'etudiant'))
        if q := self.request.GET.get('q', '').strip():
            qs = qs.filter(Q(titre__icontains=q))
        if statut := self.request.GET.get('statut', ''):
            if statut in SessionCoaching.Statut.values:
                qs = qs.filter(statut=statut)
            else:
                self.filter_errors = ['Statut invalide.']
        start_date, end_date = self.request.GET.get('date_debut', ''), self.request.GET.get('date_fin', '')
        start, end = _parse_date(start_date), _parse_date(end_date)
        errors = getattr(self, 'filter_errors', [])
        if start_date and not start:
            errors.append('Date de début invalide.')
        if end_date and not end:
            errors.append('Date de fin invalide.')
        if start and end and start > end:
            errors.append('La date de début doit précéder la date de fin.')
        if start:
            qs = qs.filter(date_session__gte=_local_midnight(start))
        if end:
            qs = qs.filter(date_session__lt=_local_midnight(end + timedelta(days=1)))
        self.filter_errors = errors
        if is_admin(self.request.user):
            if (coach_id := self.request.GET.get('coach', '')).isdigit():
                qs = qs.filter(coach_id=int(coach_id))
            elif coach_id:
                self.filter_errors = getattr(self, 'filter_errors', []) + ['Coach invalide.']
            if (student_id := self.request.GET.get('etudiant', '')).isdigit():
                qs = qs.filter(etudiant_id=int(student_id))
            elif student_id:
                self.filter_errors = getattr(self, 'filter_errors', []) + ['Apprenant invalide.']
            self.filter_errors = getattr(self, 'filter_errors', [])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(statuts=SessionCoaching.Statut.choices,
                                          can_manage=is_manager(self.request.user), filter_errors=getattr(self, 'filter_errors', []), **kwargs)
        if is_admin(self.request.user):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            context['coaches'] = User.objects.filter(is_active=True, groups__name='Enseignant / Coach').distinct().order_by('username')
            context['etudiants'] = User.objects.filter(is_active=True, groups__name='Apprenant').distinct().order_by('username')
        return context


class SessionDetailView(CoachingPermissionMixin, SessionVisibleMixin, DetailView):
    permission_required = 'coaching.view_sessioncoaching'
    model = SessionCoaching
    template_name = 'coaching/session_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        manager = is_manager(self.request.user) and (is_admin(self.request.user) or obj.coach_id == self.request.user.pk)
        context.update(can_manage=manager, can_edit=manager and obj.statut == SessionCoaching.Statut.PLANIFIEE,
                       can_transition=manager and obj.statut == SessionCoaching.Statut.PLANIFIEE,
                       can_assign_actions=manager and self.request.user.has_perm('coaching.add_coachingaction'),
                       coaching_actions=visible_actions(self.request.user, CoachingAction.objects.filter(session=obj).select_related('etudiant')))
        return context


class SessionFormMixin:
    form_class = SessionCoachingForm
    template_name = 'coaching/session_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class SessionCreateView(CoachingManagerMixin, SessionFormMixin, CreateView):
    permission_required = 'coaching.add_sessioncoaching'

    def form_valid(self, form):
        if not is_admin(self.request.user):
            form.instance.coach = self.request.user
        messages.success(self.request, 'Séance de coaching créée.')
        return super().form_valid(form)


class SessionUpdateView(CoachingManagerMixin, SessionManagedMixin, SessionFormMixin, UpdateView):
    permission_required = 'coaching.change_sessioncoaching'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if is_admin(self.request.user) else qs.filter(statut=SessionCoaching.Statut.PLANIFIEE)

    def form_valid(self, form):
        if not is_admin(self.request.user):
            form.instance.coach = self.request.user
        messages.success(self.request, 'Séance de coaching modifiée.')
        return super().form_valid(form)


class SessionDeleteView(CoachingManagerMixin, SessionManagedMixin, DeleteView):
    permission_required = 'coaching.delete_sessioncoaching'
    http_method_names = ['post']
    success_url = reverse_lazy('coaching:session_list')

    def get_queryset(self):
        return super().get_queryset().filter(statut=SessionCoaching.Statut.PLANIFIEE)

    def form_valid(self, form):
        messages.success(self.request, 'Séance de coaching supprimée.')
        return super().form_valid(form)


class SessionStatusView(CoachingManagerMixin, SessionManagedMixin, View):
    permission_required = 'coaching.change_sessioncoaching'
    http_method_names = ['post']

    def post(self, request, pk):
        session = self.get_queryset().filter(pk=pk, statut=SessionCoaching.Statut.PLANIFIEE).first()
        if session is None:
            raise Http404('Séance introuvable ou transition indisponible.')
        target = request.POST.get('statut')
        if target not in (SessionCoaching.Statut.TERMINEE, SessionCoaching.Statut.ANNULEE):
            messages.error(request, 'Transition de statut invalide.')
            return redirect(session)
        session.statut = target
        try:
            session.full_clean()
        except ValidationError as error:
            messages.error(request, next(iter(error.messages), 'Impossible de changer le statut.'))
        else:
            session.save(update_fields=['statut'])
            messages.success(request, f'Séance {session.get_statut_display().lower()}.')
        return redirect(session)


class ConseilVisibleMixin:
    def get_queryset(self):
        sessions = visible_sessions(self.request.user, SessionCoaching.objects.all())
        return ConseilPedagogique.objects.select_related('session__coach', 'session__etudiant').filter(session__in=sessions)


class ConseilManagedMixin:
    def get_queryset(self):
        sessions = managed_sessions(self.request.user, SessionCoaching.objects.all())
        return ConseilPedagogique.objects.select_related('session__coach', 'session__etudiant').filter(session__in=sessions)


class ConseilListView(CoachingPermissionMixin, SafeCoachingPaginationMixin, QueryStringMixin, ListView):
    permission_required = 'coaching.view_conseilpedagogique'
    template_name = 'coaching/conseil_list.html'
    paginate_by = 10

    def get_queryset(self):
        sessions = visible_sessions(self.request.user, SessionCoaching.objects.all())
        qs = ConseilPedagogique.objects.select_related('session__coach', 'session__etudiant').filter(session__in=sessions)
        if q := self.request.GET.get('q', '').strip():
            qs = qs.filter(Q(titre__icontains=q) | Q(description__icontains=q))
        if kind := self.request.GET.get('type', ''):
            if kind in ConseilPedagogique.TypeConseil.values:
                qs = qs.filter(type_conseil=kind)
            else:
                self.filter_errors = ['Type de conseil invalide.']
        session_id = self.request.GET.get('session', '')
        if session_id:
            if session_id.isdigit() and qs.filter(session_id=int(session_id)).exists():
                qs = qs.filter(session_id=int(session_id))
            else:
                self.filter_errors = getattr(self, 'filter_errors', []) + ['Séance invalide ou inaccessible.']
        created_after = self.request.GET.get('date_debut', '')
        created_before = self.request.GET.get('date_fin', '')
        start, end = _parse_date(created_after), _parse_date(created_before)
        errors = getattr(self, 'filter_errors', [])
        if created_after and not start:
            errors.append('Date de début invalide.')
        if created_before and not end:
            errors.append('Date de fin invalide.')
        if start and end and start > end:
            errors.append('La date de début doit précéder la date de fin.')
        if start:
            qs = qs.filter(date_creation__gte=_local_midnight(start))
        if end:
            qs = qs.filter(date_creation__lt=_local_midnight(end + timedelta(days=1)))
        self.filter_errors = errors
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(types=ConseilPedagogique.TypeConseil.choices,
                                           can_manage=is_manager(self.request.user), filter_errors=getattr(self, 'filter_errors', []), **kwargs)
        context['sessions'] = visible_sessions(self.request.user, SessionCoaching.objects.order_by('-date_session'))
        return context


class CoachingDashboardView(CoachingPermissionMixin, TemplateView):
    permission_required = ('coaching.view_sessioncoaching', 'coaching.view_conseilpedagogique')
    template_name = 'coaching/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sessions = visible_sessions(
            self.request.user, SessionCoaching.objects.select_related('coach', 'etudiant')
        )
        now = timezone.now()
        upcoming = sessions.filter(statut=SessionCoaching.Statut.PLANIFIEE, date_session__gte=now)
        counts = {status: sessions.filter(statut=status).count() for status, _ in SessionCoaching.Statut.choices}
        advice_count = ConseilPedagogique.objects.filter(session__in=sessions).count()
        context.update(
            total_sessions=sessions.count(),
            upcoming_count=upcoming.count(),
            completed_count=counts[SessionCoaching.Statut.TERMINEE],
            cancelled_count=counts[SessionCoaching.Statut.ANNULEE],
            advice_count=advice_count,
            next_session=upcoming.order_by('date_session', 'pk').first(),
            can_manage=is_manager(self.request.user),
            pending_bookings=visible_bookings(self.request.user).filter(status=BookingRequest.Status.PENDING).count(),
            open_actions=visible_actions(self.request.user).exclude(status=CoachingAction.Status.COMPLETED).count(),
            recent_advice=ConseilPedagogique.objects.filter(session__in=sessions).select_related('session').order_by('-date_creation')[:4],
        )
        return context


class CoachingAiGenerateView(CoachingManagerMixin, View):
    """POST-only generation for a session inside the caller's managed scope."""
    permission_required = 'coaching.view_sessioncoaching'
    http_method_names = ['post']

    def post(self, request, pk):
        session = get_object_or_404(
            managed_sessions(request.user, SessionCoaching.objects.select_related('coach', 'etudiant')),
            pk=pk,
        )
        mode = request.POST.get('mode', '')
        if mode not in ('conseil', 'resume'):
            return render(request, 'coaching/ai_preview.html', {
                'object': session, 'ai_error': 'Action IA inconnue.', 'ai_mode': mode,
            }, status=400)
        if mode == 'conseil' and not request.user.has_perm('coaching.add_conseilpedagogique'):
            return render(request, 'coaching/ai_preview.html', {
                'object': session, 'ai_error': 'Vous ne pouvez pas enregistrer un conseil pédagogique.',
                'ai_mode': mode,
            }, status=403)

        now = timezone.now().timestamp()
        last_call = request.session.get('coaching_ai_last_call', 0)
        if last_call > now - 30:
            return render(request, 'coaching/ai_preview.html', {
                'object': session, 'ai_error': 'Attendez 30 secondes avant une nouvelle demande Gemini.',
                'ai_mode': mode,
            }, status=429)
        request.session['coaching_ai_last_call'] = now

        try:
            data = generer_brouillon(session.notes, mode)
        except ValueError as error:
            return render(request, 'coaching/ai_preview.html', {
                'object': session, 'ai_error': str(error), 'ai_mode': mode,
            }, status=503 if not settings.GEMINI_API_KEY else 200)

        context = {'object': session, 'ai_mode': mode, 'ai_data': data,
                   'ai_sections': [(label, data[key]) for key, label in SCHEMAS[mode].items()]}
        if mode == 'conseil':
            description = proposition_en_texte(data, mode)
            context['review_form'] = GeneratedAdviceReviewForm(initial={
                'titre': f'Conseil pédagogique — {session.titre}'[:200],
                'description': description,
                'type_conseil': ConseilPedagogique.TypeConseil.METHODE,
            })
        return render(request, 'coaching/ai_preview.html', context)


class CoachingAiSaveAdviceView(CoachingManagerMixin, View):
    """Persist an advice only after a separate, explicit review submission."""
    permission_required = 'coaching.add_conseilpedagogique'
    http_method_names = ['post']

    def post(self, request, pk):
        session = get_object_or_404(
            managed_sessions(request.user, SessionCoaching.objects.select_related('coach', 'etudiant')),
            pk=pk,
        )
        form = GeneratedAdviceReviewForm(request.POST)
        if not form.is_valid():
            return render(request, 'coaching/ai_preview.html', {
                'object': session, 'ai_mode': 'conseil', 'review_form': form,
                'ai_error': 'Vérifiez le titre et le contenu avant l’enregistrement.',
            }, status=400)
        advice = ConseilPedagogique(
            session=session, titre=form.cleaned_data['titre'],
            description=form.cleaned_data['description'],
            type_conseil=form.cleaned_data['type_conseil'],
        )
        advice.full_clean()
        advice.save()
        messages.success(request, 'Conseil relu et enregistré.')
        return redirect(session)


class CoachingSessionNotesView(CoachingManagerMixin, View):
    permission_required = 'coaching.change_sessioncoaching'
    http_method_names = ['post']

    def post(self, request, pk):
        session = get_object_or_404(
            managed_sessions(request.user, SessionCoaching.objects.all()), pk=pk,
        )
        form = SessionNotesForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Les notes doivent contenir au plus 6 000 caractères.')
            return redirect(session)
        session.notes = form.cleaned_data['notes']
        session.save(update_fields=['notes'])
        messages.success(request, 'Notes de séance enregistrées.')
        return redirect(session)


class ConseilDetailView(CoachingPermissionMixin, ConseilVisibleMixin, DetailView):
    permission_required = 'coaching.view_conseilpedagogique'
    model = ConseilPedagogique
    template_name = 'coaching/conseil_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        context['can_manage'] = is_manager(self.request.user) and (is_admin(self.request.user) or obj.session.coach_id == self.request.user.pk)
        return context


class ConseilFormMixin:
    form_class = ConseilPedagogiqueForm
    template_name = 'coaching/conseil_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class ConseilCreateView(CoachingManagerMixin, ConseilFormMixin, CreateView):
    permission_required = 'coaching.add_conseilpedagogique'

    def get_initial(self):
        initial = super().get_initial()
        session_id = self.request.GET.get('session', '')
        choices = self.get_form_class()(user=self.request.user).fields['session'].queryset
        if session_id.isdigit() and choices.filter(pk=session_id).exists():
            initial['session'] = int(session_id)
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Conseil pédagogique créé.')
        return super().form_valid(form)


class ConseilUpdateView(CoachingManagerMixin, ConseilManagedMixin, ConseilFormMixin, UpdateView):
    permission_required = 'coaching.change_conseilpedagogique'

    def form_valid(self, form):
        messages.success(self.request, 'Conseil pédagogique modifié.')
        return super().form_valid(form)


class ConseilDeleteView(CoachingManagerMixin, ConseilManagedMixin, DeleteView):
    permission_required = 'coaching.delete_conseilpedagogique'
    http_method_names = ['post']
    success_url = reverse_lazy('coaching:conseil_list')

    def form_valid(self, form):
        messages.success(self.request, 'Conseil pédagogique supprimé.')
        return super().form_valid(form)


class BookingSearchView(CoachingPermissionMixin, TemplateView):
    permission_required = 'coaching.add_bookingrequest'
    template_name = 'coaching/booking_search.html'

    def has_permission(self):
        return super().has_permission() and self.request.user.groups.filter(name=LEARNER).exists()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = BookingSearchForm(self.request.GET or None, user=self.request.user)
        slots = []
        if form.is_valid():
            slots = available_slots(form.cleaned_data['coach'], form.cleaned_data['day'],
                                    form.cleaned_data['duration'], learner=self.request.user)
        ctx.update(form=form, slots=slots, searched=bool(self.request.GET))
        return ctx


class BookingCreateView(CoachingPermissionMixin, View):
    permission_required = 'coaching.add_bookingrequest'
    http_method_names = ['post']

    def has_permission(self):
        return super().has_permission() and self.request.user.groups.filter(name=LEARNER).exists()

    def post(self, request):
        form = BookingRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Demande invalide. Recherchez à nouveau un créneau disponible.')
            return redirect('coaching:booking_search')
        values = form.cleaned_data
        coach, start, duration = values['coach'], values['requested_start'], values['duration']
        local_start = timezone.localtime(start, TUNIS)
        if local_start not in [slot['start'] for slot in available_slots(coach, local_start.date(), duration, request.user)]:
            messages.error(request, 'Ce créneau n’est plus disponible. Effectuez une nouvelle recherche.')
            return redirect('coaching:booking_search')
        booking = BookingRequest(coach=coach, etudiant=request.user, requested_start=start,
                                 duration=duration, topic=values['topic'])
        try:
            booking.full_clean()
            booking.save()
        except (ValidationError, IntegrityError):
            messages.error(request, 'La demande n’a pas pu être créée : ce créneau vient peut-être d’être réservé.')
            return redirect('coaching:booking_search')
        messages.success(request, 'Demande envoyée au coach. Elle réserve le créneau en attendant sa décision.')
        return redirect('coaching:booking_list')



class BookingListView(CoachingPermissionMixin, ListView):
    permission_required = 'coaching.view_bookingrequest'
    template_name = 'coaching/booking_list.html'
    context_object_name = 'bookings'
    paginate_by = 15

    def get_queryset(self):
        return visible_bookings(self.request.user, BookingRequest.objects.select_related('coach', 'etudiant', 'session'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_book'] = self.request.user.has_perm('coaching.add_bookingrequest') and self.request.user.groups.filter(name=LEARNER).exists()
        return context


class BookingDetailView(CoachingPermissionMixin, DetailView):
    permission_required = 'coaching.view_bookingrequest'
    model = BookingRequest
    template_name = 'coaching/booking_detail.html'

    def get_queryset(self):
        return visible_bookings(self.request.user, BookingRequest.objects.select_related('coach', 'etudiant', 'session'))


class BookingDecisionView(CoachingManagerMixin, View):
    permission_required = 'coaching.change_bookingrequest'
    http_method_names = ['post']

    def post(self, request, pk, decision):
        booking = get_object_or_404(visible_bookings(request.user), pk=pk)
        if booking.status != BookingRequest.Status.PENDING or (not is_admin(request.user) and booking.coach_id != request.user.pk):
            raise Http404
        if decision == 'approve':
            try:
                session = reserve_booking(booking)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(request, 'Demande approuvée et séance confirmée.')
                return redirect(session)
        elif decision == 'reject':
            booking.status = BookingRequest.Status.REJECTED
            booking.full_clean()
            booking.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Demande refusée ; aucune séance n’a été créée.')
        else:
            raise Http404
        return redirect('coaching:booking_detail', pk=pk)


class BookingCancelView(CoachingPermissionMixin, View):
    permission_required = 'coaching.change_bookingrequest'
    http_method_names = ['post']

    def post(self, request, pk):
        booking = get_object_or_404(visible_bookings(request.user), pk=pk)
        if booking.etudiant_id != request.user.pk or booking.status != BookingRequest.Status.PENDING:
            raise Http404
        booking.status = BookingRequest.Status.CANCELLED
        booking.full_clean()
        booking.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Demande annulée.')
        return redirect('coaching:booking_list')


class AvailabilityListView(CoachingManagerMixin, TemplateView):
    permission_required = 'coaching.view_coachavailability'
    template_name = 'coaching/availability.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(availability=managed_availabilities(self.request.user).select_related('coach'),
                   exceptions=managed_exceptions(self.request.user).select_related('coach'),
                   upcoming=managed_sessions(self.request.user, SessionCoaching.objects.filter(
                       statut=SessionCoaching.Statut.PLANIFIEE, date_session__gte=timezone.now()
                   ).select_related('coach', 'etudiant'))[:8],
                   availability_form=CoachAvailabilityForm(user=self.request.user), exception_form=AvailabilityExceptionForm(user=self.request.user))
        return ctx


class AvailabilityCreateView(CoachingManagerMixin, View):
    permission_required = 'coaching.add_coachavailability'
    http_method_names = ['post']

    def post(self, request):
        form = CoachAvailabilityForm(request.POST, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.coach = request.user if not is_admin(request.user) else form.cleaned_data.get('coach')
            if item.coach:
                self._save(item, request)
            else:
                messages.error(request, 'Sélectionnez un coach.')
        else:
            messages.error(request, 'Vérifiez les horaires et les chevauchements.')
        return redirect('coaching:availability')

    @staticmethod
    def _save(item, request):
        try:
            item.full_clean(); item.save()
        except (ValidationError, IntegrityError):
            messages.error(request, 'Cette disponibilité est invalide ou chevauche une plage existante.')
        else:
            messages.success(request, 'Disponibilité enregistrée.')


class AvailabilityUpdateView(CoachingManagerMixin, View):
    permission_required = 'coaching.change_coachavailability'
    http_method_names = ['get', 'post']

    def get_queryset(self, user):
        return managed_availabilities(user)

    def get(self, request, pk):
        item = get_object_or_404(self.get_queryset(request.user), pk=pk)
        return render(request, 'coaching/availability_edit.html', {'form': CoachAvailabilityForm(instance=item, user=request.user), 'item': item})

    def post(self, request, pk):
        item = get_object_or_404(self.get_queryset(request.user), pk=pk)
        form = CoachAvailabilityForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            if not is_admin(request.user):
                obj.coach = request.user
            try:
                obj.full_clean(); obj.save()
            except (ValidationError, IntegrityError):
                form.add_error(None, 'Cette plage est invalide ou chevauche une autre disponibilité.')
            else:
                messages.success(request, 'Disponibilité mise à jour.')
                return redirect('coaching:availability')
        return render(request, 'coaching/availability_edit.html', {'form': form, 'item': item}, status=400)


class AvailabilityExceptionCreateView(CoachingManagerMixin, View):
    permission_required = 'coaching.add_coachavailabilityexception'
    http_method_names = ['post']

    def post(self, request):
        form = AvailabilityExceptionForm(request.POST, user=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            item.coach = request.user if not is_admin(request.user) else form.cleaned_data.get('coach')
            if not item.coach:
                messages.error(request, 'Sélectionnez un coach.')
                return redirect('coaching:availability')
            try:
                item.full_clean(); item.save()
            except (ValidationError, IntegrityError):
                messages.error(request, 'Cette période d’indisponibilité est invalide.')
            else:
                messages.success(request, 'Période bloquée dans le calendrier.')
        else:
            messages.error(request, 'Vérifiez les dates de la période indisponible.')
        return redirect('coaching:availability')


class AvailabilityDeleteView(CoachingManagerMixin, View):
    permission_required = 'coaching.delete_coachavailability'
    http_method_names = ['post']

    def post(self, request, kind, pk):
        model, scope = ((CoachAvailability, managed_availabilities) if kind == 'window' else
                        (CoachAvailabilityException, managed_exceptions) if kind == 'exception' else (None, None))
        if model is None:
            raise Http404
        item = get_object_or_404(scope(request.user), pk=pk)
        item.delete()
        messages.success(request, 'Élément supprimé.')
        return redirect('coaching:availability')


class CoachingActionListView(CoachingPermissionMixin, TemplateView):
    permission_required = 'coaching.view_coachingaction'
    template_name = 'coaching/learning_path.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        actions = visible_actions(self.request.user, CoachingAction.objects.select_related('session', 'session__coach'))
        total, completed = actions.count(), actions.filter(status=CoachingAction.Status.COMPLETED).count()
        ctx.update(actions=actions, total_actions=total, completed_actions=completed,
                   progress_percent=round(completed * 100 / total) if total else 0)
        return ctx


class CoachingActionCreateView(CoachingManagerMixin, View):
    permission_required = 'coaching.add_coachingaction'
    http_method_names = ['get', 'post']

    def get(self, request, pk):
        session = get_object_or_404(managed_sessions(request.user, SessionCoaching.objects.all()), pk=pk)
        return render(request, 'coaching/action_form.html', {'form': CoachingActionForm(), 'session': session})

    def post(self, request, pk):
        session = get_object_or_404(managed_sessions(request.user, SessionCoaching.objects.all()), pk=pk)
        form = CoachingActionForm(request.POST)
        if form.is_valid():
            action = form.save(commit=False); action.session = session; action.etudiant_id = session.etudiant_id
            try:
                action.full_clean(); action.save()
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, 'Action ajoutée au parcours pédagogique.')
                return redirect(session)
        return render(request, 'coaching/action_form.html', {'form': form, 'session': session}, status=400)


class CoachingActionUpdateView(CoachingManagerMixin, View):
    permission_required = 'coaching.change_coachingaction'
    http_method_names = ['get', 'post']

    def get_queryset(self, user):
        return visible_actions(user, CoachingAction.objects.select_related('session'))

    def get(self, request, pk):
        action = get_object_or_404(self.get_queryset(request.user), pk=pk)
        return render(request, 'coaching/action_form.html', {'form': CoachingActionUpdateForm(instance=action), 'session': action.session, 'action': action})

    def post(self, request, pk):
        action = get_object_or_404(self.get_queryset(request.user), pk=pk)
        if not (is_admin(request.user) or action.session.coach_id == request.user.pk):
            raise Http404
        form = CoachingActionUpdateForm(request.POST, instance=action)
        if form.is_valid():
            obj = form.save(commit=False); obj.full_clean(); obj.save()
            messages.success(request, 'Action et retour mis à jour.')
            return redirect(obj.session)
        return render(request, 'coaching/action_form.html', {'form': form, 'session': action.session, 'action': action}, status=400)


class CoachingActionProgressView(CoachingPermissionMixin, View):
    permission_required = 'coaching.change_coachingaction'
    http_method_names = ['post']

    def post(self, request, pk):
        action = get_object_or_404(visible_actions(request.user), pk=pk)
        if action.etudiant_id != request.user.pk or action.status == CoachingAction.Status.COMPLETED:
            raise Http404
        form = CoachingActionProgressForm(request.POST)
        target = form.data.get('status')
        transitions = {CoachingAction.Status.TODO: {CoachingAction.Status.IN_PROGRESS, CoachingAction.Status.COMPLETED},
                       CoachingAction.Status.IN_PROGRESS: {CoachingAction.Status.COMPLETED}}
        if not form.is_valid() or target not in transitions.get(action.status, set()):
            messages.error(request, 'Transition d’avancement invalide.')
            return redirect('coaching:learning_path')
        action.status = target
        action.completed_at = timezone.now() if target == CoachingAction.Status.COMPLETED else None
        action.full_clean(); action.save(update_fields=['status', 'completed_at', 'updated_at'])
        messages.success(request, 'Avancement enregistré.')
        return redirect('coaching:learning_path')
