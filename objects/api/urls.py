from django.urls import include, path

from rest_framework import routers

from .views import ObjectViewSet, getObjectRunViewSet, getObjectDatafileViewSet

app_name = 'objects-api'

router = routers.DefaultRouter()
router.register('', ObjectViewSet)

urlpatterns = [
    path('', include(router.urls) ),
    path(
        '<int:object_pk>/obsruns/',
        getObjectRunViewSet.as_view({'get': 'list'}),
        name='object_obsruns',
    ),
    path(
        '<int:object_pk>/datafiles/',
        getObjectDatafileViewSet.as_view({'get': 'list'}),
        name='object_datafiles',
    ),
]
