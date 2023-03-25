from django.urls import path

from . import views

app_name = 'obs_runs'
urlpatterns = [
    path('', views.obs_run_list, name='run_list'),
    path('<int:run_id>/', views.obs_run_detail, name='run_detail'),
]
