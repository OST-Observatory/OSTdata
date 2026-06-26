from .settings_base import *
from .settings_base import env  # make linter aware

# Load environment-specific settings (fail-safe default: development).
# Override with DJANGO_ENV=production in .env or the process environment.
_django_env = env('DJANGO_ENV', default='development').strip().lower()

if _django_env == 'production':
    from .settings_production import (
        DEBUG,
        ALLOWED_HOSTS,
        DATABASES,
        LOGGING,
        DEFAULT_FROM_EMAIL,
        FORCE_SCRIPT_NAME,
        CSRF_TRUSTED_ORIGINS,
    )
else:
    from .settings_development import DEBUG, ALLOWED_HOSTS, DATABASES, LOGGING
