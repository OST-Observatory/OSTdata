from django.core.exceptions import ImproperlyConfigured

from .settings_base import *  # noqa: F403
from .settings_base import env  # make linter aware

# Load environment-specific settings. Only 'development' and 'production' are allowed.
# Override with DJANGO_ENV=production in .env or the process environment.
_ALLOWED_DJANGO_ENVS = frozenset({'development', 'production'})
_django_env = env('DJANGO_ENV', default='development').strip().lower()
if _django_env not in _ALLOWED_DJANGO_ENVS:
    raise ImproperlyConfigured(
        f"DJANGO_ENV must be 'development' or 'production', got {_django_env!r}."
    )

if _django_env == 'production':
    from . import settings_production as _env_settings
else:
    from . import settings_development as _env_settings

# Apply all uppercase settings from the environment module so production
# security flags (cookies, HSTS, renderers, …) are never skipped.
for _name, _value in vars(_env_settings).items():
    if _name.isupper():
        globals()[_name] = _value
