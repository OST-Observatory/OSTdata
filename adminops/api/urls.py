from django.urls import path
from .views import (
    admin_health,
    admin_trigger_cleanup_downloads,
    admin_trigger_reconcile,
    admin_trigger_orphans_hashcheck,
    admin_get_banner,
    admin_set_banner,
    admin_clear_banner,
    banner_info,
)

app_name = 'adminops-api'

urlpatterns = [
    path('health/', admin_health, name='health'),
    path('maintenance/cleanup-downloads/', admin_trigger_cleanup_downloads, name='cleanup_downloads'),
    path('maintenance/reconcile/', admin_trigger_reconcile, name='reconcile'),
    path('maintenance/orphans-hashcheck/', admin_trigger_orphans_hashcheck, name='orphans_hashcheck'),
    path('banner/', admin_get_banner, name='get_banner'),
    path('banner/set', admin_set_banner, name='set_banner'),
    path('banner/clear', admin_clear_banner, name='clear_banner'),
    path('banner-info/', banner_info, name='banner_info'),
]




