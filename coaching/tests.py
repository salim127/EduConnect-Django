from datetime import datetime, timedelta, timezone as datetime_timezone
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test import Client, override_settings
from django.urls import reverse

from accounts.roles import LEARNER, TEACHER
from .models import ConseilPedagogique, SessionCoaching
from .forms import ConseilPedagogiqueForm, SessionCoachingForm


class CoachingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, role in [('coach', TEACHER), ('coach2', TEACHER), ('student', LEARNER), ('student2', LEARNER)]:
            user = get_user_model().objects.create_user(username=name)
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
            setattr(cls, name, user)

    def setUp(self):
        self.now = datetime(2030, 1, 10, 12, tzinfo=datetime_timezone.utc)
        clock = patch('coaching.models.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def session(self, **changes):
        values = dict(titre='Méthodologie', date_session=self.now + timedelta(days=1), duree=60, coach=self.coach, etudiant=self.student)
        values.update(changes)
        return SessionCoaching(**values)

    def persisted_session(self, **changes):
        session = self.session(**changes)
        session.full_clean()
        session.save()
        return session

    def advice(self, session, **changes):
        values = dict(titre='Révisions', description='Réviser régulièrement.', type_conseil='organisation', session=session)
        values.update(changes)
        return ConseilPedagogique(**values)

    def assertInvalid(self, obj, field):
        with self.assertRaises(ValidationError) as error:
            obj.full_clean()
        self.assertIn(field, error.exception.message_dict)

    def test_valid_session_creation_and_reverse_relations(self):
        session = self.persisted_session()
        self.assertEqual(session.statut, SessionCoaching.Statut.PLANIFIEE)
        self.assertEqual(self.coach.sessions_coachees.get(), session)
        self.assertEqual(self.student.sessions_coaching.get(), session)

    def test_valid_advice_creation_and_relation(self):
        session = self.persisted_session()
        advice = self.advice(session)
        advice.full_clean()
        advice.save()
        self.assertEqual(session.conseils.get(), advice)
        self.assertIsNotNone(advice.date_creation)

    def test_required_session_fields(self):
        for field, value in [('titre', ''), ('date_session', None), ('duree', None), ('coach', None), ('etudiant', None), ('statut', '')]:
            with self.subTest(field=field):
                self.assertInvalid(self.session(**{field: value}), field)

    def test_required_advice_fields(self):
        session = self.persisted_session()
        for field, value in [('titre', ''), ('description', ''), ('type_conseil', ''), ('session', None)]:
            with self.subTest(field=field):
                self.assertInvalid(self.advice(session, **{field: value}) if field != 'session' else self.advice(None), field)

    def test_duration_validation(self):
        for duration in [0, -1, 'incorrect', 10**20]:
            with self.subTest(duration=duration):
                self.assertInvalid(self.session(duree=duration), 'duree')

    def test_database_positive_duration_constraint(self):
        session = self.persisted_session()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SessionCoaching.objects.filter(pk=session.pk).update(duree=0)

    def test_participant_roles(self):
        self.assertInvalid(self.session(coach=self.student2), 'coach')
        self.assertInvalid(self.session(etudiant=self.coach2), 'etudiant')

    def test_inactive_participants(self):
        for field, user in [('coach', self.coach), ('etudiant', self.student)]:
            with self.subTest(field=field):
                user.is_active = False
                user.save()
                self.assertInvalid(self.session(), field)
                user.is_active = True
                user.save()

    def test_same_participant_rejected_even_with_both_roles(self):
        self.coach.groups.add(Group.objects.get(name=LEARNER))
        self.assertInvalid(self.session(etudiant=self.coach), 'etudiant')

    def test_nonexistent_participant(self):
        session = self.session()
        session.coach_id = 999999
        self.assertInvalid(session, 'coach')

    def test_new_past_or_present_planned_session_rejected(self):
        for delta in [timedelta(days=-1), timedelta(0)]:
            self.assertInvalid(self.session(date_session=self.now + delta), 'date_session')

    def test_naive_and_invalid_dates_rejected(self):
        self.assertInvalid(self.session(date_session=self.now.replace(tzinfo=None)), 'date_session')
        self.assertInvalid(self.session(date_session='incorrect'), 'date_session')

    def test_overlap_for_coach_and_student_in_another_timezone(self):
        original = self.persisted_session()
        start = (original.date_session + timedelta(minutes=30)).astimezone(ZoneInfo('Africa/Tunis'))
        self.assertInvalid(self.session(date_session=start, etudiant=self.student2), 'date_session')
        self.assertInvalid(self.session(date_session=start, coach=self.coach2), 'date_session')

    def test_overlap_before_inside_and_enclosing_existing_session(self):
        original = self.persisted_session()
        for offset, duration in [(-30, 60), (15, 10), (-30, 120), (0, 60)]:
            with self.subTest(offset=offset, duration=duration):
                self.assertInvalid(self.session(date_session=original.date_session + timedelta(minutes=offset), duree=duration), 'date_session')

    def test_different_participants_can_share_a_time(self):
        self.persisted_session()
        self.persisted_session(coach=self.coach2, etudiant=self.student2)
        self.assertEqual(SessionCoaching.objects.count(), 2)

    def test_adjacent_sessions_do_not_overlap(self):
        original = self.persisted_session()
        self.persisted_session(date_session=original.date_session - timedelta(hours=1))
        self.persisted_session(date_session=original.date_session + timedelta(hours=1))

    def test_cancelled_sessions_ignored_in_both_directions(self):
        self.persisted_session(statut='annulee')
        self.persisted_session()
        self.persisted_session(statut='annulee')

    def test_reactivating_cancelled_session_checks_overlap(self):
        cancelled = self.persisted_session(statut='annulee')
        self.persisted_session()
        cancelled.statut = 'planifiee'
        self.assertInvalid(cancelled, 'date_session')

    def test_update_excludes_current_session_but_checks_others(self):
        session = self.persisted_session()
        session.titre = 'Titre corrigé'
        session.full_clean()
        session.save()
        other = self.persisted_session(date_session=session.date_session + timedelta(hours=2))
        session.date_session = other.date_session
        self.assertInvalid(session, 'date_session')

    def test_historical_title_and_closure_remain_editable(self):
        session = self.persisted_session()
        with patch('coaching.models.timezone.now', return_value=self.now + timedelta(days=2)):
            session.titre = 'Titre corrigé'
            session.full_clean()
            session.save()
            session.statut = 'terminee'
            session.full_clean()
            session.save()

    def test_historical_schedule_and_participants_are_frozen(self):
        session = self.persisted_session(date_session=self.now - timedelta(days=1), statut='terminee')
        for field, value in [('duree', 30), ('coach', self.coach2), ('etudiant', self.student2), ('date_session', self.now + timedelta(days=1))]:
            with self.subTest(field=field):
                session.refresh_from_db()
                setattr(session, field, value)
                self.assertInvalid(session, 'date_session')

    def test_historical_session_cannot_be_replanned_in_the_past(self):
        session = self.persisted_session(date_session=self.now - timedelta(days=1), statut='annulee')
        session.statut = 'planifiee'
        self.assertInvalid(session, 'date_session')

    def test_finished_session_requires_end_in_the_past(self):
        self.assertInvalid(self.session(statut='terminee'), 'statut')
        self.assertInvalid(self.session(statut='terminee', date_session=self.now - timedelta(minutes=30)), 'statut')
        self.persisted_session(statut='terminee', date_session=self.now - timedelta(hours=1))

    def test_finished_sessions_still_block_historical_overlap(self):
        start = self.now - timedelta(days=1)
        self.persisted_session(statut='terminee', date_session=start)
        self.assertInvalid(self.session(statut='terminee', date_session=start), 'date_session')

    def test_advice_cascades_on_session_deletion(self):
        session = self.persisted_session()
        advice = self.advice(session)
        advice.full_clean()
        advice.save()
        session.delete()
        self.assertFalse(ConseilPedagogique.objects.filter(pk=advice.pk).exists())

    def test_both_users_are_protected_from_deletion(self):
        session = self.persisted_session()
        for user in [self.coach, self.student]:
            with self.assertRaises(ProtectedError):
                user.delete()
        self.assertTrue(SessionCoaching.objects.filter(pk=session.pk).exists())

    def test_whitespace_content_rejected(self):
        session = self.persisted_session()
        self.assertInvalid(self.session(titre=' \t\n'), 'titre')
        for field in ['titre', 'description']:
            self.assertInvalid(self.advice(session, **{field: ' \t\n\u00a0'}), field)

    def test_invalid_choices_rejected(self):
        self.assertInvalid(self.session(statut='inconnu'), 'statut')
        self.assertInvalid(self.advice(self.persisted_session(), type_conseil='inconnu'), 'type_conseil')

    def test_string_representations(self):
        session = self.session()
        self.assertEqual(str(session), 'Méthodologie')
        self.assertEqual(str(self.advice(session)), 'Révisions')

    def test_migration_matches_models(self):
        call_command('makemigrations', 'coaching', check=True, dry_run=True, stdout=StringIO())

    def test_admin_uses_model_validation(self):
        admin = get_user_model().objects.create_superuser(username='root', email='root@example.test', password='test-password')
        self.client.force_login(admin)
        response = self.client.post(reverse('admin:coaching_sessioncoaching_add'), {
            'titre': 'Invalide', 'date_session_0': '2030-01-11', 'date_session_1': '13:00:00',
            'duree': 0, 'statut': 'planifiee', 'coach': self.coach.pk, 'etudiant': self.student.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SessionCoaching.objects.exists())
        self.assertIn('duree', response.context['adminform'].form.errors)

    def test_student_has_no_admin_access_or_coaching_write_permissions(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('admin:coaching_sessioncoaching_add')).status_code, 302)
        self.assertFalse(self.student.has_perm('coaching.add_sessioncoaching'))


class CoachingCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.roles import ADMIN
        from accounts.roles import ensure_system_roles
        ensure_system_roles()
        cls.groups = {name: Group.objects.get(name=name) for name in (ADMIN, TEACHER, LEARNER)}
        cls.admin = get_user_model().objects.create_user(username='business-admin')
        cls.admin.groups.add(cls.groups[ADMIN])
        cls.coach = get_user_model().objects.create_user(username='crud-coach')
        cls.coach.groups.add(cls.groups[TEACHER])
        cls.coach2 = get_user_model().objects.create_user(username='other-coach')
        cls.coach2.groups.add(cls.groups[TEACHER])
        cls.student = get_user_model().objects.create_user(username='crud-student')
        cls.student.groups.add(cls.groups[LEARNER])
        cls.student2 = get_user_model().objects.create_user(username='other-student')
        cls.student2.groups.add(cls.groups[LEARNER])

    def setUp(self):
        self.now = datetime(2030, 1, 10, 12, tzinfo=datetime_timezone.utc)
        clock = patch('coaching.models.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def url(self, name, pk=None):
        return reverse('coaching:' + name, args=[pk] if pk is not None else [])

    def make_session(self, **kwargs):
        data = dict(titre='Suivi Python', date_session=self.now + timedelta(days=1), duree=60,
                    statut='planifiee', coach=self.coach, etudiant=self.student)
        data.update(kwargs)
        obj = SessionCoaching(**data)
        obj.full_clean()
        obj.save()
        return obj

    def make_advice(self, session, **kwargs):
        data = dict(titre='Conseil utile', description='Réviser par étapes.',
                    type_conseil='methode', session=session)
        data.update(kwargs)
        obj = ConseilPedagogique(**data)
        obj.full_clean()
        obj.save()
        return obj

    def login(self, user):
        self.client.force_login(user)

    def test_role_permissions_are_added_and_existing_custom_rights_survive_role_edit(self):
        custom = Permission.objects.get(content_type__app_label='objectifs', codename='update_statut_tacheapprentissage')
        self.groups[LEARNER].permissions.add(custom)
        # Simule post_migrate et l'actualisation des rôles déjà créés.
        from accounts.roles import ensure_system_roles
        ensure_system_roles()
        self.groups[LEARNER].refresh_from_db()
        self.assertTrue(self.groups[LEARNER].permissions.filter(pk=custom.pk).exists())
        self.assertTrue(self.groups[LEARNER].permissions.filter(codename='view_sessioncoaching').exists())
        self.assertFalse(self.groups[LEARNER].permissions.filter(codename='add_sessioncoaching').exists())
        self.assertTrue(self.groups[TEACHER].permissions.filter(codename='add_sessioncoaching').exists())
        self.assertTrue(self.groups['Administrateur'].permissions.filter(codename='delete_conseilpedagogique').exists())

        from accounts.forms import RoleForm
        displayed = list(RoleForm(instance=self.groups[LEARNER]).fields['permissions'].queryset)
        form = RoleForm(data={'name': LEARNER, 'permissions': [str(p.pk) for p in displayed
                       if p.codename == 'view_sessioncoaching']}, instance=self.groups[LEARNER])
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertTrue(self.groups[LEARNER].permissions.filter(pk=custom.pk).exists())

    def test_role_form_displays_coaching_crud_permissions(self):
        from accounts.forms import RoleForm
        form = RoleForm(instance=self.groups[TEACHER])
        self.assertIn(('coaching', 'sessioncoaching'), __import__('accounts.forms', fromlist=['PERM_MODELS']).PERM_MODELS)
        codes = set(form.fields['permissions'].queryset.values_list('codename', flat=True))
        self.assertTrue({'add_sessioncoaching', 'view_conseilpedagogique'} <= codes)

    def test_anonymous_is_redirected_from_crud_and_demo_routes_remain(self):
        for name, pk in [('session_list', None), ('conseil_list', None), ('session_create', None),
                         ('session_detail', 9999), ('conseil_detail', 9999)]:
            response = self.client.get(self.url(name, pk))
            self.assertEqual(response.status_code, 302, name)
        self.assertEqual(self.client.get(self.url('sessions')).status_code, 302)
        self.assertEqual(self.client.get(self.url('conseils')).status_code, 302)

    def test_teacher_session_crud_and_learner_read_only(self):
        self.login(self.coach)
        create = {'titre': 'Séance créée', 'date_session': '2030-01-11T14:00:00', 'duree': 45,
                  'etudiant': self.student.pk, 'coach': self.coach2.pk, 'statut': 'annulee'}
        response = self.client.post(self.url('session_create'), create)
        self.assertEqual(response.status_code, 302)
        session = SessionCoaching.objects.get(titre='Séance créée')
        self.assertEqual(session.coach, self.coach)
        self.assertEqual(session.statut, 'planifiee')
        self.assertEqual(session.etudiant, self.student)

        response = self.client.post(self.url('session_update', session.pk), {
            'titre': 'Séance modifiée', 'date_session': '2030-01-11T14:00:00', 'duree': 45,
            'etudiant': self.student.pk, 'coach': self.coach2.pk, 'statut': 'annulee'})
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.titre, 'Séance modifiée')
        self.assertEqual(session.coach, self.coach)
        self.assertEqual(session.statut, 'planifiee')

        advice = self.make_advice(session)
        advice_data = {'titre': 'Conseil modifié', 'description': 'Texte modifié', 'type_conseil': 'organisation', 'session': session.pk}
        self.assertEqual(self.client.post(self.url('conseil_update', advice.pk), advice_data).status_code, 302)
        advice.refresh_from_db()
        self.assertEqual(advice.titre, 'Conseil modifié')
        self.assertEqual(self.client.post(self.url('conseil_delete', advice.pk)).status_code, 302)
        self.assertFalse(ConseilPedagogique.objects.filter(pk=advice.pk).exists())

        self.login(self.student)
        self.assertEqual(self.client.get(self.url('session_list')).status_code, 200)
        self.assertContains(self.client.get(self.url('session_detail', session.pk)), session.titre)
        self.assertEqual(self.client.get(self.url('session_create')).status_code, 403)
        self.assertEqual(self.client.get(self.url('session_update', session.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url('session_delete', session.pk)).status_code, 403)
        self.assertEqual(self.client.get(self.url('conseil_detail', advice.pk)).status_code, 404)

    def test_admin_can_read_all_and_manage_sessions_and_advice(self):
        own = self.make_session(titre='Séance du coach courant')
        other = self.make_session(coach=self.coach2, etudiant=self.student2, titre='Séance privée du second coach')
        advice = self.make_advice(other, titre='Conseil du coach voisin')
        self.login(self.admin)
        self.assertContains(self.client.get(self.url('session_list')), own.titre)
        self.assertContains(self.client.get(self.url('session_list')), other.titre)
        self.assertEqual(self.client.post(self.url('session_update', other.pk), {
            'titre': 'Admin modifie', 'date_session': '2030-01-12T12:00:00', 'duree': 60,
            'coach': self.coach2.pk, 'etudiant': self.student2.pk}).status_code, 302)
        self.assertEqual(self.client.post(self.url('conseil_update', advice.pk), {
            'titre': 'Admin conseil', 'description': 'Description.', 'type_conseil': 'methode', 'session': other.pk}).status_code, 302)
        self.assertEqual(self.client.post(self.url('conseil_delete', advice.pk)).status_code, 302)

    def test_coach_and_learner_see_only_their_assigned_records(self):
        own = self.make_session(titre='Session du coach courant')
        other = self.make_session(coach=self.coach2, etudiant=self.student2, titre='Session du coach voisin')
        advice = self.make_advice(other, titre='Conseil du coach voisin')
        self.login(self.coach)
        response = self.client.get(self.url('session_list'))
        self.assertContains(response, own.titre)
        self.assertNotContains(response, other.titre)
        self.assertEqual(self.client.get(self.url('session_detail', other.pk)).status_code, 404)
        self.assertEqual(self.client.get(self.url('conseil_detail', advice.pk)).status_code, 404)
        self.login(self.student)
        own_advice = self.make_advice(own)
        self.assertContains(self.client.get(self.url('conseil_list')), own_advice.titre)
        self.assertNotContains(self.client.get(self.url('conseil_list')), advice.titre)
        self.assertEqual(self.client.get(self.url('conseil_detail', advice.pk)).status_code, 404)

    def test_forged_foreign_keys_and_advice_sessions_are_rejected(self):
        self.login(self.coach)
        response = self.client.post(self.url('session_create'), {
            'titre': 'Falsifiée', 'date_session': '2030-01-11T14:00:00', 'duree': 45,
            'etudiant': self.coach2.pk, 'coach': self.coach2.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SessionCoaching.objects.filter(titre='Falsifiée').exists())

        foreign = self.make_session(coach=self.coach2, etudiant=self.student2)
        response = self.client.post(self.url('conseil_create'), {
            'titre': 'Conseil injecté', 'description': 'Texte.', 'type_conseil': 'methode', 'session': foreign.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConseilPedagogique.objects.filter(titre='Conseil injecté').exists())
        self.assertFalse(ConseilPedagogiqueForm(user=self.student).fields['session'].queryset.exists())

    def test_search_and_filters_stay_inside_user_scope(self):
        own = self.make_session(titre='Python individuel')
        self.make_session(coach=self.coach2, etudiant=self.student2, titre='Python secret')
        self.login(self.coach)
        self.assertContains(self.client.get(self.url('session_list'), {'q': 'Python', 'statut': 'planifiee'}), own.titre)
        self.assertNotContains(self.client.get(self.url('session_list'), {'q': 'secret'}), 'Python secret')
        advice = self.make_advice(own, titre='Conseil organisation')
        self.assertContains(self.client.get(self.url('conseil_list'), {'q': 'organisation', 'type': 'methode'}), advice.titre)

    def test_status_transitions_are_post_only_owned_and_one_way(self):
        own = self.make_session()
        other = self.make_session(coach=self.coach2, etudiant=self.student2)
        self.login(self.coach)
        url = self.url('session_status', own.pk)
        self.assertEqual(self.client.get(url).status_code, 405)
        before = own.statut
        self.assertEqual(self.client.post(url, {'statut': 'planifiee'}).status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.statut, before)
        self.assertEqual(self.client.post(self.url('session_status', other.pk), {'statut': 'annulee'}).status_code, 404)
        self.assertEqual(self.client.post(url, {'statut': 'annulee'}).status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.statut, 'annulee')
        self.assertEqual(self.client.post(url, {'statut': 'terminee'}).status_code, 404)

        finished = self.make_session(titre='Fin prochaine')
        with patch('coaching.models.timezone.now', return_value=finished.date_session + timedelta(hours=1)):
            self.assertEqual(self.client.post(self.url('session_status', finished.pk), {'statut': 'terminee'}).status_code, 302)
        finished.refresh_from_db()
        self.assertEqual(finished.statut, 'terminee')

    def test_deletes_and_status_require_post_and_delete_is_confirmed_by_form(self):
        session = self.make_session()
        advice = self.make_advice(session)
        self.login(self.coach)
        self.assertEqual(self.client.get(self.url('session_delete', session.pk)).status_code, 405)
        self.assertEqual(self.client.get(self.url('conseil_delete', advice.pk)).status_code, 405)
        self.assertContains(self.client.get(self.url('session_detail', session.pk)), 'data-bs-target="#deleteModal"')
        self.assertEqual(self.client.post(self.url('session_delete', session.pk)).status_code, 302)
        self.assertFalse(SessionCoaching.objects.filter(pk=session.pk).exists())
        self.assertFalse(ConseilPedagogique.objects.filter(pk=advice.pk).exists())

    def test_completed_or_cancelled_session_cannot_be_edited_or_deleted_by_coach(self):
        session = self.make_session(statut='annulee')
        self.login(self.coach)
        self.assertEqual(self.client.get(self.url('session_update', session.pk)).status_code, 404)
        self.assertEqual(self.client.post(self.url('session_delete', session.pk)).status_code, 404)

    def test_forms_validate_and_use_bootstrap_widgets(self):
        self.assertTrue(SessionCoachingForm(user=self.coach).fields['coach'].disabled)
        self.assertFalse(SessionCoachingForm(user=self.admin).fields['coach'].disabled)
        self.assertEqual(list(SessionCoachingForm(user=self.coach).fields['etudiant'].queryset), [self.student, self.student2])
        self.assertIn('form-control', SessionCoachingForm(user=self.coach).fields['titre'].widget.attrs['class'])
        self.assertFalse(SessionCoachingForm(data={'titre': 'x', 'date_session': '2030-01-11T14:00', 'duree': 0,
                      'etudiant': self.student.pk, 'coach': self.coach.pk}, user=self.coach).is_valid())

    def test_csrf_enforced_for_mutations(self):
        session = self.make_session()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.coach)
        response = strict.post(self.url('session_status', session.pk), {'statut': 'annulee'})
        self.assertEqual(response.status_code, 403)
        session.refresh_from_db()
        self.assertEqual(session.statut, 'planifiee')

    def test_existing_demo_url_names_and_pages_are_preserved(self):
        self.login(self.coach)
        self.assertEqual(reverse('coaching:sessions'), '/coaching/sessions/')
        self.assertEqual(reverse('coaching:conseils'), '/coaching/conseils/')
        self.assertContains(self.client.get(self.url('sessions'), {'month': '2030-01'}), 'Calendrier du coaching')
        self.assertContains(self.client.get(self.url('conseils')), 'Démonstration')

    def test_dashboard_statistics_are_real_and_scoped_by_role(self):
        own = self.make_session(date_session=self.now + timedelta(days=2))
        self.make_session(titre='Finished item', statut='terminee', date_session=self.now - timedelta(days=2))
        self.make_advice(own)
        foreign = self.make_session(coach=self.coach2, etudiant=self.student2, titre='Private item')
        self.make_advice(foreign, titre='Private advice')

        self.login(self.coach)
        response = self.client.get(self.url('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_sessions'], 2)
        self.assertEqual(response.context['upcoming_count'], 1)
        self.assertEqual(response.context['completed_count'], 1)
        self.assertEqual(response.context['advice_count'], 1)
        self.assertEqual(response.context['next_session'], own)
        self.assertNotContains(response, 'Private item')

        self.login(self.student)
        student_response = self.client.get(self.url('dashboard'))
        self.assertEqual(student_response.context['total_sessions'], 2)
        self.assertNotContains(student_response, 'Private advice')

        self.login(self.admin)
        admin_response = self.client.get(self.url('dashboard'))
        self.assertEqual(admin_response.context['total_sessions'], 3)
        self.assertEqual(admin_response.context['advice_count'], 2)

    def test_calendar_navigation_multiple_sessions_and_invalid_month(self):
        first = self.make_session(titre='Calendar item A', date_session=self.now + timedelta(days=1))
        second = self.make_session(titre='Calendar item B',
                                   date_session=self.now + timedelta(days=1, hours=3))
        self.make_session(titre='Secret calendar item', coach=self.coach2, etudiant=self.student2,
                          date_session=self.now + timedelta(days=2))
        self.login(self.coach)
        response = self.client.get(self.url('sessions'), {'month': '2030-01'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first.titre)
        self.assertContains(response, second.titre)
        self.assertNotContains(response, 'Secret calendar item')
        self.assertContains(response, f'href="{first.get_absolute_url()}"')
        self.assertContains(response, '?month=2029-12')
        self.assertContains(response, '?month=2030-02')

        invalid = self.client.get(self.url('sessions'), {'month': 'not-a-month'})
        self.assertEqual(invalid.status_code, 200)
        self.assertTrue(invalid.context['calendar_error'])

    def test_calendar_groups_sessions_by_africa_tunis_local_date(self):
        # 23:30 UTC on Jan 31 is 00:30 on Feb 1 in Tunis.
        session = self.make_session(titre='Month boundary', date_session=datetime(
            2030, 1, 31, 23, 30, tzinfo=datetime_timezone.utc))
        self.login(self.coach)
        response = self.client.get(self.url('sessions'), {'month': '2030-02'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, session.titre)
        self.assertEqual(response.context['sessions_count'], 1)

    def test_lists_paginate_preserve_filters_and_reject_invalid_parameters_safely(self):
        sessions = []
        for index in range(11):
            sessions.append(self.make_session(
                titre=f'Pagination {index:02d}', date_session=self.now + timedelta(days=index + 1),
                coach=self.coach, etudiant=self.student))
        advice = []
        for index, session in enumerate(sessions):
            advice.append(self.make_advice(session, titre=f'Advice pagination {index:02d}'))

        self.login(self.coach)
        page = self.client.get(self.url('session_list'), {
            'q': 'Pagination', 'statut': 'incorrect', 'page': 'abc'})
        self.assertEqual(page.status_code, 200, page.content[:1000])
        self.assertEqual(len(page.context['page_obj']), 9)
        self.assertTrue(page.context['filter_errors'])
        self.assertContains(page, 'page=2')
        self.assertContains(page, 'q=Pagination')
        bad_dates = self.client.get(self.url('session_list'), {
            'date_debut': 'not-a-date', 'date_fin': '2030-01-01'})
        self.assertEqual(bad_dates.status_code, 200)
        self.assertTrue(bad_dates.context['filter_errors'])

        self.login(self.admin)
        admin_filtered = self.client.get(self.url('session_list'), {
            'q': 'Pagination', 'date_debut': '2030-01-15', 'date_fin': '2030-01-15',
            'coach': str(self.coach.pk), 'etudiant': str(self.student.pk)})
        self.assertEqual(admin_filtered.status_code, 200)
        self.assertEqual(admin_filtered.context['paginator'].count, 1)

        ConseilPedagogique.objects.filter(pk=advice[0].pk).update(
            date_creation=datetime(2030, 1, 10, 14, tzinfo=datetime_timezone.utc))
        advice_filtered = self.client.get(self.url('conseil_list'), {
            'q': advice[0].titre, 'type': 'methode', 'session': str(sessions[0].pk),
            'date_debut': '2030-01-10', 'date_fin': '2030-01-10'})
        self.assertEqual(advice_filtered.status_code, 200)
        self.assertEqual(advice_filtered.context['paginator'].count, 1)

        advice_page = self.client.get(self.url('conseil_list'), {'q': 'Advice pagination', 'page': '999'})
        self.assertEqual(advice_page.status_code, 200)
        self.assertEqual(len(advice_page.context['page_obj']), 1)
        self.assertContains(advice_page, 'page=1')
        invalid_session = self.client.get(self.url('conseil_list'), {'session': '999999'})
        self.assertEqual(invalid_session.status_code, 200)
        self.assertTrue(invalid_session.context['filter_errors'])

    def test_form_cannot_make_foreign_session_available_by_forged_id(self):
        foreign = self.make_session(coach=self.coach2, etudiant=self.student2)
        form = ConseilPedagogiqueForm(data={'titre': 'Interdit', 'description': 'x', 'type_conseil': 'methode',
                                           'session': foreign.pk}, user=self.coach)
        self.assertFalse(form.is_valid())
