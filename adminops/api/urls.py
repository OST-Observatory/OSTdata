from django.urls import path
from .views import (
    admin_health,
    admin_trigger_cleanup_downloads,
    admin_trigger_reconcile,
    admin_trigger_orphans_hashcheck,
    admin_trigger_scan_missing,
    admin_trigger_orphan_objects,
    admin_trigger_refresh_dashboard_stats,
    admin_run_set_date,
    admin_run_recompute_date,
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
    path('maintenance/scan-missing/', admin_trigger_scan_missing, name='scan_missing'),
    path('maintenance/orphan-objects/', admin_trigger_orphan_objects, name='orphan_objects'),
    path('maintenance/refresh-dashboard-stats/', admin_trigger_refresh_dashboard_stats, name='refresh_dashboard_stats'),
    path('runs/<int:run_id>/set-date/', admin_run_set_date, name='run_set_date'),
    path('runs/<int:run_id>/recompute-date/', admin_run_recompute_date, name='run_recompute_date'),
    path('banner/', admin_get_banner, name='get_banner'),
    path('banner/set', admin_set_banner, name='set_banner'),
    path('banner/clear', admin_clear_banner, name='clear_banner'),
    path('banner-info/', banner_info, name='banner_info'),
]




