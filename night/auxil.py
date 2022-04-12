
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import reverse

from .models import Night

############################################################################

def invalid_form(request, redirect, project_slug):
    """
        Handel invalid forms
    """
    #   Add message
    messages.add_message(
        request,
        messages.ERROR,
        "Invalid form. Please try again.",
    )
    print("Invalid form...")

    #   Return and redirect
    return HttpResponseRedirect(
        reverse(redirect, kwargs={'project': project_slug})
    )

############################################################################

def populate_nights(night_data):
    """
        Analyse provided dictionary and populate the corresponding
        `Night` object

        Parameters
        ----------
        night_data      : `dictionary`
            Information to be added to the `Night` object
    """
    #   Check for duplicates
    duplicates = Night.objects.filter(name=night_data["main_id"])

    if len(duplicates) != 1:
        return False, "System exists already: {}".format(night_data["main_id"])

    return True, "New system ({}) created".format(night_data["main_id"])
