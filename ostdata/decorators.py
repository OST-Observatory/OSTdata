
from django.shortcuts import get_object_or_404

from night.models import Night

def user_login_required_for_edit(function):
   '''
   Decorator for views that checks that the logged in user is a student,
   redirects to the log-in page if necessary.
   '''

   def wrap(request, *args, **kwargs):

      night = get_object_or_404(Night, slug=kwargs.get('name', None))

      if night in request.user.readonly_nights.objects.all():
         raise PermissionDenied

      elif night in request.user.readwriteown_nights.objects.all():
         if Star.objects.get(pk=kwargs['star_id']).added_by == request.user:
            return function(request, *args, **kwargs)
         else:
            raise PermissionDenied

      elif night in request.user.readwrite_nights.objects.all():
         return function(request, *args, **kwargs)

      else:
         raise PermissionDenied

   wrap.__doc__ = function.__doc__
   wrap.__name__ = function.__name__
   return wrap
