from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from rest_framework import permissions

from objects.models import Object
from obs_run.models import ObservationRun
from ostdata.permissions import user_has_acl


class IsAllowedOnRun(permissions.BasePermission):
    """
    Custom permission to allow users to see/edit/add/remove objects only
    if they have permission to perform those actions for the observation
    runs this object belongs to.

    Note: only has_object_permission is implemented. Function-based views
    (@api_view) do not invoke this automatically; those endpoints must
    enforce access manually (e.g. can_read on the related run).
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
        if request.method == 'POST' and not request.user.is_anonymous:
            return request.user.can_add(subject)

        #   Check if the user is allowed to edit/delete this specific
        #   object
        if (request.method in ['PUT', 'PATCH', 'DELETE'] and not request.user.is_anonymous):
            return request.user.can_edit(subject)

        return False


def get_allowed_run_objects_to_view_for_user(qs, user):
    """
    Limit a DataFile queryset to files the user may see (via run visibility).
    """
    public = qs.filter(observation_run__is_public__exact=True)
    if user.is_anonymous:
        return public
    restricted = qs.filter(
        observation_run__pk__in=user.get_read_model(ObservationRun).values('pk')
    )
    if restricted.exists():
        return public | restricted
    return public


def get_allowed_runs_to_view_for_user(qs, user):
    """Limit an ObservationRun queryset to runs the user may see."""
    return get_allowed_model_to_view_for_user(qs, user, ObservationRun)


def get_allowed_objects_to_view_for_user(qs, user):
    """
    Limit an Object queryset.
    Anonymous / users without acl_objects_view_private: public only.
    Users with acl_objects_view_private: all objects.
    """
    if getattr(user, 'is_anonymous', True):
        return qs.filter(is_public=True)
    if user_has_acl(user, 'acl_objects_view_private'):
        return qs
    return qs.filter(is_public=True)


def get_allowed_model_to_view_for_user(qs, user, model):
    """
    Limit a queryset of models with is_public + per-user read membership
    (ObservationRun and similar).
    """
    public = qs.filter(is_public__exact=True)
    if user.is_anonymous:
        return public
    restricted = qs.filter(
        pk__in=user.get_read_model(model).values('pk')
    )
    if restricted.exists():
        return public | restricted
    return public


def user_can_view_run(user, run) -> bool:
    if run is None:
        return False
    if getattr(run, 'is_public', False):
        return True
    if getattr(user, 'is_anonymous', True):
        return False
    try:
        return bool(user.can_read(run))
    except Exception:
        return False


def user_can_view_object(user, obj) -> bool:
    if obj is None:
        return False
    if getattr(obj, 'is_public', False):
        return True
    if getattr(user, 'is_anonymous', True):
        return False
    return user_has_acl(user, 'acl_objects_view_private')


def get_run_for_user_or_404(user, pk):
    """Load ObservationRun by pk if visible; else raise Http404."""
    try:
        run = ObservationRun.objects.get(pk=pk)
    except ObservationRun.DoesNotExist:
        raise Http404
    if not user_can_view_run(user, run):
        raise Http404
    return run


def get_object_for_user_or_404(user, pk):
    """Load Object by pk if visible; else raise Http404."""
    try:
        obj = Object.objects.get(pk=pk)
    except Object.DoesNotExist:
        raise Http404
    if not user_can_view_object(user, obj):
        raise Http404
    return obj


def check_user_can_view_run(function):
    """
    Decorator that loads the function if the user is allowed to see the
    observation run, redirects to login page otherwise.
    """
    def wrapper(request, *args, **kwargs):
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
