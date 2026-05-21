const getLocales = () => (typeof navigator !== 'undefined' && navigator.languages && navigator.languages.length)
  ? navigator.languages
  : (typeof navigator !== 'undefined' ? [navigator.language] : undefined)

const getTimeZone = () => import.meta.env.VITE_TIME_ZONE || undefined

/**
 * Parse API datetimes (ISO-8601). Naive strings are treated as UTC (Django USE_TZ).
 */
export function parseApiDateTime(value) {
  if (value == null || value === '') return null
  if (value instanceof Date) return value
  const s = String(value).trim()
  if (!s) return null
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) {
    return new Date(`${s}Z`)
  }
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Relative time for admin lists; returns "Never" when empty. */
export function formatRelativeFromNow(value) {
  const d = parseApiDateTime(value)
  if (!d) return 'Never'
  const diff = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
  if (diff < 60) return `${diff}s ago`
  const m = Math.floor(diff / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const days = Math.floor(h / 24)
  if (days < 14) return `${days}d ago`
  return formatDateTime(d)
}

export function formatDateTime(value, options = { dateStyle: 'short', timeStyle: 'medium' }) {
  if (!value) return 'N/A'
  const d = parseApiDateTime(value) ?? (value instanceof Date ? value : new Date(value))
  try {
    return new Intl.DateTimeFormat(getLocales(), { ...options, timeZone: getTimeZone() }).format(d)
  } catch (e) {
    return d.toLocaleString()
  }
}

export function formatDateOnly(value, options = { dateStyle: 'short' }) {
  return formatDateTime(value, options)
}

export function formatTimeOnly(value, options = { timeStyle: 'medium' }) {
  return formatDateTime(value, options)
}

export function sameLocalDay(a, b) {
  if (!a || !b) return false
  const tz = getTimeZone()
  const da = new Date(a)
  const db = new Date(b)
  // Compare formatted date parts for given timezone
  const fmt = new Intl.DateTimeFormat(getLocales(), { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: tz })
  return fmt.format(da) === fmt.format(db)
}

/**
 * Convert Julian Date (JD) to JavaScript Date object
 * @param {number} jd - Julian Date (e.g., 2459254.48)
 * @returns {Date|null} - Date object or null if JD is invalid
 */
export function jdToDate(jd) {
  if (!jd || typeof jd !== 'number' || jd <= 0 || jd < 2440587.5) {
    return null
  }
  // JD to milliseconds: (JD - 2440587.5) * 86400000
  // 2440587.5 is the JD for 1970-01-01 00:00:00 UTC
  const milliseconds = (jd - 2440587.5) * 86400000
  return new Date(milliseconds)
}
