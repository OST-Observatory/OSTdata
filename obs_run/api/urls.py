from django.urls import include, path

from rest_framework import routers

from .views import RunViewSet

app_name = 'runs-api'

router = routers.DefaultRouter()
#router.register(r'', StarViewSet)
router.register('', RunViewSet)

urlpatterns = [
   path('', include(router.urls) ),
]
