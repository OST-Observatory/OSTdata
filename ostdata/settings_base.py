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

# Plate Solving Configuration
PLATE_SOLVING_ENABLED = env.bool('PLATE_SOLVING_ENABLED', default=False)
PLATE_SOLVING_TOOLS = env.list('PLATE_SOLVING_TOOLS', default=['watney'])  # Ordered list
PLATE_SOLVING_FOV_MARGIN = env.float('PLATE_SOLVING_FOV_MARGIN', default=0.2)  # 20% margin
PLATE_SOLVING_MAX_RADIUS = env.float('PLATE_SOLVING_MAX_RADIUS', default=30.0)  # degrees
PLATE_SOLVING_MIN_RADIUS = env.float('PLATE_SOLVING_MIN_RADIUS', default=0.11)  # degrees
PLATE_SOLVING_TIMEOUT_SECONDS = env.int('PLATE_SOLVING_TIMEOUT_SECONDS', default=600)  # 10 minutes
PLATE_SOLVING_BATCH_SIZE = env.int('PLATE_SOLVING_BATCH_SIZE', default=10)  # Files per batch
# For nearby search: search radius in degrees around center coordinate (used when ra/dec known)
PLATE_SOLVING_NEARBY_SEARCH_RADIUS = env.float('PLATE_SOLVING_NEARBY_SEARCH_RADIUS', default=5.0)
# Re-evaluation: threshold (arcmin) for WCS vs header coord difference to trigger re-eval
PLATE_SOLVING_RE_EVAL_COORD_THRESHOLD_ARCMIN = env.float(
    'PLATE_SOLVING_RE_EVAL_COORD_THRESHOLD_ARCMIN', default=5.0
)
PLATE_SOLVING_RE_EVAL_BATCH_SIZE = env.int('PLATE_SOLVING_RE_EVAL_BATCH_SIZE', default=50)

# Watney-specific settings
WATNEY_SOLVE_PATH = env('WATNEY_SOLVE_PATH', default='watney-solve')
# Supported file formats for Watney (comma-separated, lowercase, without dot)
# Default: fits,fit,fts,tiff,tif (Watney does not support PNG)
WATNEY_SUPPORTED_FORMATS = env.list('WATNEY_SUPPORTED_FORMATS', default=['fits', 'fit', 'fts', 'tiff', 'tif'])

# Enable Celery Beat schedule for plate solving if enabled
if PLATE_SOLVING_ENABLED:
    CELERY_BEAT_SCHEDULE['plate_solve_pending_files'] = {
        'task': 'obs_run.tasks.plate_solve_pending_files',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
        'args': (),
    }
    CELERY_BEAT_SCHEDULE['re_evaluate_plate_solved_files'] = {
        'task': 'obs_run.tasks.re_evaluate_plate_solved_files',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
        'args': (),
    }

# Orphan Objects cleanup - removes Objects with no DataFiles (e.g. after special_targets removal)
if env.bool('ENABLE_ORPHAN_OBJECTS_CLEANUP', default=False):
    CELERY_BEAT_SCHEDULE['cleanup_orphan_objects'] = {
        'task': 'obs_run.tasks.cleanup_orphan_objects',
        'schedule': crontab(minute=0, hour='4'),  # Daily at 4:00
        'kwargs': {'dry_run': False},
    }

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
        from django_auth_ldap.config import LDAPSearch, GroupOfNamesType
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
        # Configure group type (required when using AUTH_LDAP_USER_FLAGS_BY_GROUP)
        # GroupOfNamesType works with memberOf attribute (standard LDAP/Active Directory)
        # Our custom memberUid support is handled separately in the populate_user hook
        AUTH_LDAP_GROUP_TYPE = GroupOfNamesType()
        
        # Configure group search if GROUP_SEARCH_BASE is set
        if AUTH_LDAP_GROUP_SEARCH_BASE:
            AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
                AUTH_LDAP_GROUP_SEARCH_BASE,
                ldap.SCOPE_SUBTREE,
                '(objectClass=groupOfNames)',
            )
        
        AUTH_LDAP_USER_FLAGS_BY_GROUP = {}
        if LDAP_GROUP_STAFF_DN:
            AUTH_LDAP_USER_FLAGS_BY_GROUP['is_staff'] = LDAP_GROUP_STAFF_DN
        if LDAP_GROUP_SUPERUSER_DN:
            AUTH_LDAP_USER_FLAGS_BY_GROUP['is_superuser'] = LDAP_GROUP_SUPERUSER_DN
        
        # Add memberUid support for all group types
        if LDAP_GROUP_STAFF_DN or LDAP_GROUP_SUPERUSER_DN or LDAP_GROUP_SUPERVISOR_DN or LDAP_GROUP_STUDENT_DN:
            from django_auth_ldap.backend import populate_user
            import os
            
            def _check_ldap_group_membership_via_memberuid(group_dn, user_uid, ldap_conn=None):
                """
                Check if a user is a member of a group via memberUid attribute.
                This is a fallback when memberOf is not available.
                
                Args:
                    group_dn: Distinguished Name of the group
                    user_uid: UID of the user to check
                    ldap_conn: Optional existing LDAP connection (will create one if not provided)
                
                Returns:
                    bool: True if user is a member, False otherwise
                """
                if not group_dn or not user_uid:
                    return False
                
                conn = ldap_conn
                should_close = False
                try:
                    if conn is None:
                        import ldap as ldap_module
                        from django.conf import settings as django_settings
                        server_uri = getattr(django_settings, 'AUTH_LDAP_SERVER_URI', None) or os.environ.get('LDAP_SERVER_URI')
                        if not server_uri:
                            return False
                        conn = ldap_module.initialize(server_uri)
                        conn.set_option(ldap_module.OPT_REFERRALS, 0)
                        start_tls = bool(getattr(django_settings, 'AUTH_LDAP_START_TLS', False) or str(os.environ.get('LDAP_START_TLS', 'false')).lower() in ('1', 'true', 'yes'))
                        if start_tls:
                            try:
                                conn.start_tls_s()
                            except Exception:
                                pass
                        bind_dn = getattr(django_settings, 'AUTH_LDAP_BIND_DN', None) or os.environ.get('LDAP_BIND_DN') or ''
                        bind_pw = getattr(django_settings, 'AUTH_LDAP_BIND_PASSWORD', None) or os.environ.get('LDAP_BIND_PASSWORD') or ''
                        try:
                            if bind_dn:
                                conn.simple_bind_s(bind_dn, bind_pw or '')
                            else:
                                conn.simple_bind_s()
                        except Exception:
                            return False
                        should_close = True
                    
                    # Try to read the group entry
                    try:
                        import ldap as ldap_module
                        attrs = ['memberUid']
                        result = conn.search_s(group_dn, ldap_module.SCOPE_BASE, '(objectClass=*)', attrs)
                        if result:
                            _, group_vals = result[0]
                            member_uids = group_vals.get('memberUid', [])
                            if member_uids:
                                # Convert bytes to strings if needed
                                member_uids_str = []
                                for uid in member_uids:
                                    try:
                                        uid_str = uid.decode('utf-8') if isinstance(uid, (bytes, bytearray)) else str(uid)
                                        member_uids_str.append(uid_str)
                                    except Exception:
                                        member_uids_str.append(str(uid))
                                # Check if user_uid is in the list
                                return user_uid in member_uids_str
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    if should_close and conn:
                        try:
                            conn.unbind_s()
                        except Exception:
                            pass
                return False
            
            def _ldap_sync_custom_flags(sender, user=None, ldap_user=None, **kwargs):
                try:
                    dns = set((ldap_user.group_dns or []))
                    dirty = False
                    
                    # Get user's UID for memberUid checks
                    user_uid = None
                    try:
                        user_uid = getattr(ldap_user, 'attrs', {}).get('uid', [None])[0]
                        if user_uid:
                            user_uid = user_uid.decode('utf-8') if isinstance(user_uid, (bytes, bytearray)) else str(user_uid)
                    except Exception:
                        pass
                    
                    # Try to get LDAP connection from ldap_user if available
                    ldap_conn = None
                    try:
                        if hasattr(ldap_user, '_connection'):
                            ldap_conn = ldap_user._connection
                    except Exception:
                        pass
                    
                    # Check is_staff via memberUid if configured
                    if LDAP_GROUP_STAFF_DN:
                        # First check memberOf (handled by django_auth_ldap, but we check here too)
                        new_val = any(d.lower() == LDAP_GROUP_STAFF_DN.lower() for d in dns)
                        # If not found via memberOf, try memberUid
                        if not new_val and user_uid:
                            new_val = _check_ldap_group_membership_via_memberuid(LDAP_GROUP_STAFF_DN, user_uid, ldap_conn)
                        if user.is_staff != new_val:
                            user.is_staff = new_val
                            dirty = True
                    
                    # Check is_superuser via memberUid if configured
                    if LDAP_GROUP_SUPERUSER_DN:
                        # First check memberOf (handled by django_auth_ldap, but we check here too)
                        new_val = any(d.lower() == LDAP_GROUP_SUPERUSER_DN.lower() for d in dns)
                        # If not found via memberOf, try memberUid
                        if not new_val and user_uid:
                            new_val = _check_ldap_group_membership_via_memberuid(LDAP_GROUP_SUPERUSER_DN, user_uid, ldap_conn)
                        if user.is_superuser != new_val:
                            user.is_superuser = new_val
                            dirty = True
                    
                    # Check is_supervisor via memberUid if configured
                    if LDAP_GROUP_SUPERVISOR_DN:
                        # First check memberOf
                        new_val = any(d.lower() == LDAP_GROUP_SUPERVISOR_DN.lower() for d in dns)
                        # If not found via memberOf, try memberUid
                        if not new_val and user_uid:
                            new_val = _check_ldap_group_membership_via_memberuid(LDAP_GROUP_SUPERVISOR_DN, user_uid, ldap_conn)
                        if getattr(user, 'is_supervisor', False) != new_val:
                            user.is_supervisor = new_val
                            dirty = True
                    
                    # Check is_student via memberUid if configured
                    if LDAP_GROUP_STUDENT_DN:
                        # First check memberOf
                        new_val = any(d.lower() == LDAP_GROUP_STUDENT_DN.lower() for d in dns)
                        # If not found via memberOf, try memberUid
                        if not new_val and user_uid:
                            new_val = _check_ldap_group_membership_via_memberuid(LDAP_GROUP_STUDENT_DN, user_uid, ldap_conn)
                        if getattr(user, 'is_student', False) != new_val:
                            user.is_student = new_val
                            dirty = True
                    
                    if dirty:
                        try:
                            update_fields = []
                            if LDAP_GROUP_STAFF_DN:
                                update_fields.append('is_staff')
                            if LDAP_GROUP_SUPERUSER_DN:
                                update_fields.append('is_superuser')
                            if LDAP_GROUP_SUPERVISOR_DN:
                                update_fields.append('is_supervisor')
                            if LDAP_GROUP_STUDENT_DN:
                                update_fields.append('is_student')
                            if update_fields:
                                user.save(update_fields=update_fields)
                        except Exception:
                            pass
                except Exception:
                    pass
            populate_user.connect(_ldap_sync_custom_flags)
except Exception:
    pass

# ML Model Configuration for Exposure Type Classification
ML_EXPOSURE_TYPE_MODEL_PATH = env('ML_EXPOSURE_TYPE_MODEL_PATH', default=None)
ML_EXPOSURE_TYPE_THRESHOLDS_PATH = env('ML_EXPOSURE_TYPE_THRESHOLDS_PATH', default=None)
ML_EXPOSURE_TYPE_TEMPERATURE = env.float('ML_EXPOSURE_TYPE_TEMPERATURE', default=0.7)
ML_EXPOSURE_TYPE_TTA = env.bool('ML_EXPOSURE_TYPE_TTA', default=False)
ML_EXPOSURE_TYPE_ABSTAIN_UNKNOWN = env.bool('ML_EXPOSURE_TYPE_ABSTAIN_UNKNOWN', default=True)
ML_EXPOSURE_TYPE_SUPPORTED_FORMATS = env.list('ML_EXPOSURE_TYPE_SUPPORTED_FORMATS', default=['FITS', 'TIFF'])
ML_EXPOSURE_TYPE_TARGET_SIZE = env.list('ML_EXPOSURE_TYPE_TARGET_SIZE', default=[448, 448])  # [width, height]
ML_EXPOSURE_TYPE_ENABLED = env.bool('ML_EXPOSURE_TYPE_ENABLED', default=False)

# Observatory Location Configuration for Solar System Object Detection
# These coordinates are used when FITS headers don't contain observatory location information
# Latitude and longitude should be in decimal degrees (latitude: -90 to 90, longitude: -180 to 180)
# Elevation should be in meters above sea level
OBSERVATORY_LATITUDE = env.float('OBSERVATORY_LATITUDE', default=None)
OBSERVATORY_LONGITUDE = env.float('OBSERVATORY_LONGITUDE', default=None)
OBSERVATORY_ELEVATION = env.float('OBSERVATORY_ELEVATION', default=0.0)  # meters

