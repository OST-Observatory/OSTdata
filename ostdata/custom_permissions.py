
from django.shortcuts import redirect
from django.contrib import messages
from rest_framework import permissions

from obs_run.models import ObservationRun


class IsAllowedOnRun(permissions.BasePermission):
    """
        Custom permission to allow users to see/edit/add/remove objects only
        if they have permission to perform those actions for the observation
        runs this object belongs to.
    """

    def has_object_permission(self, request, view, obj):
        # Resolve the permission subject: for DataFile use its observation_run
        subject = getattr(obj, 'observation_run', obj)

        # Show the object if the user is allowed to see the associated run/object
        # (GET, HEAD or OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_anonymous:
                return getattr(subject, 'is_public', False)
            else:
                return request.user.can_read(subject)

        #   User can add objects to this observation run?
        if request.method == ['POST'] and not request.user.is_anonymous:
            return request.user.can_add(subject)

        #   Check if the user is allowed to edit/delete this specific
        #   object
        if (request.method in ['PUT', 'PATCH', 'DELETE'] and not request.user.is_anonymous):
            return request.user.can_edit(subject)


        return False


def get_allowed_run_objects_to_view_for_user(qs, user):
    """
    Function that will limit the provided queryset to the objects that
    the provided user can see.

    This filtering is based on the observation runs that the object belongs too.
    An anonymous user can see objects from all public runs. A logged
    in user can also see private runs that he/she has viewing rights
    for.

    (for some reason qs1.union(qs2) can not be used here instead of
    using th | operator!!!)
    """

    #   Check if the observation run is public
    public = qs.filter(observation_run__is_public__exact=True)

    #   Check if user is logged in ...
    if user.is_anonymous:
        #   ... return the "public" queryset if not
        return public
    else:
        #   Check if user is allowed to view the observation run ...
        restricted = qs.filter(
            observation_run__pk__in=user.get_read_model(ObservationRun).values('pk')
            )
        if len(restricted) > 0:
            #   ... if this is the case return the specific queryset ...
            return restricted
        else:
            #   ... if not, return the public queryset
            return public
#
#
# def get_allowed_runs_to_view_for_user(qs, user):
#     """
#     Function that will limit the provided queryset to observation runs that
#     the provided user can see.
#
#     An anonymous user can see objects from all public runs. A logged
#     in user can also see private runs that he/she has viewing rights
#     for.
#     """
#
#     #   Check if the observation run is public
#     public = qs.filter(is_public__exact=True)
#
#     #   Check if user is logged in ...
#     if user.is_anonymous:
#         #   ... return the "public" queryset if not
#         return public
#     else:
#         #   Check if user is allowed to view the observation run ...
#         restricted = qs.filter(
#             pk__in=user.get_read_runs().values('pk')
#             )
#         if len(restricted) > 0:
#             #   ... if this is the case return the specific queryset ...
#             return restricted
#         else:
#             #   ... if not, return the public queryset
#             return public



def get_allowed_model_to_view_for_user(qs, user, model):
    """
    Function that will limit the provided queryset to objects that
    the provided user can see.

    An anonymous user can see objects from all public runs. A logged
    in user can also see private runs that he/she has viewing rights
    for.
    """

    #   Check if the object is public
    public = qs.filter(is_public__exact=True)

    #   Check if user is logged in ...
    if user.is_anonymous:
        #   ... return the "public" queryset if not
        return public
    else:
        #   Check if user is allowed to view the object ...
        restricted = qs.filter(
            pk__in=user.get_read_model(model).values('pk')
            )
        if len(restricted) > 0:
            #   ... if this is the case return the specific queryset ...
            return restricted
        else:
            #   ... if not, return the public queryset
            return public

def check_user_can_view_run(function):
    """
        Decorator that loads the function if the user is allowed to see the
        observation run, redirects to login page otherwise.
    """
    def wrapper(request, *args, **kwargs):
        user = request.user
        try:
            run = ObservationRun.objects.get(pk=kwargs['run_id'])
        except Exception:
            messages.error(request, "That page requires login to view")
            return redirect('login')

        if request.user.is_anonymous and run.is_public:
            return function(request, *args, **kwargs)
        elif not request.user.is_anonymous and request.user.can_read(run):
            return function(request, *args, **kwargs)
        else:
            messages.error(
                request,
                "ObservationRun: {} requires login to see".format(run),
            )
            return redirect('login')

    return wrapper
