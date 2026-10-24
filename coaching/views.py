import calendar
from datetime import date, datetime, time, timedelta

from django.views.generic import TemplateView
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from accounts.roles import is_admin
from config.mixins import QueryStringMixin

from .access import is_manager, managed_sessions, visible_sessions
from . import demo
from .forms import ConseilPedagogiqueForm, SessionCoachingForm
from .models import ConseilPedagogique, SessionCoaching

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

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        selected = _parse_month(self.request.GET.get('month'))
        if selected is None:
            selected = timezone.localdate().replace(day=1)
            ctx['calendar_error'] = 'Mois invalide. Le mois courant est affiché.'
        start, end = _month_window(selected)
        sessions = visible_sessions(
            self.request.user,
            SessionCoaching.objects.select_related('coach', 'etudiant').filter(
                date_session__gte=start, date_session__lt=end
            ),
        )
        by_day = {}
        for session in sessions:
            local_start = timezone.localtime(session.date_session)
            by_day.setdefault(local_start.day, []).append(session)
        today = timezone.localdate()
        weeks = []
        for week in calendar.Calendar(firstweekday=0).monthdayscalendar(selected.year, selected.month):
            weeks.append([{'n': number, 'sessions': by_day.get(number, []),
                           'today': bool(number and selected.year == today.year and selected.month == today.month and number == today.day)}
                          for number in week])
        previous = (selected - timedelta(days=1)).replace(day=1)
        next_month = (selected.replace(day=28) + timedelta(days=4)).replace(day=1)
        ctx.update(weeks=weeks, mois=f'{MOIS[selected.month]} {selected.year}', selected_month=selected,
                   today=today, sessions_count=sum(map(len, by_day.values())),
                   previous_url=_month_url(previous), next_url=_month_url(next_month),
                   can_manage=is_manager(self.request.user))
        return ctx


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
                       can_transition=manager and obj.statut == SessionCoaching.Statut.PLANIFIEE)
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
        )
        return context


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
