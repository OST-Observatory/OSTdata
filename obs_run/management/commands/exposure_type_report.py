import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from astropy.io import fits
from django.core.management.base import BaseCommand

from obs_run.exposure_type import RULES, effective_exposure_type, effective_exposure_type_expression, get_rule
from obs_run.management.commands._spectrograph_report import (
    SpectrographAnalysis,
    indicative_tokens,
    path_tokens,
    print_spectrograph_report,
)
from obs_run.models import DataFile

UNKNOWN = DataFile.UNKNOWN

# Upper bounds of the ML confidence buckets
CONFIDENCE_BUCKETS = [0.5, 0.7, 0.9, 0.97, 0.99, 1.0]

# Why a file needed a manual label (exposure_type_user)
CAUSE_DESCRIPTIONS = {
    'ml_not_run': 'ML never ran on the file (format not supported or not yet classified)',
    'confirmation': 'header == ML == user (user only confirmed, no correction needed)',
    'header_uk_ml_correct': 'header UK, ML correct -> solved if ML may fill header gaps',
    'header_uk_ml_abstained': 'header UK, ML abstained',
    'header_uk_ml_wrong': 'header UK, ML wrong',
    'header_correct_ml_abstained': 'header correct, ML abstained -> solved if abstaining is no veto',
    'header_correct_ml_wrong': 'header correct, ML wrong -> veto turned it into UK',
    'header_wrong_ml_correct': 'header wrong, ML correct -> ML cannot override the header',
    'header_wrong_ml_abstained': 'header wrong, ML abstained',
    'header_wrong_ml_wrong': 'header wrong, ML wrong',
}

# Why a file without a manual label is currently effectively UK
BACKLOG_DESCRIPTIONS = {
    'ml_not_run': 'ML never ran, header UK',
    'header_uk_ml_abstained': 'header UK, ML abstained',
    'header_uk_ml_confident': 'header UK, ML has a class -> resolvable if ML may fill gaps',
    'header_set_ml_abstained': 'header has a type, ML abstained -> resolvable without the abstain veto',
    'header_ml_disagree': 'header and ML disagree',
}

# What a combination rule would have produced for a manually labelled file
SIMULATION_DESCRIPTIONS = {
    'correct': 'rule result == manual label (no manual work needed)',
    'review': 'rule result UK (file lands in the review queue)',
    'wrong': 'rule result is a different type (silent error)',
}


def _bucket(confidence):
    if confidence is None:
        return 'n/a'
    lower = 0.0
    for upper in CONFIDENCE_BUCKETS:
        if confidence <= upper:
            return f'{lower:.2f}-{upper:.2f}'
        lower = upper
    return f'>{CONFIDENCE_BUCKETS[-1]:.2f}'


def _year(obs_date):
    obs_date = (obs_date or '').strip()
    return obs_date[:4] if obs_date[:4].isdigit() else 'unknown'


def _ml_state(row):
    """Return (ml_ran, ml_abstained, ml_type) for a DataFile values() row."""
    if row['exposure_type_ml_confidence'] is None:
        return False, False, None
    ml_type = (row['exposure_type_ml'] or '').strip() or UNKNOWN
    abstained = bool(row['exposure_type_ml_abstained']) or ml_type == UNKNOWN
    return True, abstained, ml_type


def classify_correction(row):
    """Assign a manually labelled file to one of CAUSE_DESCRIPTIONS."""
    user = row['exposure_type_user'].strip()
    header = row['exposure_type'] or UNKNOWN
    ml_ran, ml_abstained, ml_type = _ml_state(row)
    if not ml_ran:
        return 'ml_not_run'
    if ml_abstained:
        ml_part = 'ml_abstained'
    elif ml_type == user:
        ml_part = 'ml_correct'
    else:
        ml_part = 'ml_wrong'
    if header == UNKNOWN:
        header_part = 'header_uk'
    elif header == user:
        if ml_part == 'ml_correct':
            return 'confirmation'
        header_part = 'header_correct'
    else:
        header_part = 'header_wrong'
    return f'{header_part}_{ml_part}'


def classify_backlog(row):
    """Assign an effectively-UK file without manual label to BACKLOG_DESCRIPTIONS."""
    header = row['exposure_type'] or UNKNOWN
    ml_ran, ml_abstained, _ = _ml_state(row)
    if not ml_ran:
        return 'ml_not_run'
    if header == UNKNOWN:
        return 'header_uk_ml_abstained' if ml_abstained else 'header_uk_ml_confident'
    if ml_abstained:
        return 'header_set_ml_abstained'
    return 'header_ml_disagree'


class Command(BaseCommand):
    help = (
        'Report where manual exposure type corrections come from (header vs. ML) and how many '
        'files are currently effectively Unknown. Read-only.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--formats',
            nargs='+',
            default=None,
            help='Only include these file types (e.g. FITS TIFF). Default: all',
        )
        parser.add_argument(
            '--top',
            type=int,
            default=20,
            help='Maximum rows for breakdown tables (default: 20)',
        )
        parser.add_argument(
            '--read-headers',
            type=int,
            default=0,
            metavar='N',
            help=(
                'Read raw IMAGETYP/OBJECT from up to N FITS files whose header type is UK or whose '
                'type was corrected manually (disk access, default: 0 = off)'
            ),
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=None,
            help='Random seed for the --read-headers sample',
        )
        parser.add_argument(
            '--rule',
            choices=RULES,
            default=None,
            help='Combination rule for the backlog and the path token analysis (default: current setting)',
        )
        parser.add_argument(
            '--token-min-support',
            type=int,
            default=30,
            help='Path token analysis: minimum labelled files containing a token (default: 30)',
        )
        parser.add_argument(
            '--token-min-runs',
            type=int,
            default=3,
            help='Path token analysis: minimum observation runs containing a token (default: 3)',
        )
        parser.add_argument(
            '--token-min-purity',
            type=float,
            default=0.95,
            help='Path token analysis: minimum share of the dominant label (default: 0.95)',
        )
        parser.add_argument(
            '--token-max-run-share',
            type=float,
            default=0.25,
            help='Path token analysis: ignore tokens found in more than this share of all runs (default: 0.25)',
        )
        parser.add_argument(
            '--run-min-files',
            type=int,
            default=5,
            help='Spectrograph run heuristic: minimum LI/FL/WA files per run (default: 5)',
        )
        parser.add_argument(
            '--run-majority-share',
            type=float,
            default=0.8,
            help='Spectrograph run heuristic: minimum share of the majority spectrograph (default: 0.8)',
        )
        parser.add_argument(
            '--json',
            type=str,
            default=None,
            help='Write the full report to this JSON file',
        )

    def handle(self, *args, **options):
        formats = [f.upper() for f in options['formats']] if options['formats'] else None
        top = options['top']
        rng = random.Random(options['seed'])
        rule = options['rule'] or get_rule()

        queryset = DataFile.objects.all()
        if formats:
            queryset = queryset.filter(file_type__in=formats)
        queryset = queryset.annotate(annotated_effective_exposure_type=effective_exposure_type_expression(rule=rule))

        totals = Counter()
        effective = Counter()
        causes = Counter()
        causes_by = defaultdict(lambda: defaultdict(Counter))
        header_to_user = Counter()
        ml_to_user = Counter()
        ml_confidence = defaultdict(Counter)
        overrides = Counter()
        backlog = Counter()
        backlog_by = defaultdict(lambda: defaultdict(Counter))
        backlog_confidence = defaultdict(Counter)
        backlog_pairs = Counter()
        header_candidates = []
        user_by_file_type = defaultdict(Counter)
        simulation = {r: Counter() for r in RULES}
        simulation_by_file_type = {r: defaultdict(Counter) for r in RULES}
        token_labels = defaultdict(Counter)
        token_runs = defaultdict(set)
        problem_files = []
        spectrograph = SpectrographAnalysis(options)

        fields = (
            'pk', 'datafile', 'observation_run_id', 'file_type', 'instrument', 'obs_date', 'exposure_type',
            'exposure_type_ml', 'exposure_type_ml_confidence', 'exposure_type_ml_abstained',
            'exposure_type_user', 'exposure_type_override', 'spectrograph', 'spectrograph_override',
            'annotated_effective_exposure_type',
        )
        for row in queryset.values(*fields).iterator(chunk_size=2000):
            file_type = row['file_type'] or 'unknown'
            instrument = row['instrument'] or 'unknown'
            year = _year(row['obs_date'])
            ml_ran, ml_abstained, ml_type = _ml_state(row)
            user = (row['exposure_type_user'] or '').strip()
            header = row['exposure_type'] or UNKNOWN
            tokens = path_tokens(row['datafile'])

            totals['files'] += 1
            totals[f'file_type:{file_type}'] += 1
            totals['ml_ran'] += ml_ran
            totals['ml_abstained'] += ml_abstained
            totals['spectrograph_override'] += bool(row['spectrograph_override'])
            effective[row['annotated_effective_exposure_type']] += 1

            truth = None
            if user:
                truth = user
                totals['user_labelled'] += 1
                cause = classify_correction(row)
                causes[cause] += 1
                for dim, value in (('file_type', file_type), ('instrument', instrument), ('year', year)):
                    causes_by[dim][value][cause] += 1
                header_to_user[f"{row['exposure_type'] or UNKNOWN} -> {user}"] += 1
                user_by_file_type[file_type][user] += 1
                for r in RULES:
                    result = effective_exposure_type(header, row['exposure_type_ml'], None, r)
                    outcome = 'correct' if result == user else 'review' if result == UNKNOWN else 'wrong'
                    simulation[r][outcome] += 1
                    simulation_by_file_type[r][file_type][outcome] += 1
                if ml_ran:
                    ml_to_user[f"{ml_type} -> {user}"] += 1
                    if not ml_abstained:
                        verdict = 'correct' if ml_type == user else 'wrong'
                        ml_confidence[_bucket(row['exposure_type_ml_confidence'])][verdict] += 1
            elif row['exposure_type_override']:
                # Older corrections edited the header field directly, the original header value is lost
                truth = row['exposure_type']
                totals['header_field_overridden'] += 1
                if not ml_ran:
                    overrides['ml_not_run'] += 1
                elif ml_abstained:
                    overrides['ml_abstained'] += 1
                else:
                    verdict = 'correct' if ml_type == truth else 'wrong'
                    overrides[f'ml_{verdict}'] += 1
                    ml_confidence[_bucket(row['exposure_type_ml_confidence'])][verdict] += 1
            elif row['annotated_effective_exposure_type'] == UNKNOWN:
                category = classify_backlog(row)
                backlog[category] += 1
                for dim, value in (('file_type', file_type), ('instrument', instrument), ('year', year)):
                    backlog_by[dim][value][category] += 1
                if category == 'header_ml_disagree':
                    backlog_pairs[f"{row['exposure_type']} -> {ml_type}"] += 1
                if ml_ran and not ml_abstained:
                    backlog_confidence[category][_bucket(row['exposure_type_ml_confidence'])] += 1

            # Trusted label for the path token analysis: manual label or header/ML agreement
            token_truth = user or (header if header != UNKNOWN and row['exposure_type_ml'] == header else None)
            if token_truth:
                for token in tokens:
                    token_labels[token][token_truth] += 1
                    token_runs[token].add(row['observation_run_id'])
            if effective_exposure_type(header, row['exposure_type_ml'], None, rule) == UNKNOWN:
                problem_files.append((tokens, user or None, file_type))
            spectrograph.add(
                row, user or row['annotated_effective_exposure_type'], ml_ran, ml_abstained, ml_type, tokens,
                instrument, year,
            )

            if options['read_headers'] and file_type == 'FITS':
                corrected = truth is not None and (row['exposure_type_override'] or truth != row['exposure_type'])
                if row['exposure_type'] == UNKNOWN or corrected:
                    label = truth or (ml_type if ml_ran and not ml_abstained else UNKNOWN)
                    header_candidates.append((row['datafile'], label, 'manual' if truth else 'ml'))

        raw_headers = self._read_raw_headers(header_candidates, options['read_headers'], rng)
        path_token_analysis = self._analyse_path_tokens(token_labels, token_runs, problem_files, options)

        report = {
            'filter_formats': formats,
            'rule': rule,
            'totals': dict(totals),
            'effective_exposure_type': dict(effective),
            'manual_labels': {
                'causes': dict(causes),
                'by': {dim: {k: dict(v) for k, v in values.items()} for dim, values in causes_by.items()},
                'header_to_user': dict(header_to_user),
                'ml_to_user': dict(ml_to_user),
                'user_by_file_type': {k: dict(v) for k, v in user_by_file_type.items()},
                'rule_simulation': {r: dict(v) for r, v in simulation.items()},
                'rule_simulation_by_file_type': {
                    r: {k: dict(v) for k, v in by.items()} for r, by in simulation_by_file_type.items()
                },
            },
            'header_field_overrides': dict(overrides),
            'ml_confidence_vs_truth': {k: dict(v) for k, v in ml_confidence.items()},
            'backlog_effective_uk': {
                'categories': dict(backlog),
                'by': {dim: {k: dict(v) for k, v in values.items()} for dim, values in backlog_by.items()},
                'ml_confidence': {k: dict(v) for k, v in backlog_confidence.items()},
                'header_to_ml_disagreements': dict(backlog_pairs),
            },
            'raw_headers': raw_headers,
            'path_tokens': path_token_analysis,
            'spectrograph': spectrograph.finish(),
        }

        self._options = options
        self._print_report(report, top)

        if options['json']:
            out = Path(options['json'])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            self.stdout.write(self.style.SUCCESS(f'\nReport written to {out}'))

    def _analyse_path_tokens(self, token_labels, token_runs, problem_files, options):
        """
        Find path tokens that reliably indicate one exposure type, then estimate how many files the
        combination rule leaves at UK could be resolved by them (and how often correctly).
        """
        indicative = indicative_tokens(
            token_labels, token_runs, options['token_min_support'], options['token_min_runs'],
            options['token_min_purity'], options['token_max_run_share'],
        )

        outcome = Counter()
        outcome_by_file_type = defaultdict(Counter)
        for tokens, truth, file_type in problem_files:
            labels = {indicative[t]['label'] for t in tokens if t in indicative}
            if not labels:
                result = 'no_token'
            elif len(labels) > 1:
                result = 'conflicting_tokens'
            else:
                label = labels.pop()
                result = 'unverified' if truth is None else 'correct' if label == truth else 'wrong'
            outcome[result] += 1
            outcome_by_file_type[file_type][result] += 1

        return {
            'indicative_tokens': indicative,
            'rule_uk_files': len(problem_files),
            'rule_uk_outcome': dict(outcome),
            'rule_uk_outcome_by_file_type': {k: dict(v) for k, v in outcome_by_file_type.items()},
        }

    def _read_raw_headers(self, candidates, limit, rng):
        if not limit or not candidates:
            return None
        sample = rng.sample(candidates, min(limit, len(candidates)))
        imagetyp = defaultdict(Counter)
        objects = defaultdict(Counter)
        errors = 0
        for path, label, source in sample:
            try:
                header = fits.getheader(path, 0, ignore_missing_simple=True)
            except Exception:
                errors += 1
                continue
            raw_type = str(header.get('IMAGETYP', '<missing>')).strip() or '<empty>'
            raw_object = str(header.get('OBJECT', '<missing>')).strip() or '<empty>'
            imagetyp[raw_type][f'{label} ({source})'] += 1
            objects[raw_object][f'{label} ({source})'] += 1
        return {
            'candidates': len(candidates),
            'sampled': len(sample),
            'read_errors': errors,
            'imagetyp': {k: dict(v) for k, v in imagetyp.items()},
            'object': {k: dict(v) for k, v in objects.items()},
        }

    # --- Output -------------------------------------------------------------------------------

    def _section(self, title):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(title))

    def _counter_table(self, counter, descriptions=None, top=None):
        total = sum(counter.values())
        if not total:
            self.stdout.write('  (none)')
            return
        for key, count in Counter(counter).most_common(top):
            label = f'{key:<30}'
            if descriptions:
                label += f'  {descriptions.get(key, "")}'
            self.stdout.write(f'  {count:>8}  {count / total:6.1%}  {label}')

    def _breakdown_table(self, by_value, columns, top):
        """Rows = values of a dimension (largest first), columns = categories."""
        rows = sorted(by_value.items(), key=lambda kv: -sum(kv[1].values()))[:top]
        if not rows:
            self.stdout.write('  (none)')
            return
        columns = [c for c in columns if any(r[1].get(c) for r in rows)]
        width = max(len(str(r[0])) for r in rows)
        self.stdout.write('  ' + ' ' * width + '  ' + ''.join(f'{i:>8}' for i in range(1, len(columns) + 1)) + '     total')
        for value, counts in rows:
            cells = ''.join(f'{counts.get(c, 0):>8}' for c in columns)
            self.stdout.write(f'  {str(value):<{width}}  {cells}  {sum(counts.values()):>8}')
        for i, column in enumerate(columns, 1):
            self.stdout.write(f'    {i}: {column}')

    def _print_report(self, report, top):
        totals = report['totals']
        self._section('Overview')
        self.stdout.write(f"  Files:                              {totals.get('files', 0)}")
        for key in sorted(k for k in totals if k.startswith('file_type:')):
            self.stdout.write(f'    {key[len("file_type:"):]:<32}  {totals[key]}')
        self.stdout.write(f"  ML classified:                      {totals.get('ml_ran', 0)}")
        self.stdout.write(f"  ML abstained:                       {totals.get('ml_abstained', 0)}")
        self.stdout.write(f"  Manual label (exposure_type_user):  {totals.get('user_labelled', 0)}")
        self.stdout.write(f"  Header field edited manually:       {totals.get('header_field_overridden', 0)}")
        self.stdout.write(f"  Spectrograph edited manually:       {totals.get('spectrograph_override', 0)}")
        self.stdout.write('  Effective exposure type:')
        self._counter_table(report['effective_exposure_type'])

        manual = report['manual_labels']
        self._section('Manual labels: cause')
        self._counter_table(manual['causes'], CAUSE_DESCRIPTIONS)
        for dim in ('file_type', 'instrument', 'year'):
            self._section(f'Manual labels: cause by {dim}')
            self._breakdown_table(manual['by'].get(dim, {}), list(CAUSE_DESCRIPTIONS), top)
        self._section('Manual labels: header -> user')
        self._counter_table(manual['header_to_user'], top=top)
        self._section('Manual labels: ML -> user')
        self._counter_table(manual['ml_to_user'], top=top)

        self._section('Manual labels: label by file type')
        self._breakdown_table(manual['user_by_file_type'], ['LI', 'DA', 'FL', 'BI', 'WA', 'UK'], top)
        for r in RULES:
            self._section(f'Rule simulation on manual labels: {r}')
            self._counter_table(manual['rule_simulation'][r], SIMULATION_DESCRIPTIONS)
            self._breakdown_table(manual['rule_simulation_by_file_type'][r], list(SIMULATION_DESCRIPTIONS), top)

        self._section('Header field edited manually (no exposure_type_user): ML vs. corrected value')
        self._counter_table(report['header_field_overrides'])

        self._section('ML confidence vs. manual truth (non-abstained ML, all manual corrections)')
        confidence = report['ml_confidence_vs_truth']
        for bucket in sorted(confidence):
            counts = confidence[bucket]
            n = sum(counts.values())
            self.stdout.write(
                f"  {bucket:<10}  correct {counts.get('correct', 0):>7}  wrong {counts.get('wrong', 0):>7}"
                f"  precision {counts.get('correct', 0) / n:6.1%}"
            )
        if not confidence:
            self.stdout.write('  (none)')

        backlog = report['backlog_effective_uk']
        self._section(f"Backlog: effectively UK under rule '{report['rule']}', not yet corrected")
        self._counter_table(backlog['categories'], BACKLOG_DESCRIPTIONS)
        for dim in ('file_type', 'instrument', 'year'):
            self._section(f'Backlog by {dim}')
            self._breakdown_table(backlog['by'].get(dim, {}), list(BACKLOG_DESCRIPTIONS), top)
        self._section('Backlog: header -> ML (disagreements)')
        self._counter_table(backlog['header_to_ml_disagreements'], top=top)
        self._section('Backlog: ML confidence where ML has a class')
        for category, buckets in backlog['ml_confidence'].items():
            self.stdout.write(f'  {category}:')
            for bucket in sorted(buckets):
                self.stdout.write(f'    {bucket:<10}  {buckets[bucket]:>8}')
        if not backlog['ml_confidence']:
            self.stdout.write('  (none)')

        tokens = report['path_tokens']
        self._section(
            f"Path tokens indicating one type (support >= {self._options['token_min_support']}, "
            f"runs >= {self._options['token_min_runs']}, purity >= {self._options['token_min_purity']:.0%})"
        )
        for token, info in list(tokens['indicative_tokens'].items())[:top]:
            self.stdout.write(
                f"  {token:<24}  {info['label']}  purity {info['purity']:6.1%}  "
                f"files {info['support']:>8}  runs {info['runs']:>5}"
            )
        if not tokens['indicative_tokens']:
            self.stdout.write('  (none)')
        self._section(
            f"Path tokens applied to the {tokens['rule_uk_files']} files rule '{report['rule']}' leaves at UK "
            '(correct/wrong vs. manual label)'
        )
        self._counter_table(tokens['rule_uk_outcome'])
        self._breakdown_table(
            tokens['rule_uk_outcome_by_file_type'],
            ['correct', 'wrong', 'unverified', 'conflicting_tokens', 'no_token'], top,
        )

        raw = report['raw_headers']
        if raw:
            self._section(
                f"Raw FITS headers ({raw['sampled']} of {raw['candidates']} candidates, "
                f"{raw['read_errors']} read errors)"
            )
            for key in ('imagetyp', 'object'):
                self.stdout.write(f'  {key.upper()} -> label (source):')
                values = sorted(raw[key].items(), key=lambda kv: -sum(kv[1].values()))
                for value, labels in values[:top]:
                    detail = ', '.join(f'{lbl}: {n}' for lbl, n in Counter(labels).most_common())
                    self.stdout.write(f'    {value!r:<32}  {detail}')

        print_spectrograph_report(self, report['spectrograph'], top)
