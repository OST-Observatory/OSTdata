from django.urls import path

from . import views

app_name = 'nights'
urlpatterns = [
    path('', views.night_list, name='night_list'),
    path('<int:night_id>/', views.night_detail, name='night_detail'),
]
