import os

import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import multiprocessing as mp

import environ

import django
from django.conf import settings

from utilities import add_new_observation_run

# sys.path.append('../')
# os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
# django.setup()

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
    #   Wait 20 minutes to ensure that the data upload to the directory is
    #   complete.
    time.sleep(1200)
    print(f"Start evaluation of {data_path} directory")

    #   Analyse directory and add adds associated data
    add_new_observation_run(data_path)


class Watcher:

    def __init__(self, directory):
        self.observer = Observer()
        self.directory_to_watch = directory

    def run(self):
        event_handler = Handler()
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("Error")

        self.observer.join()


class Handler(FileSystemEventHandler):

    @staticmethod
    def on_created(event):
        if event.is_directory:
            print(f"Directory created - {event.src_path}")
            p = mp.Process(
                target=add_new_observation_run_wrapper,
                args=(event.src_path),
            )
            p.start()
            # add_new_observation_run_wrapper(event.src_path)
        else:
            print(f"File created - {event.src_path}")

    @staticmethod
    def on_deleted(event):
        if event.is_directory:
            print(f"Directory deleted - {event.src_path}")
            # ObservationRun.objects.all()
            # run.delete()
        else:
            print(f"File deleted - {event.src_path}")

    @staticmethod
    def on_moved(event):
        if event.is_directory:
            print(f"Directory moved - {event.src_path} -> {event.dest_path}")
            # print(dir(event))
        else:
            print(f"File moved - {event.src_path}")

    @staticmethod
    def on_modified(event):
        if not event.is_directory:
            print(f"File modified - {event.src_path}")


if __name__ == '__main__':
    w = Watcher(directory_to_watch)
    w.run()
