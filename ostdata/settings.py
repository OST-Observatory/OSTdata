from .settings.base import *
from .settings.base import env  # make linter aware
import platform  # make linter aware

# Load specific settings for development or production
if env("DEVICE") in platform.node():
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
