"""ostdata URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from rest_framework import routers

# Legacy server-rendered views have been removed

router = routers.DefaultRouter()

urlpatterns = [
    # Root: hand off to frontend (served separately) or keep as is
    path('', RedirectView.as_view(url='/')),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt",
            content_type="text/plain",
            ),
    ),
    # Removed legacy Django-rendered frontend routes under /w/*

    path('api/', include(router.urls), name='api'),
    path('api/runs/', include("obs_run.api.urls", namespace='runs-api')),
    path('api/admin/', include("adminops.api.urls", namespace='adminops-api')),
    path('api/tags/', include("tags.api.urls", namespace='tags-api')),
    path('api/objects/', include("objects.api.urls", namespace='objects-api')),
    path('api/users/', include("users.api.urls", namespace='users-api')),
    # OpenAPI schema and docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path(r'admin/', admin.site.urls),

    # Legacy Django auth routes removed; SPA handles authentication
]
