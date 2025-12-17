import os

from pathlib import Path

import time

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

import threading

import multiprocessing as mp

import environ

import django
from django.conf import settings

from utilities import (
    add_new_observation_run,
    add_new_data_file,
    evaluate_data_file,
    compute_file_hash,
)

"""
This module is imported by the Django management command `watch_data`.
Django is already configured in that execution context, so we must NOT
override DJANGO_SETTINGS_MODULE or call django.setup() here at import time.
"""

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
WATCH_USE_POLLING = env.bool('WATCH_USE_POLLING', default=False)
WATCH_POLLING_INTERVAL = env.float('WATCH_POLLING_INTERVAL', default=1.0)  # Polling interval in seconds


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
    #   Important: when a pre-filled directory is moved into the watch root,
    #   no file-created events are generated for existing files. Ingest now.
    add_new_observation_run(data_path, add_data_files=True)


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
        # Use polling for filesystems without inotify support (e.g., some network mounts)
        if WATCH_USE_POLLING:
            self.observer = PollingObserver(timeout=WATCH_POLLING_INTERVAL)
            self._mode = 'polling'
        else:
            self.observer = Observer()
            self._mode = 'inotify'
        self.directory_to_watch = directory

    def run(self):
        # Log startup configuration
        logger.info("=" * 60)
        logger.info("Watcher starting...")
        logger.info("  Directory: %s", self.directory_to_watch)
        logger.info("  Mode: %s", self._mode)
        if self._mode == 'polling':
            logger.info("  Polling interval: %.1f seconds", WATCH_POLLING_INTERVAL)
        logger.info("  Debounce: %.1f seconds", WATCH_DEBOUNCE_SECONDS)
        logger.info("  Created delay: %.1f seconds", WATCH_CREATED_DELAY_SECONDS)
        logger.info("  Stability check: %.1f seconds", WATCH_STABILITY_SECONDS)
        logger.info("  Ignored suffixes: %s", WATCH_IGNORED_SUFFIXES)
        logger.info("=" * 60)

        event_handler = Handler(self.directory_to_watch)
        self.observer.schedule(
            event_handler,
            self.directory_to_watch,
            recursive=True,
        )
        self.observer.start()
        logger.info("Watcher is now running and monitoring for changes...")

        try:
            while self.observer.is_alive():
                self.observer.join(1)
        finally:
            self.observer.stop()
            self.observer.join()
            logger.info("Watcher stopped.")


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
            logger.info("[EVENT:CREATED:DIR] %s", event.src_path)
            # Only treat brand-new top-level run directories as runs
            parts = self._rel_parts(event.src_path)
            if len(parts) == 1:
                # Skip hidden/system/trash directories
                name = parts[0]
                low = name.lower()
                if name.startswith('.') or low.startswith('trash') or name in ('lost+found',):
                    logger.info("[SKIP] Ignoring system/trash directory '%s'", name)
                    return
                logger.info("[ACTION] Creating new observation run for '%s'", name)
                add_new_observation_run_wrapper(Path(event.src_path))
        else:
            suffix = Path(event.src_path).suffix
            if suffix in WATCH_IGNORED_SUFFIXES:
                logger.debug("[SKIP] Ignored suffix %s for %s", suffix, event.src_path)
            else:
                logger.info("[EVENT:CREATED:FILE] %s", event.src_path)
                logger.info("[ACTION] Adding new data file...")
                add_new_data_file_wrapper(
                    Path(event.src_path),
                    self.directory_to_monitor,
                )

    def on_deleted(self, event):
        if event.is_directory:
            logger.info("[EVENT:DELETED:DIR] %s", event.src_path)
            #   Delete observation run when a top-level run folder is removed
            parts = self._rel_parts(event.src_path)
            if len(parts) == 1:
                run_name = parts[0]
                try:
                    observation_run = ObservationRun.objects.get(name=run_name)
                    logger.info("[ACTION] Deleting observation run '%s' from DB", run_name)
                    observation_run.delete()
                    logger.info("[SUCCESS] Observation run '%s' deleted", run_name)
                except ObservationRun.DoesNotExist:
                    logger.warning("[WARN] Run not found for deletion: %s", run_name)
        else:
            suffix = Path(event.src_path).suffix
            if suffix in WATCH_IGNORED_SUFFIXES:
                logger.debug("[SKIP] Ignored suffix %s for %s", suffix, event.src_path)
                return

            logger.info("[EVENT:DELETED:FILE] %s", event.src_path)

            #   Delete data file object (robust to path variations and missing rows)
            deleted_run = None
            deleted_file_id = None
            try:
                # Try exact path first
                data_file = DataFile.objects.get(datafile=event.src_path)
                deleted_run = data_file.observation_run
                deleted_file_id = data_file.pk
                logger.info("[ACTION] Deleting DataFile #%s from DB (exact path match)", deleted_file_id)
                data_file.delete()
                logger.info("[SUCCESS] DataFile #%s deleted", deleted_file_id)
            except DataFile.DoesNotExist:
                # Try realpath (symlinks)
                try:
                    real = os.path.realpath(event.src_path)
                    data_file = DataFile.objects.get(datafile=real)
                    deleted_run = data_file.observation_run
                    deleted_file_id = data_file.pk
                    logger.info("[ACTION] Deleting DataFile #%s from DB (realpath match)", deleted_file_id)
                    data_file.delete()
                    logger.info("[SUCCESS] DataFile #%s deleted", deleted_file_id)
                except DataFile.DoesNotExist:
                    # Fallback: endswith match by relative path under the monitored directory
                    try:
                        rel = os.path.relpath(event.src_path, self.directory_to_monitor)
                        rel = rel.strip(os.sep)
                        if rel:
                            qs = DataFile.objects.filter(datafile__endswith=os.sep + rel)
                            count = qs.count()
                            if count == 1:
                                df = qs.first()
                                deleted_run = df.observation_run
                                deleted_file_id = df.pk
                                logger.info("[ACTION] Deleting DataFile #%s from DB (suffix match)", deleted_file_id)
                                df.delete()
                                logger.info("[SUCCESS] DataFile #%s deleted", deleted_file_id)
                            elif count > 1:
                                logger.warning("[WARN] Multiple DataFile rows (%d) match deleted path suffix '%s'; skipping delete", count, rel)
                    except Exception as e:
                        logger.exception("[ERROR] Exception during fallback path matching: %s", e)

            # Update run statistics after file deletion
            if deleted_run:
                try:
                    observation_run_statistic_update(deleted_run)
                    logger.info("[ACTION] Updated statistics for run '%s' after file deletion", deleted_run.name)
                except Exception as e:
                    logger.warning("[WARN] Failed to update run statistics after file deletion: %s", e)
            elif deleted_file_id is None:
                # If we reach here, we didn't find a corresponding DB row
                logger.info("[INFO] No DataFile row found for deleted path '%s'; nothing to delete from DB", event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            logger.info("[EVENT:MOVED:DIR] %s -> %s", event.src_path, event.dest_path)
            #   Only handle top-level run directory renames/moves
            src_parts = self._rel_parts(event.src_path)
            dst_parts = self._rel_parts(event.dest_path)
            if len(src_parts) == 1 and len(dst_parts) == 1:
                src_run = src_parts[0]
                dst_run = dst_parts[0]
                try:
                    observation_run = ObservationRun.objects.get(name=src_run)
                except ObservationRun.DoesNotExist:
                    logger.warning("[WARN] Run not found for rename: %s", src_run)
                    return

                # Update run name
                logger.info("[ACTION] Renaming run '%s' -> '%s'", src_run, dst_run)
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
                        logger.error("[ERROR] Failed to update path for df %s: %s", df.pk, e)
                logger.info("[SUCCESS] Updated run name and %d file paths from '%s' to '%s'", n, src_run, dst_run)
        else:
            suffix = Path(event.src_path).suffix
            if suffix in WATCH_IGNORED_SUFFIXES:
                logger.debug("[SKIP] Ignored suffix %s for moved file", suffix)
                return

            logger.info("[EVENT:MOVED:FILE] %s -> %s", event.src_path, event.dest_path)

            #   Find and update data file
            try:
                data_file = DataFile.objects.get(datafile=event.src_path)
                logger.info("[ACTION] Updating DataFile #%s path to new location", data_file.pk)
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
                logger.info("[SUCCESS] DataFile #%s path updated", data_file.pk)
            except DataFile.DoesNotExist:
                # If a move was missed earlier, try to see if the destination already exists
                try:
                    DataFile.objects.get(datafile=event.dest_path)
                    logger.info('[INFO] Destination path already tracked; skipping update.')
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
                                logger.info('[SUCCESS] Matched moved file by content hash to DataFile #%s', match.pk)
                            elif count > 1:
                                logger.warning('[WARN] Multiple DB candidates (%d) match content hash; skipping ambiguous move recovery.', count)
                            else:
                                # No match: treat this as a newly added file under an existing run
                                if dst_parts:
                                    try:
                                        run_name = dst_parts[0]
                                        observation_run = ObservationRun.objects.get(name=run_name)
                                        logger.info('[ACTION] Ingesting new file after move into run %s: %s', run_name, str(p))
                                        add_new_data_file(p, observation_run)
                                        observation_run_statistic_update(observation_run)
                                        logger.info('[SUCCESS] Ingested new file after move into run %s', run_name)
                                    except ObservationRun.DoesNotExist:
                                        logger.warning('[WARN] Moved file is not under a known run: %s', event.dest_path)
                                else:
                                    logger.warning('[WARN] File move cannot be applied (no matching DataFile).')
                        else:
                            logger.warning('[WARN] File move destination does not exist: %s', event.dest_path)
                    except Exception as e:
                        logger.warning('[WARN] File move cannot be applied (no matching DataFile): %s', e)
            except Exception as e:
                logger.exception('[ERROR] File move cannot be applied: %s', e)

    def on_modified(self, event):
        if event.is_directory:
            return
        suffix = Path(event.src_path).suffix
        if suffix in WATCH_IGNORED_SUFFIXES:
            return
        # Debounce: coalesce rapid successive modifications of the same file
        logger.debug("[EVENT:MODIFIED:FILE] %s (scheduling debounced processing)", event.src_path)
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
        logger.info("[EVENT:MODIFIED:FILE] %s (debounced, now processing)", abs_path)
        # Extra small wait to ensure file is closed by writers
        time.sleep(1)
        try:
            self._process_modified_once(abs_path)

        except Exception as e:
            logger.exception('[ERROR] File modification cannot be applied: %s', e)
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

                logger.info("[ACTION] Re-evaluating modified DataFile #%s", data_file.pk)

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

                logger.info("[SUCCESS] DataFile #%s re-evaluated", data_file.pk)
                return
            except Exception as e:
                last_exc = e
                logger.debug("[RETRY] Attempt %d/%d failed for %s: %s", i+1, attempts, abs_path, e)
                time.sleep(backoff)
        if last_exc:
            raise last_exc


if __name__ == '__main__':
    w = Watcher(directory_to_watch)
    w.run()
