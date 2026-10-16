"""
Spectrograph suggestions from two heuristics, and their evaluation on manually reviewed files.

- Run majority: a file whose spectrograph differs from the value of a clear majority of its run.
- Path tokens: words in directory/file names that (almost) always come with one spectrograph.

Only files with an effective type LI/FL/WA are considered (bias/darks never carry a spectrograph).
Suggestions are stored in ``SpectrographSuggestion`` for files without a manual spectrograph; the
evaluation on manually reviewed files (``spectrograph_override``) in ``HeuristicReport``. The value the
classifier produced before a review is not stored separately, so it is recovered from the history.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from obs_run.exposure_type import effective_exposure_type_expression
from obs_run.image_quality import BAD_FLAGS as BAD_QUALITY_FLAGS
from obs_run.models import DataFile, HeuristicReport, SpectrographSuggestion

TOKEN_PATTERN = re.compile(r'[a-z]{3,}')

# Exposure types for which the spectrograph matters
SPECTROGRAPH_RELEVANT = ('LI', 'FL', 'WA')

# History change reasons written by admin/API endpoints (history_user is set for API requests too)
MANUAL_REASON_PREFIXES = ('admin:', 'api:')

REPORT_NAME = 'spectrograph_suggestions'

DEFAULT_PARAMS = {
    'run_min_files': 5,
    'run_majority_share': 0.8,
    'token_min_support': 30,
    'token_min_runs': 3,
    'token_min_purity': 0.95,
    'token_max_run_share': 0.25,
}

HEURISTICS = ('run_majority', 'path_token', 'both')


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


def run_majority(counts, min_files, min_share):
    """Majority value of a run if the run is large and uniform enough, else None."""
    total = sum(counts.values())
    if not total:
        return None
    value, count = counts.most_common(1)[0]
    return value if total >= min_files and count / total >= min_share else None


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


def _suggestions(spectrograph, tokens, run_counts, indicative, params):
    """(run majority suggestion, path token suggestion) differing from ``spectrograph``, else None."""
    majority = run_majority(run_counts, params['run_min_files'], params['run_majority_share'])
    by_run = majority if majority and majority != spectrograph else None
    label = token_label(tokens, indicative)
    by_token = label if label not in (None, 'conflict') and label != spectrograph else None
    return by_run, by_token


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def analyse(params=None):
    """
    Compute suggestions for files without a manual spectrograph and evaluate both heuristics on the
    manually reviewed files (state before the review vs. manual value).
    """
    params = {**DEFAULT_PARAMS, **(params or {})}
    queryset = (
        DataFile.objects
        .annotate(annotated_effective_exposure_type=effective_exposure_type_expression())
        .filter(annotated_effective_exposure_type__in=SPECTROGRAPH_RELEVANT)
        .exclude(quality_flag__in=BAD_QUALITY_FLAGS)
        .values_list('pk', 'observation_run_id', 'spectrograph', 'spectrograph_override', 'datafile')
    )
    files = []
    token_labels = defaultdict(Counter)
    token_runs = defaultdict(set)
    current_counts = defaultdict(Counter)
    for pk, run, spectrograph, override, path in queryset.iterator(chunk_size=2000):
        spectrograph = spectrograph or 'N'
        tokens = path_tokens(path)
        files.append((pk, run, spectrograph, override, tokens))
        current_counts[run][spectrograph] += 1
        for token in tokens:
            token_labels[token][spectrograph] += 1
            token_runs[token].add(run)

    indicative = indicative_tokens(
        token_labels, token_runs, params['token_min_support'], params['token_min_runs'],
        params['token_min_purity'], params['token_max_run_share'],
    )

    # State before manual review: automatic value for reviewed files (from history), current otherwise
    auto = auto_spectrograph_values(pk for pk, _, _, override, _ in files if override)
    before = {}
    before_counts = defaultdict(Counter)
    for pk, run, spectrograph, override, _ in files:
        value = auto.get(pk, spectrograph) if override else spectrograph
        before[pk] = spectrograph if value == 'unknown' else value
        before_counts[run][before[pk]] += 1

    suggestions = {}
    open_counts = Counter()
    reviewed = 0
    outcomes = {name: Counter() for name in HEURISTICS}
    transitions = {name: defaultdict(Counter) for name in HEURISTICS}
    for pk, run, spectrograph, override, tokens in files:
        if not override:
            by_run, by_token = _suggestions(spectrograph, tokens, current_counts[run], indicative, params)
            if by_run or by_token:
                suggestions[pk] = (by_run, by_token)
                open_counts['run_majority'] += by_run is not None
                open_counts['path_token'] += by_token is not None
                open_counts['both'] += by_run is not None and by_run == by_token
                open_counts['any'] += 1
            continue
        if auto.get(pk, 'unknown') == 'unknown':
            continue
        reviewed += 1
        value = before[pk]
        by_run, by_token = _suggestions(value, tokens, before_counts[run], indicative, params)
        both = by_run if by_run is not None and by_run == by_token else None
        for name, suggestion in zip(HEURISTICS, (by_run, by_token, both)):
            if suggestion is None:
                outcome = 'fn' if spectrograph != value else 'tn'
            else:
                outcome = 'tp' if suggestion == spectrograph else 'fp'
                transitions[name][f'{value} -> {suggestion}'][outcome] += 1
            outcomes[name][outcome] += 1

    evaluation = {}
    for name in HEURISTICS:
        counts = outcomes[name]
        tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
        evaluation[name] = {
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': counts['tn'],
            'precision': _ratio(tp, tp + fp), 'recall': _ratio(tp, tp + fn),
            'transitions': {k: dict(v) for k, v in sorted(transitions[name].items(), key=lambda kv: -sum(kv[1].values()))},
        }

    return {
        'params': params,
        'suggestions': suggestions,
        'report': {
            'evaluation': evaluation,
            'reviewed_files': reviewed,
            'open_suggestions': dict(open_counts),
            'indicative_tokens': {
                token: info for token, info in indicative.items() if info['label'] != 'N'
            },
            'indicative_tokens_total': len(indicative),
        },
    }


def recompute_suggestions(params=None):
    """Run ``analyse`` and replace the stored suggestions and report atomically."""
    result = analyse(params)
    now = timezone.now()
    with transaction.atomic():
        SpectrographSuggestion.objects.all().delete()
        SpectrographSuggestion.objects.bulk_create(
            [
                SpectrographSuggestion(datafile_id=pk, run_majority=by_run, path_token=by_token, computed_at=now)
                for pk, (by_run, by_token) in result['suggestions'].items()
            ],
            batch_size=2000,
        )
        HeuristicReport.objects.update_or_create(
            name=REPORT_NAME,
            defaults={'computed_at': now, 'params': result['params'], 'data': result['report']},
        )
    return result
