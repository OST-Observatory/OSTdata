from django.core.management.base import BaseCommand

from obs_run.spectrograph_heuristics import HEURISTICS, recompute_suggestions


class Command(BaseCommand):
    help = (
        'Recompute the spectrograph suggestions (run majority + path tokens) shown in the data files view '
        'and their evaluation on manually reviewed files. Same as the nightly Celery task.'
    )

    def handle(self, *args, **options):
        result = recompute_suggestions()
        report = result['report']
        self.stdout.write(f"Open suggestions: {report['open_suggestions']}")
        self.stdout.write(f"Reviewed files used for the evaluation: {report['reviewed_files']}")
        for name in HEURISTICS:
            ev = report['evaluation'][name]
            self.stdout.write(
                f"  {name:<14} tp {ev['tp']:>6}  fp {ev['fp']:>6}  fn {ev['fn']:>6}  "
                f"precision {ev['precision']}  recall {ev['recall']}"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(result['suggestions'])} suggestions stored"))
