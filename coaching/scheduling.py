"""Timezone-aware appointment slot calculation and confirmation service.

Pending booking requests reserve their coach slot until approved, rejected, or
cancelled. A booking is checked both when requested and when approved.
SQLite transactions and uniqueness constraints prevent common duplicate submits,
but SQLite does not provide a portable exclusion constraint for overlapping
intervals. PostgreSQL should use a range exclusion constraint for hard
concurrent double-booking protection.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import BookingRequest, CoachAvailability, CoachAvailabilityException, SessionCoaching


TUNIS = ZoneInfo('Africa/Tunis')
SLOT_STEP_MINUTES = 15


def _intervals_conflict(coach, learner, start, end, exclude_request_id=None):
    participant_ids = [coach.pk]
    if learner is not None:
        participant_ids.append(learner.pk)
    sessions = SessionCoaching.objects.filter(
        Q(coach_id__in=participant_ids) | Q(etudiant_id__in=participant_ids),
        date_session__lt=end,
    ).exclude(statut=SessionCoaching.Statut.ANNULEE).only('date_session', 'duree')
    for session in sessions:
        session_end = session.date_session + timedelta(minutes=session.duree)
        if session.date_session < end and session_end > start:
            return True

    requests = BookingRequest.objects.filter(
        Q(coach_id__in=participant_ids) | Q(etudiant_id__in=participant_ids),
        status=BookingRequest.Status.PENDING,
        requested_start__lt=end,
    )
    if exclude_request_id:
        requests = requests.exclude(pk=exclude_request_id)
    for request in requests.only('requested_start', 'duration'):
        request_end = request.requested_start + timedelta(minutes=request.duration)
        if request.requested_start < end and request_end > start:
            return True
    return False


def available_slots(coach, day, duration, learner=None, exclude_request_id=None):
    """Return available local-time slots for one Tunisian calendar date."""
    if duration not in {30, 45, 60, 90} or day < timezone.localdate():
        return []
    windows = CoachAvailability.objects.filter(coach=coach, weekday=day.weekday(), is_active=True).order_by('start_time')
    exceptions = list(CoachAvailabilityException.objects.filter(
        coach=coach,
        start_datetime__lt=timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), TUNIS),
        end_datetime__gt=timezone.make_aware(datetime.combine(day, time.min), TUNIS),
    ).only('start_datetime', 'end_datetime'))
    results = []
    for window in windows:
        cursor = datetime.combine(day, window.start_time, tzinfo=TUNIS)
        window_end = datetime.combine(day, window.end_time, tzinfo=TUNIS)
        while cursor + timedelta(minutes=duration) <= window_end:
            end = cursor + timedelta(minutes=duration)
            blocked = any(exception.start_datetime < end and exception.end_datetime > cursor for exception in exceptions)
            if (cursor > timezone.now() and not blocked and
                    not _intervals_conflict(coach, learner, cursor, end, exclude_request_id)):
                results.append({'start': cursor, 'end': end, 'label': f'{cursor:%H:%M}–{end:%H:%M}'})
            cursor += timedelta(minutes=SLOT_STEP_MINUTES)
    return results


def reserve_booking(booking):
    """Create one confirmed session for a pending request, idempotently."""
    with transaction.atomic():
        locked = BookingRequest.objects.select_for_update().select_related('coach', 'etudiant', 'session').get(pk=booking.pk)
        if locked.status == BookingRequest.Status.APPROVED:
            return locked.session
        if locked.status != BookingRequest.Status.PENDING:
            raise ValidationError('Seule une demande en attente peut être approuvée.')
        local_start = timezone.localtime(locked.requested_start, TUNIS)
        slots = available_slots(
            locked.coach, local_start.date(), locked.duration, learner=locked.etudiant,
            exclude_request_id=locked.pk,
        )
        if not any(slot['start'] == local_start for slot in slots):
            raise ValidationError('Ce créneau n’est plus disponible selon les disponibilités ou les conflits actuels.')
        session = SessionCoaching(
            titre=locked.topic, date_session=locked.requested_start, duree=locked.duration,
            coach=locked.coach, etudiant=locked.etudiant, statut=SessionCoaching.Statut.PLANIFIEE,
        )
        session.full_clean()
        session.save()
        locked.session = session
        locked.status = BookingRequest.Status.APPROVED
        locked.full_clean()
        try:
            locked.save(update_fields=['session', 'status', 'updated_at'])
        except IntegrityError:
            raise ValidationError('Cette demande a déjà été confirmée.') from None
        return session
