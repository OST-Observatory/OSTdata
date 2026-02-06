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
    admin_clear_override_flag,
    admin_clear_all_overrides,
    admin_list_override_flags,
    admin_get_banner,
    admin_set_banner,
    admin_clear_banner,
    banner_info,
    admin_update_object_identifiers,
    admin_get_exposure_type_discrepancies,
    admin_update_exposure_type_user,
    admin_get_spectrograph_files,
    admin_update_spectrograph,
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
    path('override-flags/<str:model_type>/<int:instance_id>/<str:field_name>/clear/', admin_clear_override_flag, name='clear_override_flag'),
    path('override-flags/<str:model_type>/<int:instance_id>/clear-all/', admin_clear_all_overrides, name='clear_all_overrides'),
    path('override-flags/list/', admin_list_override_flags, name='list_override_flags'),
    path('banner/', admin_get_banner, name='get_banner'),
    path('banner/set', admin_set_banner, name='set_banner'),
    path('banner/clear', admin_clear_banner, name='clear_banner'),
    path('banner-info/', banner_info, name='banner_info'),
    path('objects/<int:object_id>/update-identifiers/', admin_update_object_identifiers, name='update_object_identifiers'),
    # Exposure type classification endpoints
    path('datafiles/discrepancies/', admin_get_exposure_type_discrepancies, name='exposure_type_discrepancies'),
    path('datafiles/<int:pk>/exposure-type-user/', admin_update_exposure_type_user, name='update_exposure_type_user'),
    # Spectrograph management endpoints
    path('datafiles/spectrograph/', admin_get_spectrograph_files, name='spectrograph_files'),
    path('datafiles/<int:pk>/spectrograph/', admin_update_spectrograph, name='update_spectrograph'),
]




