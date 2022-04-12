from django.db import models

from django.contrib.auth.models import AbstractUser

from night import models as night_models

def get_sentinel_user():
   """
   Sets a default 'deleted' user if the user is deleted.
   """
   return User().objects.get_or_create(username='deleted')[0]

def get_unknown_user():
   """
   Gets the unknown user to be used as a default for the added_by field
   """
   return User().objects.get_or_create(username='unknown')[0]



class User(AbstractUser):

   is_student = models.BooleanField(default=False)

   note = models.TextField(default='')

   def get_read_nights(self):
      if self.is_superuser:
         return night_models.Night.objects.all()
      else:
         return self.readonly_users.all().union(self.readwrite_users.all())

   def can_read(self, night):
      """
      Returns True if this user has read access to entries of this night
      """

      if night.is_public or self.is_superuser:
         #  Public nights can be read by everyone
         return True
      elif night in self.readonly_users.all() or \
           night in self.readwrite_users.all():
         #  Specific night might require read access
         return True
      else:
         return False

   def can_add(self, night):
      """
      Returns True if this user can add new entries to this night
      """

      if self.is_superuser:
         return True
      elif night in self.readwrite_users.all():
         return True
      else:
         return False

   def can_edit(self, obj):
      """
      Returns True if this user can edit this specific night
      """
      if self.is_superuser:
         return True
      elif obj.night in self.readwrite_users.all():
         return True
      else:
         return False

   def can_delete(self, obj):
      """
      Returns True if this user can delete this specific night
      """
      if self.is_superuser:
         return True
      elif obj.night in self.readwrite_users.all() and \
           obj.added_by == self:
         return True
      elif obj.night in self.managed_projects.all():
         return True
      else:
         return False
