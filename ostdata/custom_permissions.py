
from django.shortcuts import redirect
from django.contrib import messages
from rest_framework import permissions

from night.models import Night


class IsAllowedOnNight(permissions.BasePermission):
    """
        Custom permission to allow users to see/edit/add/remove objects only
        if they have permission to perform those actions for the night this
        object belongs to.
    """

    def has_object_permission(self, request, view, obj):

        #     Show the object if the user is allowed to see this night
        #     (GET, HEAD or OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_anonymous:
                #return obj.night.is_public
                return obj.is_public
            else:
                #return request.user.can_read(obj.night)
                return request.user.can_read(obj)

        #   User can add objects to this night?
        if request.method == ['POST'] and not request.user.is_anonymous:
            #return request.user.can_add(obj.night)
            return request.user.can_add(obj)

        #   Check if the user is allowed to edit/delete this specific
        #   object
        if (request.method in ['PUT', 'PATCH', 'DELETE']
            and not request.user.is_anonymous):
            return request.user.can_edit(obj)


        return False


def get_allowed_objects_to_view_for_user(qs, user):
    """
    Function that will limit the provided queryset to the objects that
    the provided user can see.

    This filtering is based on the night that the object belongs too.
    An anonymous user can see objects from all public nights. A logged
    in user can also see private nights that he/she has viewing rights
    for.

    (for some reason qs1.union(qs2) can not be used here instead of
    using th | operator!!!)
    """

    #   Check if night is public
    public = qs.filter(night__is_public__exact=True)

    #   Check if user is logged in ...
    if user.is_anonymous:
        #   ... return the "public" queryset if not
        return public
    else:
        #   Check if user is allowed to view the night ...
        restricted = qs.filter(
            night__pk__in=user.get_read_nights().values('pk')
            )
        if len(restricted) > 0:
            #   ... if this is the case return the specific queryset ...
            return restricted
        else:
            #   ... if not, return the public queryset
            return public


def get_allowed_nights_to_view_for_user(qs, user):
    """
    Function that will limit the provided queryset to nights that
    the provided user can see.

    An anonymous user can see objects from all public nights. A logged
    in user can also see private nights that he/she has viewing rights
    for.
    """

    #   Check if night is public
    public = qs.filter(is_public__exact=True)

    #   Check if user is logged in ...
    if user.is_anonymous:
        #   ... return the "public" queryset if not
        return public
    else:
        #   Check if user is allowed to view the night ...
        restricted = qs.filter(
            pk__in=user.get_read_nights().values('pk')
            )
        if len(restricted) > 0:
            #   ... if this is the case return the specific queryset ...
            return restricted
        else:
            #   ... if not, return the public queryset
            return public


def check_user_can_view_night(function):
    """
        Decorator that loads the function if the user is allowed to see the
        night, redirects to login page otherwise.
    """
    def wrapper(request, *args, **kwargs):
        user = request.user
        try:
            night = Night.objects.get(pk=kwargs['night_id'])
        except Exception:
            messages.error(request, "That page requires login to view")
            return redirect('login')

        if request.user.is_anonymous and night.is_public:
            return function(request, *args, **kwargs)
        elif not request.user.is_anonymous and request.user.can_read(night):
            return function(request, *args, **kwargs)
        else:
            messages.error(
                request,
                "Night: {} requires login to see".format(night),
            )
            return redirect('login')

    return wrapper
