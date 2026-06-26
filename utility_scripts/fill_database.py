"""One-off ingest: wipe runs/datafiles/objects, then load all top-level run dirs under DATA path."""
import os
import sys
from pathlib import Path

# Project root (OSTdata/) must be on sys.path for `ostdata` and `utilities`.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ostdata.settings')
django.setup()

from objects.models import Object
from obs_run.models import ObservationRun, DataFile

from utilities import add_new_observation_run

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python utility_scripts/fill_database.py /path/to/DATA_DIRECTORY', file=sys.stderr)
        sys.exit(1)

    data_path = Path(sys.argv[1])
    if not data_path.is_dir():
        print(f'Not a directory: {data_path}', file=sys.stderr)
        sys.exit(1)

    for run in ObservationRun.objects.all():
        run.delete()

    for f in DataFile.objects.all():
        f.delete()

    for o in Object.objects.all():
        o.delete()

    for path_to_run in sorted(data_path.iterdir()):
        if not path_to_run.is_dir() or path_to_run.name.startswith('.'):
            continue
        add_new_observation_run(
            path_to_run,
            print_to_terminal=True,
            add_data_files=True,
        )
