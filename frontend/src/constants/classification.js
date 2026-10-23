// Exposure type and spectrograph codes of DataFile (obs_run/models.py) with labels and colors

export const EXPOSURE_TYPE_ITEMS = [
  { label: 'Bias', value: 'BI' },
  { label: 'Dark', value: 'DA' },
  { label: 'Flat', value: 'FL' },
  { label: 'Light', value: 'LI' },
  { label: 'Wave', value: 'WA' },
  { label: 'Unknown', value: 'UK' },
]

export const SPECTROGRAPH_ITEMS = [
  { label: 'DADOS', value: 'D' },
  { label: 'BACHES', value: 'B' },
  { label: 'Einsteinturm', value: 'E' },
  { label: 'None', value: 'N' },
]

// Image quality flags (obs_run/image_quality.py); BAD ones are excluded from plate solving, dark finder,
// spectrograph heuristics and training data
export const QUALITY_FLAG_ITEMS = [
  { label: 'OK', value: 'OK' },
  { label: 'Over-exposed', value: 'OE' },
  { label: 'Empty / constant', value: 'EM' },
  { label: 'Unreadable', value: 'UR' },
  { label: 'Not checked', value: 'NC' },
]
export const BAD_QUALITY_FLAGS = ['OE', 'EM', 'UR']

export function qualityFlagLabel(code) {
  return (QUALITY_FLAG_ITEMS.find(i => i.value === code) || {}).label || code
}

const EXPOSURE_TYPE_COLORS = { BI: 'blue', DA: 'grey-darken-2', FL: 'green', LI: 'orange', WA: 'purple', UK: 'grey' }
const SPECTROGRAPH_COLORS = { D: 'blue', B: 'green', E: 'purple', N: 'grey' }

export function exposureTypeColor(code) {
  return EXPOSURE_TYPE_COLORS[code] || 'grey'
}

export function exposureTypeLabel(code) {
  return (EXPOSURE_TYPE_ITEMS.find(i => i.value === code) || {}).label || code || '—'
}

export function spectrographColor(code) {
  return SPECTROGRAPH_COLORS[code] || 'grey'
}

export function spectrographLabel(code) {
  return (SPECTROGRAPH_ITEMS.find(i => i.value === code) || {}).label || code || '—'
}

// Cameras (canonical names of obs_run/utils.py INSTRUMENT_CATALOG); colors differ from the spectrograph
// colors so photometry and spectroscopy chips stay distinguishable
const CAMERA_COLORS = {
  'QHY 600M': 'teal',
  'QHY 268M': 'indigo',
  'QHY 5III485C': 'pink',
  'QHY 5III462C': 'pink-darken-2',
  'SBIG ST-8': 'brown',
  'SBIG ST-7': 'brown-lighten-1',
  'SBIG STF-8300': 'deep-orange',
  'SBIG ST-i': 'blue-grey',
  'Skyris 445C': 'lime-darken-2',
  'ZWO ASI174MM': 'cyan-darken-2',
  'ZWO ASI174MM Mini': 'cyan-darken-2',
  'ZWO ASI220MM': 'cyan',
  'ZWO ASI678MM': 'light-blue-darken-2',
  'ZWO ASI2600MC Pro': 'amber-darken-3',
  'ZWO ASI294MM Pro': 'orange-darken-3',
}
const CAMERA_FALLBACK_COLORS = ['teal-darken-2', 'indigo-lighten-1', 'deep-orange-darken-2', 'blue-grey-darken-1', 'pink-lighten-1']

export function cameraColor(name) {
  if (CAMERA_COLORS[name]) return CAMERA_COLORS[name]
  // Stable color for cameras not in the list
  let hash = 0
  for (const ch of String(name || '')) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return CAMERA_FALLBACK_COLORS[hash % CAMERA_FALLBACK_COLORS.length]
}

/**
 * Open heuristic spectrograph suggestion of a data file row (serializer field spectrograph_suggestion):
 * { byRun, byToken, values } with only the values that still differ from the current spectrograph.
 * Files with a manually set spectrograph have no open suggestion.
 */
export function openSpectrographSuggestion(item) {
  const s = item?.spectrograph_suggestion
  if (!s || item.spectrograph_override) return null
  const current = item.spectrograph || 'N'
  const byRun = s.run_majority && s.run_majority !== current ? s.run_majority : null
  const byToken = s.path_token && s.path_token !== current ? s.path_token : null
  if (!byRun && !byToken) return null
  const values = [...new Set([byRun, byToken].filter(Boolean))]
  return { byRun, byToken, values, agree: !!byRun && byRun === byToken }
}
