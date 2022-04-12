from django.urls import include, path
from rest_framework import routers

from .views import TagViewSet

app_name = 'tags-api'

router = routers.DefaultRouter()
#router.register(r'', TagViewSet)
router.register('', TagViewSet)

urlpatterns = [
   path('', include(router.urls) ),
]
