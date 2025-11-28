from django.core.management.base import BaseCommand, CommandError
import logging


class Command(BaseCommand):
    help = "Start the filesystem watcher to ingest observation data."

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        try:
            try:
                # Prefer local module path when running from project root
                from data_directory_watchdog import Watcher, directory_to_watch
            except Exception:
                # Fallback to absolute package path
                from OSTdata.data_directory_watchdog import Watcher, directory_to_watch
            self.stdout.write(self.style.SUCCESS(f"Starting watcher for: {directory_to_watch}"))
            watcher = Watcher(directory_to_watch)
            watcher.run()  # blocks until stopped
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Watcher stopped by user"))
        except Exception as e:
            logger.exception("Watcher crashed")
            raise CommandError(str(e))


