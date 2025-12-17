"""
Django settings base for ostdata project (shared across environments).
"""
from pathlib import Path
import platform
import environ

# Initialise environment variables
env = environ.Env()
environ.Env.read_env()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# Application definition
INSTALLED_APPS = [
    'obs_run.apps.RunConfig',
    'users.apps.UsersConfig',
    'tags.apps.TagsConfig',
    'objects.apps.ObjectsConfig',
    'adminops.apps.AdminopsConfig',
    'drf_spectacular',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'simple_history',
    'corsheaders',
    'django_celery_results',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'ostdata.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
        'ostdata.custom_permissions.IsAllowedOnRun',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
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
    },
    'DATETIME_FORMAT': 'iso-8601',
}

# drf-spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'OST Data Archive API',
    'DESCRIPTION': 'OpenAPI schema for the OST Data Archive REST API.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVE_PERMISSIONS': [],
    'COMPONENT_SPLIT_REQUEST': True,
}

LOGIN_URL = '/login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

WSGI_APPLICATION = 'ostdata.wsgi.application'

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = env('STATIC_URL', default='/static/')
STATIC_ROOT = BASE_DIR / 'static/'
STATICFILES_DIRS = []
_site_static = BASE_DIR / 'site_static'
_frontend_dist = BASE_DIR / 'frontend' / 'dist'
if _site_static.exists():
    STATICFILES_DIRS.append(str(_site_static))
if _frontend_dist.exists():
    STATICFILES_DIRS.append(str(_frontend_dist))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery
from celery.schedules import crontab
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=False)
CELERY_TASK_EAGER_PROPAGATES = env.bool('CELERY_TASK_EAGER_PROPAGATES', default=True)
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default='redis://localhost:6379/1')
CELERY_RESULT_EXTENDED = True
CELERY_BEAT_SCHEDULE = {}
if env.bool('ENABLE_FS_RECONCILE', default=False):
    CELERY_BEAT_SCHEDULE['reconcile_filesystem'] = {
        'task': 'obs_run.tasks.reconcile_filesystem',
        'schedule': crontab(minute=0, hour='3'),
        'args': (),
    }
if env.bool('ENABLE_DOWNLOAD_CLEANUP', default=False):
    CELERY_BEAT_SCHEDULE['cleanup_expired_downloads'] = {
        'task': 'obs_run.tasks.cleanup_expired_downloads',
        'schedule': crontab(minute='15', hour='*/1'),
        'args': (),
    }
if env.bool('ENABLE_DASHBOARD_STATS_REFRESH', default=False):
    # Pre-compute dashboard stats in background (default: every 30 min)
    CELERY_BEAT_SCHEDULE['refresh_dashboard_stats'] = {
        'task': 'obs_run.tasks.refresh_dashboard_stats',
        'schedule': crontab(minute='*/30'),
        'args': (),
    }

DOWNLOAD_JOB_TTL_HOURS = env.int('DOWNLOAD_JOB_TTL_HOURS', default=72)

# CORS
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type', 'dnt',
    'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]

# Optional LDAP scaffolding
AUTH_LDAP_SERVER_URI = env.str('LDAP_SERVER_URI', default='')
AUTH_LDAP_START_TLS = env.bool('LDAP_START_TLS', default=False)
AUTH_LDAP_BIND_DN = env.str('LDAP_BIND_DN', default='')
AUTH_LDAP_BIND_PASSWORD = env.str('LDAP_BIND_PASSWORD', default='')
AUTH_LDAP_USER_SEARCH_BASE = env.str('LDAP_USER_SEARCH_BASE', default='')
AUTH_LDAP_GROUP_SEARCH_BASE = env.str('LDAP_GROUP_SEARCH_BASE', default='')
AUTH_LDAP_CONNECT_TIMEOUT = env.int('LDAP_CONNECT_TIMEOUT', default=5)
AUTH_LDAP_USER_FILTER = env.str('LDAP_USER_FILTER', default='(uid=%(user)s)')
LDAP_GROUP_STAFF_DN = env.str('LDAP_GROUP_STAFF_DN', default='')
LDAP_GROUP_SUPERUSER_DN = env.str('LDAP_GROUP_SUPERUSER_DN', default='')
LDAP_GROUP_SUPERVISOR_DN = env.str('LDAP_GROUP_SUPERVISOR_DN', default='')
LDAP_GROUP_STUDENT_DN = env.str('LDAP_GROUP_STUDENT_DN', default='')

try:
    if AUTH_LDAP_SERVER_URI:
        import ldap  # type: ignore
        from django_auth_ldap.config import LDAPSearch
        AUTHENTICATION_BACKENDS = (
            'django_auth_ldap.backend.LDAPBackend',
            'django.contrib.auth.backends.ModelBackend',
        )
        AUTH_LDAP_CONNECTION_OPTIONS = {
            ldap.OPT_NETWORK_TIMEOUT: AUTH_LDAP_CONNECT_TIMEOUT,
        }
        if AUTH_LDAP_BIND_DN:
            AUTH_LDAP_BIND_DN = AUTH_LDAP_BIND_DN
            AUTH_LDAP_BIND_PASSWORD = AUTH_LDAP_BIND_PASSWORD
        AUTH_LDAP_ALWAYS_UPDATE_USER = True
        if AUTH_LDAP_USER_SEARCH_BASE:
            AUTH_LDAP_USER_SEARCH = LDAPSearch(
                AUTH_LDAP_USER_SEARCH_BASE,
                ldap.SCOPE_SUBTREE,
                AUTH_LDAP_USER_FILTER,
            )
        AUTH_LDAP_USER_ATTR_MAP = {
            'first_name': 'givenName',
            'last_name': 'sn',
            'email': 'mail',
        }
        AUTH_LDAP_USER_FLAGS_BY_GROUP = {}
        if LDAP_GROUP_STAFF_DN:
            AUTH_LDAP_USER_FLAGS_BY_GROUP['is_staff'] = LDAP_GROUP_STAFF_DN
        if LDAP_GROUP_SUPERUSER_DN:
            AUTH_LDAP_USER_FLAGS_BY_GROUP['is_superuser'] = LDAP_GROUP_SUPERUSER_DN
        if LDAP_GROUP_SUPERVISOR_DN or LDAP_GROUP_STUDENT_DN:
            from django_auth_ldap.backend import populate_user
            def _ldap_sync_custom_flags(sender, user=None, ldap_user=None, **kwargs):
                try:
                    dns = set((ldap_user.group_dns or []))
                    dirty = False
                    if LDAP_GROUP_SUPERVISOR_DN:
                        new_val = any(d.lower() == LDAP_GROUP_SUPERVISOR_DN.lower() for d in dns)
                        if getattr(user, 'is_supervisor', False) != new_val:
                            user.is_supervisor = new_val
                            dirty = True
                    if LDAP_GROUP_STUDENT_DN:
                        new_val = any(d.lower() == LDAP_GROUP_STUDENT_DN.lower() for d in dns)
                        if getattr(user, 'is_student', False) != new_val:
                            user.is_student = new_val
                            dirty = True
                    if dirty:
                        try:
                            user.save(update_fields=['is_supervisor', 'is_student'])
                        except Exception:
                            pass
                except Exception:
                    pass
            populate_user.connect(_ldap_sync_custom_flags)
except Exception:
    pass

