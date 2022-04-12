from django.urls import include, path

from rest_framework import routers

from .views import NightViewSet

app_name = 'nights-api'

router = routers.DefaultRouter()
#router.register(r'', StarViewSet)
router.register('', NightViewSet)

urlpatterns = [
   path('', include(router.urls) ),
]
