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
    get_datafile_thumbnail,
    download_datafile,
    download_run_datafiles,
    download_datafiles_bulk,
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
    path('dashboard/stats/', getDashboardStats, name='dashboard_stats'),
    path('datafiles/<int:pk>/thumbnail/', get_datafile_thumbnail, name='datafile_thumbnail'),
    path('datafiles/<int:pk>/download/', download_datafile, name='datafile_download'),
    path('runs/<int:run_pk>/download/', download_run_datafiles, name='run_datafiles_download'),
    path('datafiles/download/', download_datafiles_bulk, name='datafiles_download_bulk'),
    path('', include(router.urls) ),
]
