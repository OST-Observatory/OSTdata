from django.urls import include, path

from rest_framework import routers

from .views import ObjectViewSet, getObjectRunViewSet, getObjectDatafileViewSet, ObjectVuetifyViewSet
from .solar_image_views import object_solar_image

app_name = 'objects-api'

router = routers.DefaultRouter()
router.register('', ObjectViewSet)

urlpatterns = [
    path(
        'vuetify', 
        ObjectVuetifyViewSet.as_view({'get': 'list'}),
        name='object-vuetify-list',
    ),
    path(
        '<int:pk>/solar-image/',
        object_solar_image,
        name='object_solar_image',
    ),
    path('', include(router.urls)),
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
