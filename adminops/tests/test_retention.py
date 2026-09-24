"""Retention: history/audit entries lose the link to persons after PERSONAL_DATA_RETENTION_DAYS."""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from adminops.models import AuditLogEntry
from adminops.retention import PSEUDONYMISED, history_models, pseudonymise_personal_data
from obs_run.models import ObservationRun
from users.tasks import clear_expired_sessions

User = get_user_model()


@override_settings(PERSONAL_DATA_RETENTION_DAYS=730)
class PseudonymisePersonalDataTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.old = timezone.now() - timedelta(days=800)
        self.run = ObservationRun.objects.create(name='Run A', is_public=True)
        self.run.name = 'Run B'
        self.run.save()
        hist = ObservationRun.history.filter(id=self.run.pk).order_by('history_date')
        hist.update(history_user=self.admin)
        # First revision is old, second one recent.
        ObservationRun.history.filter(pk=hist.first().pk).update(history_date=self.old)

    def _audit(self, **kwargs):
        entry = AuditLogEntry.objects.create(
            model_type=kwargs.pop('model_type', 'acl'),
            model_label='x',
            action=kwargs.pop('action', 'updated'),
            user=self.admin,
            entity_label=kwargs.pop('entity_label', 'label'),
            **kwargs,
        )
        return entry

    def test_history_models_found(self):
        labels = {m._meta.label for m in history_models()}
        self.assertIn('obs_run.HistoricalObservationRun', labels)
        self.assertIn('objects.HistoricalObject', labels)

    def test_old_history_loses_user_recent_keeps_it(self):
        result = pseudonymise_personal_data()
        self.assertEqual(result['history'].get('obs_run.HistoricalObservationRun'), 1)
        rows = list(ObservationRun.history.filter(id=self.run.pk).order_by('history_date'))
        self.assertIsNone(rows[0].history_user_id)
        self.assertEqual(rows[0].name, 'Run A')  # content is kept
        self.assertEqual(rows[1].history_user_id, self.admin.pk)

    def test_old_audit_entries_lose_user(self):
        old_entry = self._audit()
        recent_entry = self._audit()
        AuditLogEntry.objects.filter(pk=old_entry.pk).update(created_at=self.old)

        result = pseudonymise_personal_data()

        self.assertEqual(result['audit_log'], 1)
        old_entry.refresh_from_db()
        recent_entry.refresh_from_db()
        self.assertIsNone(old_entry.user_id)
        self.assertEqual(old_entry.entity_label, 'label')
        self.assertEqual(recent_entry.user_id, self.admin.pk)

    def test_user_role_entries_drop_username_and_profile_values(self):
        entry = self._audit(
            model_type='user_role',
            entity_label='jdoe',
            summary='Updated user jdoe',
            changes=[
                {'field': 'email', 'old': 'a@example.org', 'new': 'b@example.org'},
                {'field': 'is_staff', 'old': False, 'new': True},
            ],
        )
        AuditLogEntry.objects.filter(pk=entry.pk).update(created_at=self.old)

        pseudonymise_personal_data()

        entry.refresh_from_db()
        self.assertEqual(entry.entity_label, PSEUDONYMISED)
        self.assertNotIn('jdoe', entry.summary)
        self.assertEqual(entry.changes[0], {'field': 'email', 'old': None, 'new': None})
        self.assertEqual(entry.changes[1], {'field': 'is_staff', 'old': False, 'new': True})

    def test_dry_run_changes_nothing(self):
        entry = self._audit()
        AuditLogEntry.objects.filter(pk=entry.pk).update(created_at=self.old)

        result = pseudonymise_personal_data(dry_run=True)

        self.assertEqual(result['audit_log'], 1)
        self.assertEqual(result['history'].get('obs_run.HistoricalObservationRun'), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.user_id, self.admin.pk)
        self.assertEqual(
            ObservationRun.history.filter(id=self.run.pk, history_user__isnull=True).count(), 0
        )

    def test_management_command_dry_run(self):
        out = StringIO()
        call_command('pseudonymise_audit_data', '--dry-run', stdout=out)
        self.assertIn('Would pseudonymise', out.getvalue())
        self.assertIn('obs_run.HistoricalObservationRun: 1', out.getvalue())


class ClearExpiredSessionsTest(TestCase):
    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.db')
    def test_expired_sessions_removed(self):
        expired = SessionStore()
        expired.create()
        active = SessionStore()
        active.create()
        Session.objects.filter(session_key=expired.session_key).update(
            expire_date=timezone.now() - timedelta(days=1)
        )

        clear_expired_sessions.apply()

        self.assertFalse(Session.objects.filter(session_key=expired.session_key).exists())
        self.assertTrue(Session.objects.filter(session_key=active.session_key).exists())
