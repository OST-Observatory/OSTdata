"""
Evaluate and apply the name rule of obs_run/exposure_type.py (arc lamp names in file name or OBJECT -> WA).

    python manage.py apply_exposure_type_name_rule --dry-run    # evaluation against manual labels, no changes
    python manage.py apply_exposure_type_name_rule              # needs EXPOSURE_TYPE_NAME_RULE=True

New and edited files get the rule in DataFile.save(); this command fills it in for existing files (and clears
it where it no longer applies).
"""
import json
from collections import Counter, defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from obs_run.exposure_type import UNKNOWN, arc_lamp_token, effective_exposure_type, name_rule_exposure_type
from obs_run.models import DataFile

FIELDS = ('pk', 'datafile', 'observation_run_id', 'exposure_type', 'header_target_name', 'exposure_type_rule',
          'exposure_type_user', 'exposure_type_ml')
BATCH = 1000


class Command(BaseCommand):
    help = 'Evaluate (--dry-run) and apply the arc lamp name rule (exposure_type_rule)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only evaluate, change nothing')
        parser.add_argument('--examples', type=int, default=5, help='Example files per group')
        parser.add_argument('--json', type=str, default=None, help='Write the evaluation as JSON')

    def handle(self, *args, **options):
        enabled = getattr(settings, 'EXPOSURE_TYPE_NAME_RULE', False)
        if not options['dry_run'] and not enabled:
            raise CommandError('EXPOSURE_TYPE_NAME_RULE is False: evaluate with --dry-run, then enable the setting')

        examples = options['examples']
        tokens = defaultdict(Counter)        # token -> manual label (or '' without) counts
        token_runs = defaultdict(set)
        wrong = defaultdict(list)            # manual label != WA -> example files
        effective_changes, change_examples = Counter(), defaultdict(list)
        updates = {}                         # pk -> new exposure_type_rule
        matches = 0

        queryset = DataFile.objects.order_by('pk').values(*FIELDS)
        for row in queryset.iterator(chunk_size=2000):
            value = name_rule_exposure_type(row['exposure_type'], row['datafile'], row['header_target_name'],
                                            enabled=True)
            if value != (row['exposure_type_rule'] or ''):
                updates[row['pk']] = value
            if not value:
                continue
            matches += 1
            token = arc_lamp_token(row['datafile'], row['header_target_name'])
            user = (row['exposure_type_user'] or '').strip()
            tokens[token][user if user and user != UNKNOWN else ''] += 1
            token_runs[token].add(row['observation_run_id'])
            if user and user not in (UNKNOWN, value) and len(wrong[user]) < examples:
                wrong[user].append(row['datafile'])
            if not user:
                before = effective_exposure_type(row['exposure_type'], row['exposure_type_ml'], None,
                                                 name_rule=row['exposure_type_rule'])
                after = effective_exposure_type(row['exposure_type'], row['exposure_type_ml'], None, name_rule=value)
                if before != after:
                    key = f'{before} -> {after}'
                    effective_changes[key] += 1
                    if len(change_examples[key]) < examples:
                        change_examples[key].append(row['datafile'])

        report = self._report(matches, tokens, token_runs, wrong, effective_changes, change_examples, updates)
        if options['json']:
            with open(options['json'], 'w') as f:
                json.dump(report, f, indent=1)
            self.stdout.write(f'Written to {options["json"]}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN: {len(updates)} files would change, nothing saved'))
            return
        by_value = defaultdict(list)
        for pk, value in updates.items():
            by_value[value].append(pk)
        for value, pks in by_value.items():
            for start in range(0, len(pks), BATCH):
                DataFile.objects.filter(pk__in=pks[start:start + BATCH]).update(exposure_type_rule=value)
        self.stdout.write(self.style.SUCCESS(f'\nUpdated exposure_type_rule of {len(updates)} files'))

    def _report(self, matches, tokens, token_runs, wrong, effective_changes, change_examples, updates):
        labelled = sum(n for counts in tokens.values() for label, n in counts.items() if label)
        correct = sum(counts['WA'] for counts in tokens.values())
        report = {
            'matches': matches,
            'with_manual_label': labelled,
            'manual_label_wa': correct,
            'purity': round(correct / labelled, 4) if labelled else None,
            'tokens': {token: {'files': sum(counts.values()), 'runs': len(token_runs[token]),
                               'manual_labels': {k: v for k, v in counts.items() if k}}
                       for token, counts in sorted(tokens.items(), key=lambda kv: -sum(kv[1].values()))},
            'wrong_manual_labels': dict(wrong),
            'effective_changes_without_manual_label': [
                {'change': key, 'n': n, 'examples': change_examples[key]} for key, n in effective_changes.most_common()
            ],
            'files_to_update': len(updates),
        }
        purity = '-' if report['purity'] is None else f'{100 * report["purity"]:.1f} %'
        self.stdout.write(f'Files matching the name rule: {matches}; with manual label: {labelled}, '
                          f'of which WA: {correct} (purity {purity})')
        self.stdout.write('\nPer token (files, runs, manual labels):')
        for token, entry in report['tokens'].items():
            labels = ', '.join(f'{k} {v}' for k, v in sorted(entry['manual_labels'].items(), key=lambda kv: -kv[1]))
            self.stdout.write(f'    {token:<8} {entry["files"]:>7} {entry["runs"]:>5}   {labels or "-"}')
        if wrong:
            self.stdout.write('\nManual label is not WA (examples):')
            for label, paths in wrong.items():
                for path in paths:
                    self.stdout.write(f'    {label}  {path}')
        self.stdout.write('\nEffective exposure type of files without manual label (before -> after):')
        for entry in report['effective_changes_without_manual_label']:
            self.stdout.write(f'    {entry["change"]:<10} {entry["n"]:>7}')
            for path in entry['examples']:
                self.stdout.write(f'        {path}')
        return report
