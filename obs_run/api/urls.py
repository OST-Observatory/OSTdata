from django.urls import include, path
from rest_framework import routers

from adminops.api.views import banner_info

from .jobs import (
    batch_cancel_download_jobs,
    batch_expire_jobs_now,
    batch_extend_jobs_expiry,
    cancel_download_job,
    create_download_job,
    create_download_job_bulk,
    download_job_download,
    download_job_status,
    list_download_jobs,
)
from .runs import (
    RunViewSet,
    dark_finder_search,
    get_instrument_catalog,
    get_instruments,
    get_observing_conditions,
    get_run_aux_objects,
    get_sky_fov,
    get_time_distribution,
    get_visibility_plot,
    getDashboardStats,
    parse_fits_header,
)
from .views import (
    DataFileViewSet,
    download_datafile,
    download_datafiles_bulk,
    download_run_datafiles,
    get_datafile_header,
    get_datafile_thumbnail,
)

app_name = 'runs-api'

router = routers.DefaultRouter()
router.register(r'runs', RunViewSet)
router.register(r'datafiles', DataFileViewSet)

urlpatterns = [
    path(
        'runs/<int:run_pk>/conditions/',
        get_observing_conditions,
        name='observation_run_conditions',
    ),
    path(
        'runs/<int:pk>/aux-objects/',
        get_run_aux_objects,
        name='observation_run_aux_objects',
    ),
    path('visibility/', get_visibility_plot, name='visibility_plot'),
    path('fov/', get_sky_fov, name='sky_fov'),
    path('time-distribution/', get_time_distribution, name='time_distribution'),
    path('dashboard/stats/', getDashboardStats, name='dashboard_stats'),
    path('datafiles/<int:pk>/thumbnail/', get_datafile_thumbnail, name='datafile_thumbnail'),
    path('datafiles/<int:pk>/header/', get_datafile_header, name='datafile_header'),
    path('datafiles/<int:pk>/download/', download_datafile, name='datafile_download'),
    path('runs/<int:run_pk>/download/', download_run_datafiles, name='run_datafiles_download'),
    path('datafiles/download/', download_datafiles_bulk, name='datafiles_download_bulk'),
    path('datafiles/download-jobs/', create_download_job_bulk, name='download_job_create_bulk'),
    # Async download jobs
    path('runs/<int:run_pk>/download-jobs/', create_download_job, name='download_job_create'),
    path('jobs/<int:job_id>/status', download_job_status, name='download_job_status'),
    path('jobs/<int:job_id>/cancel', cancel_download_job, name='download_job_cancel'),
    path('jobs/<int:job_id>/download', download_job_download, name='download_job_download'),
    path('jobs/', list_download_jobs, name='download_job_list'),
    # Admin endpoints moved to adminops app under /api/admin/
    path('banner/', banner_info, name='banner_info'),
    # Admin batch job tools
    path('jobs/batch/cancel', batch_cancel_download_jobs, name='download_jobs_batch_cancel'),
    path('jobs/batch/extend-expiry', batch_extend_jobs_expiry, name='download_jobs_batch_extend_expiry'),
    path('jobs/batch/expire-now', batch_expire_jobs_now, name='download_jobs_batch_expire_now'),
    # Dark Finder endpoints
    path('dark-finder/', dark_finder_search, name='dark_finder_search'),
    path('parse-fits-header/', parse_fits_header, name='parse_fits_header'),
    path('instruments/', get_instruments, name='get_instruments'),
    path('instrument-catalog/', get_instrument_catalog, name='get_instrument_catalog'),
    path('', include(router.urls) ),
]
