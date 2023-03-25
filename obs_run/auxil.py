
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import reverse

from .models import Obs_run

############################################################################

def invalid_form(request, redirect):
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
        reverse(redirect)
    )

############################################################################

def populate_runs(run_data):
    """
        Analyse provided dictionary and populate the corresponding
        `Obs_run` object

        Parameters
        ----------
        run_data          : `dictionary`
            Information to be added to the `Obs_run` object
    """
    #   Check for duplicates
    duplicates = Obs_run.objects.filter(name=run_data["main_id"])

    if len(duplicates) != 1:
        return False, "Observation run exists already: {}".format(run_data["main_id"])

    return True, "New observation run ({}) created".format(run_data["main_id"])
