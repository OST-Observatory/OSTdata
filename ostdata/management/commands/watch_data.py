from __future__ import annotations

import importlib
import os
import runpy
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Watch the data directory and update the database accordingly."

    def add_arguments(self, parser):
        parser.add_argument(
            '--script',
            dest='script',
            default=os.environ.get('WATCHDOG_SCRIPT', 'data_directory_watchdog.py'),
            help="Path to the watchdog script (default: data_directory_watchdog.py at project root).",
        )
        parser.add_argument(
            '--module',
            dest='module',
            default=os.environ.get('WATCHDOG_MODULE', 'data_directory_watchdog'),
            help="Python module name to import and run if available (default: data_directory_watchdog).",
        )
        parser.add_argument(
            '--callable',
            dest='callable',
            default=os.environ.get('WATCHDOG_CALLABLE', 'main'),
            help="Callable name inside module to invoke (default: main).",
        )

    def handle(self, *args, **options):
        module_name: str = options['module']
        callable_name: str = options['callable']
        script_path_opt: str = options['script']

        base_dir: Path = settings.BASE_DIR
        script_path: Path = (base_dir / script_path_opt) if not os.path.isabs(script_path_opt) else Path(script_path_opt)

        # First try to import as a module and call the entry callable
        try:
            mod = importlib.import_module(module_name)
            fn = getattr(mod, callable_name, None)
            if callable(fn):
                self.stdout.write(self.style.SUCCESS(f"Running {module_name}.{callable_name}()"))
                return fn()
        except Exception as e:
            # Fallback to script execution path
            self.stdout.write(self.style.WARNING(f"Module path failed ({e}); falling back to script execution"))

        # Fallback: run the script within current interpreter so Django is initialized
        if not script_path.exists():
            raise CommandError(f"Watchdog script not found at {script_path}")

        self.stdout.write(self.style.SUCCESS(f"Executing script: {script_path}"))
        # Run the script in its own globals but within this process (Django already configured)
        runpy.run_path(str(script_path), run_name="__main__")


