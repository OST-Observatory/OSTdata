
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from objects.models import Object
from obs_run.models import ObservationRun


def user_login_required_for_edit(function):
   '''
   Decorator for views that checks that the logged in user is a student,
   redirects to the log-in page if necessary.
   '''

   def wrap(request, *args, **kwargs):

      run = get_object_or_404(ObservationRun, slug=kwargs.get('name', None))

      if run in request.user.readonly_runs.objects.all():
         raise PermissionDenied

      elif run in request.user.readwriteown_runs.objects.all():
         obj = Object.objects.get(pk=kwargs['star_id'])
         if getattr(obj, 'added_by', None) == request.user:
            return function(request, *args, **kwargs)
         else:
            raise PermissionDenied

      elif run in request.user.readwrite_runs.objects.all():
         return function(request, *args, **kwargs)

      else:
         raise PermissionDenied

   wrap.__doc__ = function.__doc__
   wrap.__name__ = function.__name__
   return wrap
