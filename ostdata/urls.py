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

from rest_framework import routers

from obs_run import views as run_views

router = routers.DefaultRouter()

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='dashboard')),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt",
            content_type="text/plain",
            ),
    ),
    path(
        'w/documentation/',
        TemplateView.as_view(template_name='documentation.html'),
        name='documentation',
    ),
    path('w/dashboard/', run_views.dashboard, name='dashboard'),
    path('w/runs/', include('obs_run.urls')),
    path('w/tags/', include('tags.urls')),
    path('w/objects/', include('objects.urls')),

    path('api/', include(router.urls), name='api'),
    path('api/runs/', include("obs_run.api.urls", namespace='runs-api') ),
    path('api/tags/', include("tags.api.urls", namespace='tags-api') ),
    path('api/objects/', include("objects.api.urls", namespace='objects-api') ),

    path(r'admin/', admin.site.urls),

    path('accounts/', include('django.contrib.auth.urls')),
]
