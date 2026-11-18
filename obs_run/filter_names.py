"""
Canonical filter names for DataFile.filter_normalized.

``DataFile.image_filter`` keeps the FILTER keyword as written; ``filter_normalized`` maps the spellings found in
the archive to one name per physical filter. Names follow the FITS header specification of OST_OCS where it
defines them (``U B V R I``, ``Ha OIII SII``, ``SLOAN-u ... SLOAN-y``, ``Clear``).

Decisions (2026-11-18, from the spellings in the archive):

- ``R``/``B`` are Bessell filters; the RGB set is written as ``Red``/``Green``/``Blue`` and stays separate.
- ``Clear`` is plain glass, not the same as the UV/IR cut filter (``UV/IR``, ``BlockUV/IR``).
- ``UV Block`` is a separate filter.
- ``g'`` is Sloan g'.

Spellings are compared case-insensitively and without spaces, ``-`` and ``_`` (``H alpha`` = ``h-ALPHA``); the
prime of Sloan names may be written as ``'``, ``’`` or ``′``. Names that only give a wheel position (``Slot 8``,
``Filter#1``) map to ''. Unknown names are kept as written, so nothing is lost and new spellings show up for
review. Caveat: a lower-case ``r`` counts as Bessell R; Sloan filters need the prime or the ``SLOAN-`` prefix.
"""
import re

FILTER_ALIASES = {
    # Bessell / Johnson-Cousins
    'U': 'U',
    'B': 'B',
    'V': 'V',
    'R': 'R',
    'I': 'I',
    # Narrow band
    'Ha': 'Ha',
    'H alpha': 'Ha',
    'Halpha': 'Ha',
    'H-Alpha': 'Ha',
    'H_alpha': 'Ha',
    'H-a': 'Ha',
    'Hb': 'Hb',
    'H-Beta': 'Hb',
    'Hbeta': 'Hb',
    'OIII': 'OIII',
    'O III': 'OIII',
    'SII': 'SII',
    'S II': 'SII',
    # Sloan
    "u'": 'SLOAN-u',
    "g'": 'SLOAN-g',
    "r'": 'SLOAN-r',
    "i'": 'SLOAN-i',
    "z'": 'SLOAN-z',
    'SLOAN-u': 'SLOAN-u',
    'SLOAN-g': 'SLOAN-g',
    'SLOAN-r': 'SLOAN-r',
    'SLOAN-i': 'SLOAN-i',
    'SLOAN-z': 'SLOAN-z',
    'SLOAN-zs': 'SLOAN-zs',
    'SLOAN-y': 'SLOAN-y',
    # RGB set and luminance
    'Red': 'Red',
    'Green': 'Green',
    'Blue': 'Blue',
    'Luminance': 'Luminance',
    'Lum': 'Luminance',
    # Others
    'Clear': 'Clear',
    'UV/IR': 'UV/IR-Cut',
    'BlockUV/IR': 'UV/IR-Cut',
    'UV/IR-Cut': 'UV/IR-Cut',
    'UV/IR Cut': 'UV/IR-Cut',
    'UV Block': 'UV-Block',
    'UV-Block': 'UV-Block',
    'LPR': 'LPR',
}

# Names that only give a wheel position, e.g. 'Slot 8', 'Filter#1', 'Pos 3'
POSITION_ONLY = re.compile(r'^(slot|filter|pos|position)\s*#?\s*\d+$', re.IGNORECASE)


def _key(name):
    """Comparison key: lower case without spaces, '-', '_' and quote variants (g' = g’ = g′)."""
    name = str(name).lower().replace('’', "'").replace('′', "'")
    return ''.join(ch for ch in name if ch not in ' -_')


# Case-insensitive keys: no two aliases with different names differ only by case (checked in the tests)
_ALIASES = {_key(alias): name for alias, name in FILTER_ALIASES.items()}


def normalize_filter(name) -> str:
    """Canonical filter name for a stored FILTER value ('' for empty values and wheel positions)."""
    raw = str(name or '').strip()
    if not raw or POSITION_ONLY.match(raw):
        return ''
    return _ALIASES.get(_key(raw), raw)[:50]
