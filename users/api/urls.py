from django.urls import path
from . import views

app_name = 'users-api'

urlpatterns = [
    path('auth/login/', views.login, name='login'),
    path('auth/logout/', views.logout, name='logout'),
    path('auth/user/', views.user_info, name='user_info'),
    path('auth/change-password/', views.change_password, name='change_password'),
] 