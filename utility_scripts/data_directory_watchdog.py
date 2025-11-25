import os

from pathlib import Path

import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import threading

import multiprocessing as mp

import environ

import django
from django.conf import settings

from OSTdata.utilities import (
    add_new_observation_run,
    add_new_data_file,
    evaluate_data_file,
    compute_file_hash,
)

# sys.path.append('../')
os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from obs_run.models import ObservationRun, DataFile

import logging
logger = logging.getLogger(__name__)

#   Get base directory
environment_file = os.path.join(settings.BASE_DIR, 'ostdata/.env')

#   Read environment file
env = environ.Env()
environ.Env.read_env(environment_file)

#   Set data directory to watch and watcher tuning
directory_to_watch = env('DATA_DIRECTORY')
WATCH_DEBOUNCE_SECONDS = env.float('WATCH_DEBOUNCE_SECONDS', default=2.0)
WATCH_IGNORED_SUFFIXES = [s.strip() for s in env('WATCH_IGNORED_SUFFIXES', default='.filepart,.bck,.swp').split(',') if s.strip()]
WATCH_CREATED_DELAY_SECONDS = env.float('WATCH_CREATED_DELAY_SECONDS', default=20.0)
WATCH_STABILITY_SECONDS = env.float('WATCH_STABILITY_SECONDS', default=0.0)


def add_new_observation_run_wrapper(data_path):
    """
    Adds new observation run and all associated objects and datasets

    Parameters
    ----------
    data_path           : `pathlib.Path`
        Path to the directory with the observation data
    """
    logger.info(f"Start evaluation of {data_path} directory")

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
    #   Wait to ensure that the data upload is complete.
    time.sleep(WATCH_CREATED_DELAY_SECONDS)

    # Optional: stability check (size unchanged over WATCH_STABILITY_SECONDS)
    if WATCH_STABILITY_SECONDS and WATCH_STABILITY_SECONDS > 0:
        try:
            p = Path(file_path)
            s1 = p.stat().st_size
            time.sleep(WATCH_STABILITY_SECONDS)
            s2 = p.stat().st_size
            if s1 != s2:
                logger.info(f"Skipping {file_path} (size still changing)")
                return
        except Exception as e:
            logger.warning(f"Stability check failed for {file_path}: {e}")

    source_path = str(file_path).split(directory_to_monitor)[1].split('/')[0]

    # suffix = file_path.suffix
    # if suffix not in ['.filepart', '.bck', '.swp']:
    logger.info(f"Evaluating {file_path}...")
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
        logger.exception(f"Evaluation of {file_path} failed.")


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
        # try:
        #     while True:
        #         time.sleep(5)
        # except:
        #     self.observer.stop()
        #     print("Error")

        # self.observer.join()

        try:
            while self.observer.is_alive():
                self.observer.join(1)
        finally:
            self.observer.stop()
            self.observer.join()


class Handler(FileSystemEventHandler):

    def __init__(self, directory_to_monitor):
        super().__init__()
        self.directory_to_monitor = directory_to_monitor
        # Debounce timers per absolute file path
        self._debounce_timers = {}

    def _rel_parts(self, abs_path):
        """
        Return path parts relative to the monitored base directory.
        Example: /data/2023-11-01_test/sub -> ['2023-11-01_test', 'sub']
        """
        rel = os.path.relpath(abs_path, self.directory_to_monitor)
        rel = rel.strip(os.sep)
        if not rel:
            return []
        return rel.split(os.sep)

    def _abs_from_parts(self, parts):
        return os.path.join(self.directory_to_monitor, *parts)

    def on_created(self, event):
        if event.is_directory:
            logger.info(f"Directory created - {event.src_path}")
            # Only treat brand-new top-level run directories as runs
            parts = self._rel_parts(event.src_path)
            if len(parts) == 1:
                #   Add new observation run
                add_new_observation_run_wrapper(Path(event.src_path))
            # p = mp.Process(
            #     target=add_new_observation_run_wrapper,
            #     args=(Path(event.src_path),),
            # )
            # p.start()

        else:
            suffix = Path(event.src_path).suffix
            if suffix not in WATCH_IGNORED_SUFFIXES:
                logger.info(f"File created - {event.src_path}")

                #   Add new data file instance
                add_new_data_file_wrapper(
                    Path(event.src_path),
                    self.directory_to_monitor,
                )
                # p = mp.Process(
                #     target=add_new_data_file_wrapper,
                #     args=(Path(event.src_path), self.directory_to_monitor,),
                # )
                # p.start()

    def on_deleted(self, event):
        # print('IN DELETE')
        if event.is_directory:
            logger.info(f"Directory deleted - {event.src_path}")
            #   Delete observation run when a top-level run folder is removed
            parts = self._rel_parts(event.src_path)
            if len(parts) == 1:
                run_name = parts[0]
                try:
                    observation_run = ObservationRun.objects.get(name=run_name)
                    observation_run.delete()
                except ObservationRun.DoesNotExist:
                    logger.warning(f"Run not found for deletion: {run_name}")

        else:
            suffix = Path(event.src_path).suffix
            if suffix not in WATCH_IGNORED_SUFFIXES:
                logger.info(f"File deleted - {event.src_path}")

                #   Delete data file object
                data_file = DataFile.objects.get(datafile=event.src_path)
                data_file.delete()

    def on_moved(self, event):
        if event.is_directory:
            logger.info(f"Directory moved - {event.src_path} -> {event.dest_path}")
            #   Only handle top-level run directory renames/moves
            src_parts = self._rel_parts(event.src_path)
            dst_parts = self._rel_parts(event.dest_path)
            if len(src_parts) == 1 and len(dst_parts) == 1:
                src_run = src_parts[0]
                dst_run = dst_parts[0]
                try:
                    observation_run = ObservationRun.objects.get(name=src_run)
                except ObservationRun.DoesNotExist:
                    logger.warning(f"Run not found for rename: {src_run}")
                    return

                # Update run name
                observation_run.name = dst_run
                observation_run.save()

                # Update all DataFile paths under this run by prefix replacement
                src_prefix = self._abs_from_parts([src_run]) + os.sep
                dst_prefix = self._abs_from_parts([dst_run]) + os.sep
                affected = DataFile.objects.filter(datafile__startswith=src_prefix)
                n = 0
                for df in affected:
                    try:
                        df.datafile = df.datafile.replace(src_prefix, dst_prefix, 1)
                        df.save(update_fields=['datafile'])
                        n += 1
                    except Exception as e:
                        logger.error(f"Failed to update path for df {df.pk}: {e}")
                logger.info(f"Updated run name and {n} file paths from '{src_run}' to '{dst_run}'")
        else:
            suffix = Path(event.src_path).suffix
            if suffix not in WATCH_IGNORED_SUFFIXES:
                logger.info(f"File moved - {event.src_path} -> {event.dest_path}")

                #   Find and update data file
                try:
                    data_file = DataFile.objects.get(datafile=event.src_path)
                    data_file.datafile = event.dest_path
                    try:
                        p = Path(event.dest_path)
                        data_file.file_size = p.stat().st_size if p.exists() else 0
                        try:
                            data_file.content_hash = compute_file_hash(p) if p.exists() else ''
                        except Exception:
                            pass
                        data_file.save(update_fields=['datafile', 'file_size', 'content_hash'])
                    except Exception:
                        data_file.save(update_fields=['datafile'])
                except DataFile.DoesNotExist:
                    # If a move was missed earlier, try to see if the destination already exists
                    try:
                        DataFile.objects.get(datafile=event.dest_path)
                        logger.info('Destination path already tracked; skipping update.')
                    except DataFile.DoesNotExist:
                        # Optional: try to match by hash if destination exists
                        try:
                            p = Path(event.dest_path)
                            if p.exists() and p.is_file():
                                h = compute_file_hash(p)
                                size = p.stat().st_size
                                # Restrict search to files within the same destination run when possible
                                dst_parts = self._rel_parts(event.dest_path)
                                qs = DataFile.objects.filter(content_hash=h, file_size=size)
                                if dst_parts:
                                    dst_run = dst_parts[0]
                                    dst_prefix = self._abs_from_parts([dst_run]) + os.sep
                                    qs = qs.filter(datafile__startswith=dst_prefix)
                                count = qs.count()
                                if count == 1:
                                    match = qs.first()
                                    match.datafile = event.dest_path
                                    match.save(update_fields=['datafile'])
                                    logger.info('Matched moved file by content hash to DataFile #%s', match.pk)
                                elif count > 1:
                                    logger.warning('Multiple DB candidates match content hash; skipping ambiguous move recovery.')
                                else:
                                    logger.warning('File move cannot be applied (no matching DataFile).')
                            else:
                                logger.warning('File move destination does not exist.')
                        except Exception:
                            logger.warning('File move cannot be applied (no matching DataFile).')
                except Exception as e:
                    logger.exception('File move cannot be applied...')

    def on_modified(self, event):
        if event.is_directory:
            return
        suffix = Path(event.src_path).suffix
        if suffix in WATCH_IGNORED_SUFFIXES:
            return
        # Debounce: coalesce rapid successive modifications of the same file
        self._schedule_modified(event.src_path)

    def _schedule_modified(self, abs_path, delay=None):
        if delay is None:
            delay = WATCH_DEBOUNCE_SECONDS
        try:
            t = self._debounce_timers.get(abs_path)
            if t is not None:
                t.cancel()
        except Exception:
            pass
        timer = threading.Timer(delay, self._process_modified, args=(abs_path,))
        self._debounce_timers[abs_path] = timer
        timer.start()

    def _process_modified(self, abs_path):
        logger.info(f"File modified (debounced) - {abs_path}")
        # Extra small wait to ensure file is closed by writers
        time.sleep(1)
        try:
            self._process_modified_once(abs_path)

        except Exception as e:
            logger.exception('File modification cannot be applied...')
        finally:
            # Clear debounce entry
            try:
                timer = self._debounce_timers.pop(abs_path, None)
                if timer is not None:
                    timer.cancel()
            except Exception:
                pass

    def _process_modified_once(self, abs_path, attempts=3, backoff=1.5):
        """Try to re-evaluate a modified file with simple retry/backoff.
        """
        last_exc = None
        for i in range(attempts):
            try:
                #   Find data file object
                data_file = DataFile.objects.get(datafile=abs_path)

                #   Delete old object relations (will be recreated)
                objects = data_file.object_set.all()
                for object_ in objects:
                    object_.datafiles.remove(data_file)

                #   Find observation run (top-level dir name)
                parts = self._rel_parts(abs_path)
                if not parts:
                    return
                run_name = parts[0]
                observation_run = ObservationRun.objects.get(name=run_name)

                #   Re-evaluate modified file
                evaluate_data_file(data_file, observation_run)

                #   Update observation run statistics
                observation_run_statistic_update(observation_run)

                return
            except Exception as e:
                last_exc = e
                time.sleep(backoff)
        if last_exc:
            raise last_exc


if __name__ == '__main__':
    w = Watcher(directory_to_watch)
    w.run()
