from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'users-api'

urlpatterns = [
    path('auth/login/', views.login, name='login'),
    path('auth/logout/', views.logout, name='logout'),
    path('auth/user/', views.user_info, name='user_info'),
    path('auth/change-password/', views.change_password, name='change_password'),
] 

# Admin router (admin-only user management)
router = DefaultRouter()
router.register(r'users', views.UserAdminViewSet, basename='admin-users')

urlpatterns += [
    path('admin/', include(router.urls)),
    path('admin/ldap/test/', views.admin_ldap_test, name='admin_ldap_test'),
    path('admin/acl/', views.admin_acl_get, name='admin_acl_get'),
    path('admin/acl/set', views.admin_acl_set, name='admin_acl_set'),
]