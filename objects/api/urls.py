from django.urls import include, path

from rest_framework import routers

from .views import ObjectViewSet, getObjectRunViewSet, getObjectDatafileViewSet

app_name = 'objects-api'

router = routers.DefaultRouter()
router.register('', ObjectViewSet)

urlpatterns = [
    path('', include(router.urls) ),
    path(
        '<int:object_pk>/observation_runs/',
        getObjectRunViewSet.as_view({'get': 'list'}),
        name='object_observation_runs',
    ),
    path(
        '<int:object_pk>/datafiles/',
        getObjectDatafileViewSet.as_view({'get': 'list'}),
        name='object_datafiles',
    ),
]
