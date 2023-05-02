
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import reverse

from datetime import timedelta

from astropy.time import Time

from .models import Obs_run


############################################################################

def sort_modified_created(model):
    '''
        Prepare index for sorting models according to History entry

        Parameters
        ----------
        model               : django.db.models.Model instance
    '''
    try:
        return model.history.latest().history_date
    except AttributeError:
        return datetime.fromisoformat("1970-01-01")


############################################################################

def wascreated(mod):
    '''
        Modifications within the first 5 minutes of an object being created
        should not make the object count as having been modified
        => mark models that are modified within the first 5 minutes not as
           modified

        Parameters
        ----------
        model               : django.db.models.Model instance
    '''
    earliest_history = mod.history.earliest()
    latest_history = mod.history.latest()

    time_diff = latest_history.history_date - earliest_history.history_date

    if time_diff <= timedelta(minutes=5):
        return True
    else:
        return False

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

