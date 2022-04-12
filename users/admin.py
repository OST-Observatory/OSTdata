from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin


from .models import User



class CustomUserAdmin(UserAdmin):

   model = User

   list_display = [
       'username',
       'email',
       'first_name',
       'last_name',
       'is_active',
       'is_student',
       'is_superuser',
       'note',
       ]

   fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Extra Info', {'fields': ('first_name', 'last_name', 'note')}),
        ('Permissions', {'fields': (
            'is_superuser',
            'is_staff',
            'is_active',
            'is_student',
            )}),
   )

admin.site.register(User, CustomUserAdmin,)
