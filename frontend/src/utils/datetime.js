const getLocales = () => (typeof navigator !== 'undefined' && navigator.languages && navigator.languages.length)
  ? navigator.languages
  : (typeof navigator !== 'undefined' ? [navigator.language] : undefined)

const getTimeZone = () => import.meta.env.VITE_TIME_ZONE || undefined

export function formatDateTime(value, options = { dateStyle: 'short', timeStyle: 'medium' }) {
  if (!value) return 'N/A'
  const d = value instanceof Date ? value : new Date(value)
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

