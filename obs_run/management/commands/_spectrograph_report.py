"""
Spectrograph part of the exposure_type_report command.

The spectrograph is only set by the ML classifier (or manually, which sets ``spectrograph_override``).
The value the classifier produced before a manual correction is not stored separately, so it is
recovered from the DataFile history.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from obs_run.exposure_type import UNKNOWN, classifier_class_name
from obs_run.models import DataFile
from obs_run.spectrograph import constrained_spectrograph

TOKEN_PATTERN = re.compile(r'[a-z]{3,}')

# Exposure types for which the spectrograph matters
SPECTROGRAPH_RELEVANT = ('LI', 'FL', 'WA')

# History change reasons written by admin/API endpoints (history_user is set for API requests too)
MANUAL_REASON_PREFIXES = ('admin:', 'api:')

CORRECTION_DETECTION_DESCRIPTIONS = {
    'flagged_correct': 'run majority heuristic flags the file and suggests the corrected value',
    'flagged_wrong': 'run majority heuristic flags the file but suggests another value',
    'not_flagged': 'run majority heuristic does not flag the file',
}

RULE_SIMULATION_DESCRIPTIONS = {
    'fixed': 'spectrograph rules produce the manually corrected value',
    'unchanged': 'rules keep the wrong automatic value (correction still needed)',
    'changed_wrong': 'rules change the value, but not to the corrected one',
    'kept': 'confirmed automatic value is kept',
    'broken': 'rules change a value that was confirmed as correct',
}

TOKEN_PREDICTION_DESCRIPTIONS = {
    'correct': 'indicative path token predicts the corrected value',
    'wrong': 'indicative path token predicts another value',
    'conflicting_tokens': 'path tokens point to different spectrographs',
    'no_token': 'no indicative path token',
}


def path_tokens(path):
    """Lower-case letter tokens (>= 3 chars) from directory names and file stem."""
    tokens = TOKEN_PATTERN.findall(str(Path(path or '').with_suffix('')).lower())
    return tuple(sorted({sys.intern(t) for t in tokens}))


def indicative_tokens(token_labels, token_runs, min_support, min_runs, min_purity, max_run_share):
    """
    Tokens whose files carry (almost) always the same label, across several runs. Tokens found in more
    than ``max_run_share`` of all runs are generic path components (e.g. the archive mount point) and only
    mirror the overall label distribution, so they are ignored.
    """
    all_runs = set().union(*token_runs.values()) if token_runs else set()
    max_runs = max_run_share * len(all_runs)
    indicative = {}
    for token, labels in token_labels.items():
        support = sum(labels.values())
        label, count = labels.most_common(1)[0]
        runs = len(token_runs[token])
        if support >= min_support and min_runs <= runs <= max_runs and count / support >= min_purity:
            indicative[token] = {
                'label': label, 'purity': round(count / support, 4), 'support': support,
                'runs': len(token_runs[token]),
            }
    return dict(sorted(indicative.items(), key=lambda kv: -kv[1]['support']))


def token_label(tokens, indicative):
    """Single label suggested by the indicative tokens of a file, 'conflict' or None."""
    labels = {indicative[t]['label'] for t in tokens if t in indicative}
    if len(labels) > 1:
        return 'conflict'
    return labels.pop() if labels else None


def _auto_value(records):
    """Spectrograph before the first manual change; records = [(spectrograph, user_id, reason), ...]."""
    for previous, current in zip(records, records[1:]):
        manual = current[1] is not None or (current[2] or '').startswith(MANUAL_REASON_PREFIXES)
        if manual and current[0] != previous[0]:
            return previous[0] or 'N'
    if len({r[0] for r in records}) == 1:
        # Never changed: the override only confirmed the automatic value
        return records[0][0] or 'N'
    return 'unknown'


def auto_spectrograph_values(pks):
    """pk -> spectrograph value set automatically before the first manual change ('unknown' if unclear)."""
    history = DataFile.history.model
    pks = list(pks)
    result = {}
    for start in range(0, len(pks), 1000):
        rows = (
            history.objects.filter(id__in=pks[start:start + 1000])
            .order_by('id', 'history_date', 'history_id')
            .values_list('id', 'spectrograph', 'history_user_id', 'history_change_reason')
        )
        by_pk = defaultdict(list)
        for pk, spectrograph, user_id, reason in rows:
            by_pk[pk].append((spectrograph, user_id, reason))
        for pk, records in by_pk.items():
            result[pk] = _auto_value(records)
    return result


def _nested(by):
    return {k: dict(v) for k, v in by.items()}


class SpectrographAnalysis:
    def __init__(self, options):
        self.options = options
        self.totals = Counter()
        self.by_type = defaultdict(Counter)
        self.by_instrument = defaultdict(Counter)
        self.invalid = defaultdict(Counter)
        self.token_labels = defaultdict(Counter)
        self.token_runs = defaultdict(set)
        # (pk, run id, spectrograph, override, tokens) for files where the spectrograph matters
        self.files = []
        # pk -> details of manually corrected files
        self.overridden = {}
        self.rule_changes = Counter()

    def add(self, row, exposure_type, ml_ran, ml_abstained, ml_type, tokens, instrument, year):
        """``exposure_type``: manual label if set, else the effective type."""
        spectrograph = row['spectrograph'] or 'N'
        override = bool(row['spectrograph_override'])
        self.totals[spectrograph] += 1
        self.totals['override'] += override
        self.by_type[exposure_type][spectrograph] += 1
        if exposure_type != UNKNOWN and classifier_class_name(exposure_type, spectrograph) is None:
            self.invalid[f'{exposure_type}/{spectrograph}']['manual' if override else 'automatic'] += 1
        if not override:
            value, reason = constrained_spectrograph(exposure_type, row['instrument'], spectrograph)
            if value != spectrograph:
                self.rule_changes[f'{spectrograph} -> {value} ({reason})'] += 1
        if override:
            self.overridden[row['pk']] = {
                'spectrograph': spectrograph, 'exposure_type': exposure_type, 'ml_ran': ml_ran,
                'ml_abstained': ml_abstained, 'ml_type': ml_type, 'instrument': instrument, 'year': year,
                'raw_instrument': row['instrument'],
            }
        if exposure_type not in SPECTROGRAPH_RELEVANT:
            return
        self.by_instrument[instrument][spectrograph] += 1
        for token in tokens:
            self.token_labels[token][spectrograph] += 1
            self.token_runs[token].add(row['observation_run_id'])
        self.files.append((row['pk'], row['observation_run_id'], spectrograph, override, tokens))

    def finish(self):
        auto = auto_spectrograph_values(self.overridden)

        corrections = Counter()
        corrections_by = defaultdict(lambda: defaultdict(Counter))
        confusion = Counter()
        class_accuracy = defaultdict(Counter)
        rule_simulation = Counter()
        for pk, info in self.overridden.items():
            before, after = auto.get(pk, 'unknown'), info['spectrograph']
            if before != 'unknown':
                result, reason = constrained_spectrograph(info['exposure_type'], info['raw_instrument'], before)
                if before != after:
                    outcome = 'fixed' if result == after else 'unchanged' if result == before else 'changed_wrong'
                else:
                    outcome = 'kept' if result == after else 'broken'
                rule_simulation[outcome + (f' ({reason})' if reason else '')] += 1
            key = 'confirmed' if before == after else f'{before} -> {after}'
            corrections[key] += 1
            for dim in ('instrument', 'year', 'exposure_type'):
                corrections_by[dim][info[dim]][key] += 1
            if info['ml_ran'] and before != 'unknown':
                if info['ml_abstained']:
                    ml_class = 'unknown'
                else:
                    ml_class = classifier_class_name(info['ml_type'], before) or f"invalid({info['ml_type']}/{before})"
                true_class = (
                    classifier_class_name(info['exposure_type'], after) or f"invalid({info['exposure_type']}/{after})"
                )
                confusion[f'{ml_class} -> {true_class}'] += 1
                class_accuracy[true_class]['correct' if ml_class == true_class else 'wrong'] += 1

        # Run majority heuristic on the state before manual corrections
        state = {}
        run_counts = defaultdict(Counter)
        for pk, run, spectrograph, override, _ in self.files:
            value = auto.get(pk, spectrograph) if override else spectrograph
            if value == 'unknown':
                value = spectrograph
            state[pk] = value
            run_counts[run][value] += 1
        run_suspicious = Counter()
        correction_detection = Counter()
        indicative = indicative_tokens(
            self.token_labels, self.token_runs, self.options['token_min_support'],
            self.options['token_min_runs'], self.options['token_min_purity'], self.options['token_max_run_share'],
        )
        token_suspicious = Counter()
        token_prediction = Counter()
        for pk, run, spectrograph, override, tokens in self.files:
            value = state[pk]
            counts = run_counts[run]
            total = sum(counts.values())
            majority, count = counts.most_common(1)[0]
            flagged = (
                total >= self.options['run_min_files'] and count / total >= self.options['run_majority_share']
                and value != majority
            )
            suggestion = token_label(tokens, indicative)
            corrected = override and value != spectrograph
            if corrected:
                if flagged:
                    correction_detection['flagged_correct' if majority == spectrograph else 'flagged_wrong'] += 1
                else:
                    correction_detection['not_flagged'] += 1
                if suggestion is None:
                    token_prediction['no_token'] += 1
                elif suggestion == 'conflict':
                    token_prediction['conflicting_tokens'] += 1
                else:
                    token_prediction['correct' if suggestion == spectrograph else 'wrong'] += 1
            elif not override:
                if flagged:
                    run_suspicious[f'{spectrograph} (run majority {majority})'] += 1
                if suggestion not in (None, 'conflict') and suggestion != spectrograph:
                    token_suspicious[f'{spectrograph} (token says {suggestion})'] += 1

        return {
            'totals': dict(self.totals),
            'by_exposure_type': _nested(self.by_type),
            'by_instrument': _nested(self.by_instrument),
            'invalid_combinations': _nested(self.invalid),
            'corrections': dict(corrections),
            'corrections_by': {dim: _nested(by) for dim, by in corrections_by.items()},
            'class_confusion': dict(confusion),
            'class_accuracy': _nested(class_accuracy),
            'rule_simulation_on_corrections': dict(rule_simulation),
            'rule_changes_uncorrected': dict(self.rule_changes),
            'correction_detection_run_majority': dict(correction_detection),
            'suspicious_run_majority': dict(run_suspicious),
            'indicative_tokens': indicative,
            'correction_prediction_tokens': dict(token_prediction),
            'suspicious_tokens': dict(token_suspicious),
        }


def print_spectrograph_report(cmd, report, top):
    """Print the spectrograph section with the table helpers of the exposure_type_report command."""
    options = cmd._options
    spectrographs = ['N', 'D', 'B', 'E']

    cmd._section('Spectrograph: overview (D = DADOS, B = BACHES, E = Einsteinturm, N = none)')
    cmd._counter_table({k: v for k, v in report['totals'].items() if k != 'override'})
    cmd.stdout.write(f"  Manually corrected (spectrograph_override): {report['totals'].get('override', 0)}")
    cmd._section('Spectrograph by exposure type (manual label, else effective type)')
    cmd._breakdown_table(report['by_exposure_type'], spectrographs, top)
    cmd._section('Spectrograph by instrument (LI/FL/WA only)')
    cmd._breakdown_table(report['by_instrument'], spectrographs, top)
    cmd._section('Spectrograph: invalid exposure type/spectrograph combinations (no classifier class)')
    cmd._breakdown_table(report['invalid_combinations'], ['automatic', 'manual'], top)

    cmd._section('Spectrograph corrections: automatic value (from history) -> manual value')
    cmd._counter_table(report['corrections'], top=top)
    for dim in ('exposure_type', 'instrument', 'year'):
        cmd._section(f'Spectrograph corrections by {dim}')
        by = report['corrections_by'].get(dim, {})
        columns = [k for k, _ in Counter(report['corrections']).most_common(8)]
        cmd._breakdown_table(by, columns, top)

    cmd._section('Classifier class -> true class (spectrograph-corrected files, mismatches)')
    mismatches = {k: v for k, v in report['class_confusion'].items() if k.split(' -> ')[0] != k.split(' -> ')[1]}
    cmd._counter_table(mismatches, top=top)
    cmd._section('Classifier accuracy per true class (spectrograph-corrected files)')
    cmd._breakdown_table(report['class_accuracy'], ['correct', 'wrong'], top)

    cmd._section('Spectrograph rules (obs_run/spectrograph.py) simulated on past corrections')
    descriptions = {
        key: RULE_SIMULATION_DESCRIPTIONS.get(key.split(' (')[0], '') for key in report['rule_simulation_on_corrections']
    }
    cmd._counter_table(report['rule_simulation_on_corrections'], descriptions)
    cmd._section('Spectrograph rules: changes to uncorrected files (apply_spectrograph_rules)')
    cmd._counter_table(report['rule_changes_uncorrected'], top=top)

    cmd._section(
        f"Run majority heuristic (runs >= {options['run_min_files']} LI/FL/WA files, "
        f"majority >= {options['run_majority_share']:.0%}) on past corrections"
    )
    cmd._counter_table(report['correction_detection_run_majority'], CORRECTION_DETECTION_DESCRIPTIONS)
    cmd._section('Run majority heuristic: uncorrected files deviating from their run (suspicious)')
    cmd._counter_table(report['suspicious_run_majority'], top=top)

    cmd._section('Path tokens indicating a spectrograph')
    for token, info in list(report['indicative_tokens'].items())[:top]:
        cmd.stdout.write(
            f"  {token:<24}  {info['label']}  purity {info['purity']:6.1%}  "
            f"files {info['support']:>8}  runs {info['runs']:>5}"
        )
    if not report['indicative_tokens']:
        cmd.stdout.write('  (none)')
    cmd._section('Path tokens on past corrections')
    cmd._counter_table(report['correction_prediction_tokens'], TOKEN_PREDICTION_DESCRIPTIONS)
    cmd._section('Path tokens: uncorrected files contradicting a token (suspicious)')
    cmd._counter_table(report['suspicious_tokens'], top=top)
