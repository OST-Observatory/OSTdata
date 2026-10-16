"""
Training data export for ost_image_classification, format v2 (see export_cnn_training_data).

One record per file with class label, label source, metadata and split. Compared to v1:
- Labels: manual labels (incl. files where header or classifier were wrong, marked ``hard``) and
  header/classifier agreement; no year restriction by default.
- Splits are assigned per observation run, so frames of one run never end up in two splits.
- Per-class caps keep all hard files and spread the remaining quota over runs.
"""
from collections import Counter, defaultdict
from itertools import zip_longest
from pathlib import Path

from obs_run.exposure_type import classifier_class_name
from obs_run.image_quality import BAD_FLAGS as BAD_QUALITY_FLAGS
from obs_run.management.commands.exposure_type_report import _year, classify_correction
from obs_run.models import DataFile
from obs_run.spectrograph_heuristics import auto_spectrograph_values

FORMAT = 'ost-classification-export/v2'
SPLITS = ('train', 'val', 'test')
UNKNOWN = DataFile.UNKNOWN

# Manual exposure labels where header and classifier already agreed with the label are not "hard"
NOT_HARD_CAUSES = ('confirmation', 'ml_not_run')

FIELDS = (
    'pk', 'datafile', 'observation_run_id', 'observation_run__spectroscopy', 'file_type', 'instrument_normalized',
    'obs_date', 'exptime', 'plate_solved', 'exposure_type', 'exposure_type_ml', 'exposure_type_ml_confidence',
    'exposure_type_ml_abstained', 'exposure_type_user', 'spectrograph', 'spectrograph_override',
)


def label(row):
    """(class, label source) of a DataFile values() row, None if the file has no reliable class."""
    user = (row['exposure_type_user'] or '').strip()
    header = row['exposure_type'] or UNKNOWN
    ml = (row['exposure_type_ml'] or '').strip()
    if user:
        exposure_type, source = user, 'manual'
    elif ml and ml != UNKNOWN and ml == header:
        exposure_type, source = header, 'agreement'
    else:
        return None
    if row['spectrograph_override']:
        source = 'manual'
    class_name = classifier_class_name(exposure_type, row['spectrograph'] or 'N')
    return (class_name, source) if class_name else None


def collect_records(formats, data_directory, min_year=None):
    """Labelled files below ``data_directory`` as export records (without split)."""
    data_directory = Path(str(data_directory)).resolve()
    queryset = DataFile.objects.filter(file_type__in=formats).exclude(quality_flag__in=BAD_QUALITY_FLAGS).values(*FIELDS)
    records = []
    spectrograph_reviewed = []
    for row in queryset.iterator(chunk_size=2000):
        labelled = label(row)
        if labelled is None:
            continue
        year = _year(row['obs_date'])
        year = int(year) if year.isdigit() else None
        if min_year and (year is None or year < min_year):
            continue
        try:
            path = Path(row['datafile']).relative_to(data_directory)
        except ValueError:
            continue
        user = (row['exposure_type_user'] or '').strip()
        hard = bool(user) and classify_correction(row) not in NOT_HARD_CAUSES
        if row['spectrograph_override']:
            spectrograph_reviewed.append(row['pk'])
        records.append({
            'pk': row['pk'],
            'path': str(path),
            'class': labelled[0],
            'label_source': labelled[1],
            'hard': hard,
            'run': row['observation_run_id'],
            'instrument': row['instrument_normalized'] or '',
            'year': year,
            'file_type': row['file_type'],
            'exptime': row['exptime'],
            'plate_solved': bool(row['plate_solved']),
            'run_spectroscopy': bool(row['observation_run__spectroscopy']),
            '_spectrograph': row['spectrograph'] or 'N',
        })

    # A manual spectrograph correction (classifier value from the history differs) also makes a file hard
    auto = auto_spectrograph_values(spectrograph_reviewed)
    for record in records:
        before = auto.get(record['pk'])
        if before not in (None, 'unknown') and before != record['_spectrograph']:
            record['hard'] = True
        del record['_spectrograph']
    return records


def _group(record):
    """Split group: the observation run, or the file itself if it has none."""
    return record['run'] if record['run'] is not None else f"file-{record['pk']}"


def cap_per_class(records, max_per_class, rng):
    """Keep at most ``max_per_class`` files per class: all hard files, the rest round-robin over runs."""
    by_class = defaultdict(list)
    for record in records:
        by_class[record['class']].append(record)
    kept = []
    for items in by_class.values():
        hard = [r for r in items if r['hard']]
        rest = [r for r in items if not r['hard']]
        quota = max(0, max_per_class - len(hard))
        if len(rest) > quota:
            by_run = defaultdict(list)
            for record in rest:
                by_run[_group(record)].append(record)
            runs = list(by_run.values())
            rng.shuffle(runs)
            for run in runs:
                rng.shuffle(run)
            interleaved = [r for batch in zip_longest(*runs) for r in batch if r is not None]
            rest = interleaved[:quota]
        kept.extend(hard + rest)
    return kept


def split_by_run(records, ratios, rng):
    """
    Assign ``split`` per run: runs with rare classes first, each run to the split that is furthest
    below its target share for the classes the run contains.
    """
    ratios = dict(zip(SPLITS, ratios))
    if min(ratios.values()) <= 0:
        raise ValueError('All split ratios must be positive')
    run_counts = defaultdict(Counter)
    for record in records:
        run_counts[_group(record)][record['class']] += 1
    totals = Counter(record['class'] for record in records)

    runs = list(run_counts)
    rng.shuffle(runs)
    runs.sort(key=lambda run: min(totals[c] for c in run_counts[run]))
    assigned = {split: Counter() for split in SPLITS}
    run_split = {}
    for run in runs:
        counts = run_counts[run]

        def need(split):
            # Unmet share of the split's target, relative to the target (rare classes reach every split)
            return sum(
                n * (1 - assigned[split][c] / (ratios[split] * totals[c]))
                for c, n in counts.items()
            )

        best = max(SPLITS, key=lambda split: (need(split), ratios[split]))
        run_split[run] = best
        assigned[best].update(counts)

    for record in records:
        record['split'] = run_split[_group(record)]
    return records


def build_export(formats, data_directory, ratios, max_per_class, rng, min_year=None):
    """Complete v2 export document."""
    records = collect_records(formats, data_directory, min_year=min_year)
    labelled = len(records)
    records = cap_per_class(records, max_per_class, rng)
    records = split_by_run(records, ratios, rng)
    records.sort(key=lambda r: (SPLITS.index(r['split']), r['class'], r['path']))

    counts = {split: Counter() for split in SPLITS}
    hard = {split: Counter() for split in SPLITS}
    for record in records:
        counts[record['split']][record['class']] += 1
        hard[record['split']][record['class']] += record['hard']
    return {
        'format': FORMAT,
        'params': {
            'formats': formats, 'min_year': min_year, 'max_per_class': max_per_class,
            'split': dict(zip(SPLITS, ratios)), 'data_directory': str(data_directory),
        },
        'labelled_files': labelled,
        'counts': {split: dict(c) for split, c in counts.items()},
        'hard_counts': {split: {k: v for k, v in c.items() if v} for split, c in hard.items()},
        'runs': {split: len({_group(r) for r in records if r['split'] == split}) for split in SPLITS},
        'files': records,
    }
