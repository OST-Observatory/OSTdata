from django.urls import include, path

from rest_framework import routers

from .views import (
    RunViewSet,
    DataFileViewSet,
    getRunDataFile,
    getDashboardStats,
    get_visibility_plot,
    get_observing_conditions,
    get_sky_fov,
    get_time_distribution,
    get_bokeh_version,
    get_datafile_thumbnail,
    get_datafile_header,
    download_datafile,
    download_run_datafiles,
    download_datafiles_bulk,
    create_download_job_bulk,
    create_download_job,
    download_job_status,
    cancel_download_job,
    download_job_download,
)

app_name = 'runs-api'

router = routers.DefaultRouter()
router.register(r'runs', RunViewSet)
router.register(r'datafiles', DataFileViewSet)

urlpatterns = [
    path(
        'runs/<int:run_pk>/datafiles/',
        getRunDataFile,
        name='observation_run_datafiles',
    ),
    path(
        'runs/<int:run_pk>/conditions/',
        get_observing_conditions,
        name='observation_run_conditions',
    ),
    path('visibility/', get_visibility_plot, name='visibility_plot'),
    path('fov/', get_sky_fov, name='sky_fov'),
    path('time-distribution/', get_time_distribution, name='time_distribution'),
    path('bokeh-version/', get_bokeh_version, name='bokeh_version'),
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
    path('', include(router.urls) ),
]
