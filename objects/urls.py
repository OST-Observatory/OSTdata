from django.urls import path

from . import views

app_name = 'objects'
urlpatterns = [
    path('', views.objects_list, name='object_list'),
    path('<int:object_id>/', views.object_detail, name='object_detail'),
]
