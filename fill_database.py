import sys

from pathlib import Path

import django

import os

os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from objects.models import Object
from obs_run.models import ObservationRun, DataFile

from utilities import add_new_observation_run

if __name__ == "__main__":
    #   Delete all Observation runs and DataFile entries in the database
    for run in ObservationRun.objects.all():
        run.delete()

    for f in DataFile.objects.all():
        f.delete()

    for o in Object.objects.all():
        o.delete()

    #   Input path
    data_path = sys.argv[1]
    data_path = Path(data_path)

    #   Load data and setup models
    for path_to_run in data_path.iterdir():
        add_new_observation_run(
            path_to_run,
            print_to_terminal=True,
            add_data_files=True,
        )
