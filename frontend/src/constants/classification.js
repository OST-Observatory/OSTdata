// Exposure type and spectrograph codes of DataFile (obs_run/models.py) with labels and colors

export const EXPOSURE_TYPE_ITEMS = [
  { label: 'Bias', value: 'BI' },
  { label: 'Dark', value: 'DA' },
  { label: 'Flat', value: 'FL' },
  { label: 'Light', value: 'LI' },
  { label: 'Arc Frame', value: 'WA' },
  { label: 'Unknown', value: 'UK' },
]

export const SPECTROGRAPH_ITEMS = [
  { label: 'DADOS', value: 'D' },
  { label: 'BACHES', value: 'B' },
  { label: 'Einsteinturm', value: 'E' },
  { label: 'UVEX', value: 'U' },
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

// Categorical theme colors (plugins/vuetify.ts): readable in both themes
const EXPOSURE_TYPE_COLORS = { BI: 'cat-blue', DA: 'cat-slate', FL: 'cat-green', LI: 'cat-orange', WA: 'cat-purple', UK: 'cat-gray' }
const SPECTROGRAPH_COLORS = { D: 'cat-blue', B: 'cat-green', E: 'cat-purple', U: 'cat-olive', N: 'cat-gray' }

export function exposureTypeColor(code) {
  return EXPOSURE_TYPE_COLORS[String(code || '').toUpperCase()] || 'cat-gray'
}

export function exposureTypeLabel(code) {
  return (EXPOSURE_TYPE_ITEMS.find(i => i.value === code) || {}).label || code || '—'
}

export function spectrographColor(code) {
  return SPECTROGRAPH_COLORS[code] || 'cat-gray'
}

export function spectrographLabel(code) {
  return (SPECTROGRAPH_ITEMS.find(i => i.value === code) || {}).label || code || '—'
}

// Cameras (canonical names of obs_run/utils.py INSTRUMENT_CATALOG); colors differ from the spectrograph
// colors so photometry and spectroscopy chips stay distinguishable (the chip text names the camera)
const CAMERA_COLORS = {
  'QHY 600M': 'cat-teal',
  'QHY 268M': 'cat-indigo',
  'QHY 5III485C': 'cat-pink',
  'QHY 5III462C': 'cat-pink',
  'SBIG ST-8': 'cat-brown',
  'SBIG ST-7': 'cat-brown',
  'SBIG STF-8300': 'cat-orange',
  'SBIG ST-i': 'cat-slate',
  'Skyris 445C': 'cat-olive',
  'ZWO ASI174MM': 'cat-cyan',
  'ZWO ASI174MM Mini': 'cat-cyan',
  'ZWO ASI220MM': 'cat-cyan',
  'ZWO ASI678MM': 'cat-cyan',
  'ZWO ASI2600MC Pro': 'cat-orange',
  'ZWO ASI294MM Pro': 'cat-orange',
}
const CAMERA_FALLBACK_COLORS = ['cat-teal', 'cat-indigo', 'cat-orange', 'cat-slate', 'cat-pink']

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
