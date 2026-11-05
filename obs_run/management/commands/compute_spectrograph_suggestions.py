from django.core.management.base import BaseCommand

from obs_run.spectrograph_heuristics import EVALUATED, recompute_suggestions


class Command(BaseCommand):
    help = (
        'Recompute the spectrograph suggestions (run majority + path tokens) shown in the data files view '
        'and their evaluation on manually reviewed files; then apply agreeing suggestions if '
        'SPECTROGRAPH_AUTO_APPLY is on. Same as the nightly Celery task.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--no-auto-apply', action='store_true', help='Do not apply agreeing suggestions')

    def handle(self, *args, **options):
        result = recompute_suggestions(auto_apply=False if options['no_auto_apply'] else None)
        report = result['report']
        self.stdout.write(f"Open suggestions: {report['open_suggestions']}")
        self.stdout.write(f"Reviewed files used for the evaluation: {report['reviewed_files']}")
        for name in EVALUATED:
            ev = report['evaluation'][name]
            self.stdout.write(
                f"  {name:<20} tp {ev['tp']:>6}  fp {ev['fp']:>6}  fn {ev['fn']:>6}  "
                f"precision {ev['precision']}  recall {ev['recall']}"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(result['suggestions'])} suggestions stored"))
        if 'auto_applied' in report:
            self.stdout.write(self.style.SUCCESS(f"{report['auto_applied']['count']} agreeing suggestions applied"))
