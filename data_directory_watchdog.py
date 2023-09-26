import os

from pathlib import Path

import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import multiprocessing as mp

import environ

import django
from django.conf import settings

from utilities import (
    add_new_observation_run,
    add_new_data_file,
    evaluate_data_file,
)

# sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from obs_run.models import ObservationRun, DataFile

#   Get base directory
environment_file = os.path.join(settings.BASE_DIR, 'ostdata/.env')

#   Read environment file
env = environ.Env()
environ.Env.read_env(environment_file)

#   Set data directory to watch
directory_to_watch = env('DATA_DIRECTORY')


def add_new_observation_run_wrapper(data_path):
    """
    Adds new observation run and all associated objects and datasets

    Parameters
    ----------
    data_path           : `pathlib.Path`
        Path to the directory with the observation data
    """
    print(f"Start evaluation of {data_path} directory")

    #   Analyse directory and add adds associated data
    add_new_observation_run(data_path)


def add_new_data_file_wrapper(file_path, directory_to_monitor):
    """
    Adds new observation run and all associated objects and datasets

    Parameters
    ----------
    file_path               : `pathlib.Path`
        Path to the directory with the observation data

    directory_to_monitor    : `string`
        Path being monitored - base path.
    """
    #   Wait 20 seconds to ensure that the data upload is complete.
    time.sleep(20)

    source_path = str(file_path).split(directory_to_monitor)[1].split('/')[0]

    suffix = file_path.suffix
    if suffix not in ['.filepart', '.bck']:
        print(f"Evaluating {file_path}...")
        try:
            observation_run = ObservationRun.objects.get(name=source_path)

            #   Analyse directory and add adds associated data
            add_new_data_file(
                file_path,
                observation_run,
                # print_to_terminal=True,
            )

            #   Update statistic on observation run
            observation_run_statistic_update(observation_run)

        except Exception as e:
            print(f"Evaluation of {file_path} failed.")
            print(e)


def observation_run_statistic_update(observation_run):
    """
    Update/reevaluate observation time statistics for observation runs.

    Parameters
    ----------
    observation_run             : `obs_run.models.ObservationRun`
        Observation run to which the data file belongs
    """
    #   Set time of observation run -> mid of observation
    datafiles = observation_run.datafile_set.filter(
        hjd__gt=2451545
    )
    start_jd = datafiles.order_by('hjd')

    if not start_jd:
        observation_run.mid_observation_jd = 0.
    else:
        start_jd = start_jd[0].hjd
        end_jd = datafiles.order_by('hjd').reverse()
        if not end_jd:
            observation_run.mid_observation_jd = start_jd
        else:
            end_jd = end_jd[0].hjd
            observation_run.mid_observation_jd = start_jd + (end_jd - start_jd) / 2.
    observation_run.save()


class Watcher:

    def __init__(self, directory):
        self.observer = Observer()
        self.directory_to_watch = directory

    def run(self):
        event_handler = Handler(self.directory_to_watch)
        self.observer.schedule(
            event_handler,
            self.directory_to_watch,
            recursive=True,
        )
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("Error")

        self.observer.join()


class Handler(FileSystemEventHandler):

    def __init__(self, directory_to_monitor):
        super().__init__()
        self.directory_to_monitor = directory_to_monitor

    def on_created(self, event):
        if event.is_directory:
            print(f"Directory created - {event.src_path}")

            #   Add new observation run
            p = mp.Process(
                target=add_new_observation_run_wrapper,
                args=(Path(event.src_path),),
            )
            p.start()

        else:
            print(f"File created - {event.src_path}")

            #   Add new data file instance
            p = mp.Process(
                target=add_new_data_file_wrapper,
                args=(Path(event.src_path), self.directory_to_monitor,),
            )
            p.start()

    def on_deleted(self, event):
        if event.is_directory:
            print(f"Directory deleted - {event.src_path}")

            #   Delete observation run
            path = event.src_path.split(self.directory_to_monitor)[1]
            observation_run = ObservationRun.objects.get(name=path)
            observation_run.delete()

        else:
            print(f"File deleted - {event.src_path}")

            #   Delete data file object
            data_file = DataFile.objects.get(datafile=event.src_path)
            data_file.delete()

    def on_moved(self, event):
        if event.is_directory:
            print(f"Directory moved - {event.src_path} -> {event.dest_path}")

            #   Cleanup paths
            source_path = event.src_path.split(self.directory_to_monitor)[1]
            destination_path = event.dest_path.split(self.directory_to_monitor)[1]

            #   Find and update observation run
            try:
                observation_run = ObservationRun.objects.get(name=source_path)
                observation_run.name = destination_path
                observation_run.save()

            except:
                print('Directory move cannot be applied...')
        else:
            print(f"File moved - {event.src_path} -> {event.dest_path}")

            #   Find and update data file
            try:
                data_file = DataFile.objects.get(datafile=event.src_path)
                data_file.datafile = event.dest_path
                data_file.save()
            except:
                print('File move cannot be applied...')

    def on_modified(self, event):
        if not event.is_directory:
            print(f"File modified - {event.src_path}")

            try:
                #   Find data file object
                data_file = DataFile.objects.get(datafile=event.src_path)

                #   Delete old object relations
                objects = data_file.object_set.all()
                for object_ in objects:
                    object_.datafiles.remove(data_file)

                #   Find observation run
                source_path = event.src_path.split(self.directory_to_monitor)[1].split('/')[0]
                print('source_path', source_path)
                observation_run = ObservationRun.objects.get(name=source_path)

                #   Evaluate change data file
                evaluate_data_file(data_file, observation_run)

                #   Update observation run statistic
                observation_run_statistic_update(observation_run)

            except Exception as e:
                print('File modification cannot be applied...')
                print(e)


if __name__ == '__main__':
    w = Watcher(directory_to_watch)
    w.run()
