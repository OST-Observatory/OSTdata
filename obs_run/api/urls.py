from django.urls import include, path

from rest_framework import routers

from .views import (
    RunViewSet,
    DataFileViewSet,
    getRunDataFile,
    getDashboardStats
)

app_name = 'runs-api'

router = routers.DefaultRouter()
router.register(r'runs', RunViewSet)
router.register(r'datafiles', DataFileViewSet)

urlpatterns = [
    path('', include(router.urls) ),
    path(
        'runs/<int:run_pk>/datafiles/',
        getRunDataFile,
        name='observation_run_datafiles',
    ),
    path('dashboard/stats/', getDashboardStats, name='dashboard_stats'),
]
