from django.db import models

from django.contrib.auth.models import AbstractUser

# from obs_run import models as run_models

# from objects import models as object_models
# from objects.models import Objects

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

   # def get_read_runs(self):
   #    if self.is_superuser:
   #       return run_models.ObservationRun.objects.all()
   #    else:
   #       return self.readonly_users.all().union(self.readwrite_users.all())

   def get_read_model(self, model):
      if self.is_superuser:
         return model.objects.all()
         # return object_models.Objects.objects.all()
      else:
         return self.readonly_users.all().union(self.readwrite_users.all())


   def can_read(self, run):
      """
      Returns True if this user has read access to entries of this observation
      run
      """

      if run.is_public or self.is_superuser:
         #  Public observation runs can be read by everyone
         return True
      elif run in self.readonly_users.all() or \
           run in self.readwrite_users.all():
         #  Specific observation run might require read access
         return True
      else:
         return False

   def can_add(self, run):
      """
      Returns True if this user can add new entries to this observation run
      """

      if self.is_superuser:
         return True
      elif run in self.readwrite_users.all():
         return True
      else:
         return False

   def can_edit(self, obj):
      """
      Returns True if this user can edit this specific observation run
      """
      if self.is_superuser:
         return True
      elif obj.run in self.readwrite_users.all():
         return True
      else:
         return False

   def can_delete(self, obj):
      """
      Returns True if this user can delete this specific observation run
      """
      if self.is_superuser:
         return True
      elif obj.run in self.readwrite_users.all() and \
           obj.added_by == self:
         return True
      elif obj.run in self.managed_projects.all():
         return True
      else:
         return False
