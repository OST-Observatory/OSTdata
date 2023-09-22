
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import reverse

import os

from datetime import timedelta

from astropy.time import Time

from .models import ObservationRun


def get_size_dir(directory_path):
    """
        Iterate each file present in the folder using os.walk() and then compute
        and add the size of each scanned file using os.path.getsize().

        Parameters
        ----------
        directory_path             : `string
            Path to the directory
    """
    #   Assign size
    size = 0

    #   Calculate size
    for path, dirs, files in os.walk(directory_path):
        for f in files:
            fp = os.path.join(path, f)
            size += os.path.getsize(fp)

    return size

############################################################################


def sort_modified_created(model):
    """
        Prepare index for sorting models according to History entry

        Parameters
        ----------
        model               : django.db.models.Model instance
    """
    try:
        return model.history.latest().history_date
    except AttributeError:
        return datetime.fromisoformat("1970-01-01")


############################################################################


def wascreated(model):
    """
        Modifications within the first 5 minutes of an object being created
        should not make the object count as having been modified
        => mark models that are modified within the first 5 minutes not as
           modified

        Parameters
        ----------
        model               : django.db.models.Model instance
    """
    earliest_history = model.history.earliest()
    latest_history = model.history.latest()

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
        `ObservationRun` object

        Parameters
        ----------
        run_data          : `dictionary`
            Information to be added to the `ObservationRun` object
    """
    #   Check for duplicates
    duplicates = ObservationRun.objects.filter(name=run_data["main_id"])

    if len(duplicates) != 1:
        return False, "Observation run exists already: {}".format(run_data["main_id"])

    return True, "New observation run ({}) created".format(run_data["main_id"])

