"""
Complete the padding of the last FITS block. The FITS standard requires files of whole 2880-byte
blocks; some camera software ends the file right after the last data byte. The data are complete,
but astropy warns "File may have been truncated" on every open (also in users' scripts after a
download), and strict tools may refuse to append HDUs.

The missing bytes (zeros; spaces for ASCII tables) are appended to a temporary copy, which is checked
and then renamed over the file: the data directory watchdog ignores the .filepart file and the rename,
so the file is not re-evaluated. The modification time is kept. Only files flagged by the file
integrity check (obs_run.file_check) are candidates.
"""
from __future__ import annotations

import logging
import os
import shutil
import warnings
from pathlib import Path

from obs_run.file_check import update_file_issues

logger = logging.getLogger(__name__)

BLOCK = 2880
# Temporary files end in an ignored suffix of the directory watchdog (WATCH_IGNORED_SUFFIXES)
_TMP_SUFFIX = '.padding.filepart'
# Warning of obs_run.file_check._check_fits for complete data without the final padding
UNPADDED_MARKER = 'Last FITS block not padded'


def missing_padding(path):
    """
    (missing bytes, padding byte) to complete the last block; (0, b'') if the file is padded or does
    not just lack the padding (truncated data, other trailing bytes, unreadable).
    """
    from astropy.io import fits

    size = os.path.getsize(path)
    if size % BLOCK == 0:
        return 0, b''
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with fits.open(path, memmap=False, lazy_load_hdus=False, ignore_missing_simple=True) as hdul:
                # The HDU whose data end last (data size without padding)
                last = max(
                    (hdu for hdu in hdul if getattr(hdu, '_data_offset', None) is not None),
                    key=lambda hdu: hdu._data_offset + hdu.size,
                    default=None,
                )
                if last is None:
                    return 0, b''
                data_end = last._data_offset + last.size
                pad = b' ' if isinstance(last, fits.TableHDU) else b'\0'
    except Exception:
        logger.warning('Cannot read FITS structure of %s', path, exc_info=True)
        return 0, b''
    padded_end = -(-data_end // BLOCK) * BLOCK
    if not data_end <= size < padded_end:
        return 0, b''
    return padded_end - size, pad


def pad_file(path, missing, pad):
    """Append `missing` padding bytes via a checked temporary copy and an atomic rename."""
    path = Path(path)
    tmp = path.with_name(f'.{path.name}{_TMP_SUFFIX}')
    try:
        with open(path, 'rb') as src, open(tmp, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
            dst.write(pad * missing)
            dst.flush()
            os.fsync(dst.fileno())
        if tmp.stat().st_size % BLOCK or missing_padding(tmp)[0]:
            raise ValueError('padded copy is not block-aligned')
        shutil.copystat(path, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def unpadded_datafiles():
    """Data files whose last integrity check reported the missing final padding."""
    from obs_run.models import DataFile

    candidates = DataFile.objects.filter(file_issue_level__in=('warning', 'error')).order_by('pk')
    return [
        datafile for datafile in candidates.iterator(chunk_size=500)
        if any(UNPADDED_MARKER in (issue.get('message') or '') for issue in datafile.file_issues or [])
    ]


def fix_fits_padding(dry_run=False, limit=None):
    """
    Pad the flagged files; returns one result per file: {'pk', 'path', 'missing', 'status'} with status
    'padded', 'would pad' (dry run), 'skipped' (no longer just unpadded) or 'failed: <reason>'.
    Size and hash are stored without history entries, then the file is checked again.
    """
    from obs_run.models import DataFile
    from utilities import compute_file_hash

    results = []
    for datafile in unpadded_datafiles()[:limit]:
        path = Path(str(datafile.datafile))
        result = {'pk': datafile.pk, 'path': str(path), 'missing': 0}
        results.append(result)
        if not path.is_file():
            result['status'] = 'failed: file missing on disk'
            continue
        missing, pad = missing_padding(path)
        result['missing'] = missing
        if not missing:
            result['status'] = 'skipped'
        elif dry_run:
            result['status'] = 'would pad'
        else:
            try:
                pad_file(path, missing, pad)
            except Exception as exc:
                logger.warning('Padding failed for %s', path, exc_info=True)
                result['status'] = f'failed: {exc}'
                continue
            DataFile.objects.filter(pk=datafile.pk).update(
                file_size=path.stat().st_size, content_hash=compute_file_hash(path),
            )
            result['status'] = 'padded'
            logger.info('Padded last FITS block of %s (%d bytes)', path, missing)
        if dry_run:
            continue
        # Current state in the integrity list (also for skipped files whose warning is outdated)
        update_file_issues(datafile)
    return results
