"""Regression tests for effective Django settings branching."""
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _probe(django_env: str, extra_env: dict | None = None) -> str:
    env = os.environ.copy()
    env.update({
        'PYTHONPATH': str(ROOT),
        'DJANGO_SETTINGS_MODULE': 'ostdata.settings',
        'DJANGO_ENV': django_env,
        'SECRET_KEY': 'audit-only-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        'ALLOWED_HOSTS': 'example.org',
        'TRUSTED_ORIGIN': 'https://example.org',
        'DATABASE_NAME': 'audit',
        'DATABASE_USER': 'audit',
        'DATABASE_PASSWORD': 'audit',
        'DATABASE_HOST': 'localhost',
        'DATABASE_PORT': '5432',
        'DEFAULT_FROM_EMAIL': 'audit@example.com',
        'LDAP_SERVER_URI': '',
    })
    if extra_env:
        env.update(extra_env)
    code = (
        'import django; django.setup(); from django.conf import settings; '
        'print(settings.SESSION_COOKIE_SECURE); '
        'print(settings.CSRF_COOKIE_SECURE); '
        'print(settings.SECURE_HSTS_SECONDS); '
        'print(settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]); '
        'print(settings.SPECTACULAR_SETTINGS.get("SERVE_PERMISSIONS")); '
        'print(settings.DEBUG)'
    )
    proc = subprocess.run(
        [PYTHON, '-c', code],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc.stdout.strip()


class SettingsSecurityTest(SimpleTestCase):
    def test_production_applies_secure_cookies_and_renderers(self):
        out = _probe('production')
        lines = out.splitlines()
        self.assertEqual(lines[0], 'True')
        self.assertEqual(lines[1], 'True')
        self.assertEqual(lines[2], '31536000')
        self.assertIn('JSONRenderer', lines[3])
        self.assertNotIn('BrowsableAPIRenderer', lines[3])
        self.assertIn('IsAdminOrSuperuser', lines[4])
        self.assertEqual(lines[5], 'False')

    def test_development_keeps_insecure_cookies(self):
        out = _probe('development')
        lines = out.splitlines()
        self.assertEqual(lines[0], 'False')
        self.assertEqual(lines[1], 'False')
        self.assertEqual(lines[5], 'True')

    def test_unknown_django_env_raises(self):
        env = os.environ.copy()
        env.update({
            'PYTHONPATH': str(ROOT),
            'DJANGO_SETTINGS_MODULE': 'ostdata.settings',
            'DJANGO_ENV': 'staging',
            'SECRET_KEY': 'audit-only-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        })
        proc = subprocess.run(
            [PYTHON, '-c', 'import django; django.setup()'],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('DJANGO_ENV', proc.stderr)
