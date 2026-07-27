from pathlib import Path

import environ

env = environ.Env()
environ.Env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': env("DATABASE_NAME"),
        'USER': env("DATABASE_USER"),
        'PASSWORD': env("DATABASE_PASSWORD"),
        'HOST': env("DATABASE_HOST"),
        'PORT': env("DATABASE_PORT"),
    }
}

FORCE_SCRIPT_NAME = '/data_archive'
STATIC_URL = env('STATIC_URL', default=f"{FORCE_SCRIPT_NAME.rstrip('/')}/static/")

CSRF_TRUSTED_ORIGINS = env.list("TRUSTED_ORIGIN")

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{name}] {levelname} {module}:{lineno} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

# Security headers (production defaults)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
_cookie_path = env('SESSION_COOKIE_PATH', default='/data_archive')
SESSION_COOKIE_PATH = _cookie_path
CSRF_COOKIE_PATH = env('CSRF_COOKIE_PATH', default=_cookie_path)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

# TLS / HSTS (toggle via env when TLS terminates at reverse proxy).
# Enable SECURE_SSL_REDIRECT only after staging verifies X-Forwarded-Proto.
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
SECURE_PROXY_SSL_HEADER = (
    ('HTTP_X_FORWARDED_PROTO', 'https')
    if env.bool('SECURE_PROXY_SSL_HEADER', default=True)
    else None
)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)

# Production: JSON only (no browsable API HTML forms)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
        'ostdata.custom_permissions.IsAllowedOnRun',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '600/min',
        'plots': '30/min',
        'stats': '12/min',
        'jobs': '30/min',
        'login': '10/min',
        'password_change': '5/min',
        'thumbnails': '30/min',
    },
    'DATETIME_FORMAT': 'iso-8601',
    'EXCEPTION_HANDLER': 'ostdata.exception_handlers.custom_exception_handler',
}

# OpenAPI schema / Swagger / ReDoc: staff or superuser only in production
SPECTACULAR_SETTINGS = {
    'TITLE': 'OST Data Archive API',
    'DESCRIPTION': 'OpenAPI schema for the OST Data Archive REST API.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVE_PERMISSIONS': ['ostdata.permissions.IsAdminOrSuperuser'],
    'COMPONENT_SPLIT_REQUEST': True,
}

# Production LDAP must use ldaps:// or STARTTLS
_ldap_uri = env.str('LDAP_SERVER_URI', default='')
_ldap_start_tls = env.bool('LDAP_START_TLS', default=False)
if _ldap_uri:
    _uri_lower = _ldap_uri.strip().lower()
    if _uri_lower.startswith('ldap://') and not _ldap_start_tls:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "Production LDAP over ldap:// requires LDAP_START_TLS=true "
            "(or use ldaps://)."
        )
