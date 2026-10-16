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
