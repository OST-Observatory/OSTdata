from django.urls import path
from .views import (
    admin_list_all_datafiles,
    admin_re_evaluate_datafiles,
    admin_re_evaluate_run,
    admin_link_datafiles_to_object,
    admin_health,
    admin_trigger_cleanup_downloads,
    admin_trigger_reconcile,
    admin_trigger_orphans_hashcheck,
    admin_trigger_scan_missing,
    admin_trigger_orphan_objects,
    admin_trigger_refresh_dashboard_stats,
    admin_trigger_plate_solve_task,
    admin_trigger_re_evaluate_plate_solved,
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
    admin_get_unsolved_plate_files,
    admin_trigger_plate_solve,
    admin_plate_solve_stats,
    admin_get_plate_solving_task_enabled,
    admin_set_plate_solving_task_enabled,
    admin_get_observation_runs_for_plate_solving,
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
    path('maintenance/plate-solving/', admin_trigger_plate_solve_task, name='trigger_plate_solve_task'),
    path('maintenance/re-evaluate-plate-solved/', admin_trigger_re_evaluate_plate_solved, name='trigger_re_evaluate_plate_solved'),
    path('runs/<int:run_id>/set-date/', admin_run_set_date, name='run_set_date'),
    path('runs/<int:run_id>/recompute-date/', admin_run_recompute_date, name='run_recompute_date'),
    path('runs/<int:run_id>/re-evaluate/', admin_re_evaluate_run, name='run_re_evaluate'),
    path('override-flags/<str:model_type>/<int:instance_id>/<str:field_name>/clear/', admin_clear_override_flag, name='clear_override_flag'),
    path('override-flags/<str:model_type>/<int:instance_id>/clear-all/', admin_clear_all_overrides, name='clear_all_overrides'),
    path('override-flags/list/', admin_list_override_flags, name='list_override_flags'),
    path('banner/', admin_get_banner, name='get_banner'),
    path('banner/set', admin_set_banner, name='set_banner'),
    path('banner/clear', admin_clear_banner, name='clear_banner'),
    path('banner-info/', banner_info, name='banner_info'),
    path('objects/<int:object_id>/update-identifiers/', admin_update_object_identifiers, name='update_object_identifiers'),
    # DataFiles list (all) and re-evaluate
    path('datafiles/', admin_list_all_datafiles, name='list_all_datafiles'),
    path('datafiles/re-evaluate/', admin_re_evaluate_datafiles, name='re_evaluate_datafiles'),
    path('datafiles/link-objects/', admin_link_datafiles_to_object, name='link_datafiles_to_object'),
    # Exposure type classification endpoints
    path('datafiles/discrepancies/', admin_get_exposure_type_discrepancies, name='exposure_type_discrepancies'),
    path('datafiles/<int:pk>/exposure-type-user/', admin_update_exposure_type_user, name='update_exposure_type_user'),
    # Spectrograph management endpoints
    path('datafiles/spectrograph/', admin_get_spectrograph_files, name='spectrograph_files'),
    path('datafiles/<int:pk>/spectrograph/', admin_update_spectrograph, name='update_spectrograph'),
    # Plate solving endpoints
    path('datafiles/plate-solving/unsolved/', admin_get_unsolved_plate_files, name='unsolved_plate_files'),
    path('datafiles/plate-solving/trigger/', admin_trigger_plate_solve, name='trigger_plate_solve'),
    path('datafiles/plate-solving/stats/', admin_plate_solve_stats, name='plate_solve_stats'),
    path('datafiles/plate-solving/task-enabled/', admin_get_plate_solving_task_enabled, name='plate_solving_task_enabled'),
    path('datafiles/plate-solving/task-enabled/set/', admin_set_plate_solving_task_enabled, name='set_plate_solving_task_enabled'),
    path('datafiles/plate-solving/observation-runs/', admin_get_observation_runs_for_plate_solving, name='observation_runs_for_plate_solving'),
]




