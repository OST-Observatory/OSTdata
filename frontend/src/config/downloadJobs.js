/**
 * Central timeouts and copy for async ZIP download jobs (Celery).
 * Prefer values from GET /api/ui-config/ (Django settings / .env); fall back to constants below if the request fails.
 */

const FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS = 2000
const FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS = 45 * 60 * 1000 // 45 minutes
/** Ignore absurdly small server values (e.g. minutes/seconds mistaken for ms). */
const MIN_CLIENT_MAX_WAIT_MS = 5 * 60 * 1000 // 5 minutes
const MAX_CLIENT_MAX_WAIT_MS = 48 * 60 * 60 * 1000 // 48 hours

/** Same defaults as Django when /api/ui-config/ is unavailable */
export const DOWNLOAD_JOB_POLL_INTERVAL_MS = FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS

export const DOWNLOAD_JOB_MAX_WAIT_MS = FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS

let _cachedConfig = null
let _configPromise = null

function _parsePositiveMs(value, fallback) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return fallback
  return Math.round(n)
}

/**
 * Load poll/max limits from the API once (cached). Safe to call multiple times in parallel.
 * @returns {Promise<{ pollIntervalMs: number, maxWaitMs: number }>}
 */
export async function ensureDownloadJobConfig() {
  if (_cachedConfig) return _cachedConfig
  if (!_configPromise) {
    _configPromise = (async () => {
      try {
        const base = (import.meta.env?.VITE_API_BASE || '/api').replace(/\/$/, '')
        const res = await fetch(`${base}/ui-config/`, { credentials: 'include' })
        if (!res.ok) throw new Error('ui-config not ok')
        const data = await res.json()
        const poll = _parsePositiveMs(data.download_job_poll_interval_ms, FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS)
        let max = _parsePositiveMs(data.download_job_max_wait_ms, FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS)
        // Values below 5 minutes are almost always a unit mistake in .env (seconds/minutes
        // instead of ms). Fall back to the documented default rather than timing out quickly.
        if (max < MIN_CLIENT_MAX_WAIT_MS) {
          max = FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS
        }
        _cachedConfig = {
          pollIntervalMs: Math.min(Math.max(poll, 500), 120_000),
          maxWaitMs: Math.min(max, MAX_CLIENT_MAX_WAIT_MS),
        }
      } catch {
        _cachedConfig = {
          pollIntervalMs: FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS,
          maxWaitMs: FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS,
        }
      }
      return _cachedConfig
    })().finally(() => {
      _configPromise = null
    })
  }
  return _configPromise
}

export function getDownloadJobPollIntervalMs() {
  return _cachedConfig?.pollIntervalMs ?? FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS
}

export function getDownloadJobMaxWaitMs() {
  return _cachedConfig?.maxWaitMs ?? FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS
}

/** Whole minutes for user-facing copy (never show "0 minutes"). */
export function formatDownloadJobWaitMinutes(maxWaitMs = getDownloadJobMaxWaitMs()) {
  const ms = Number(maxWaitMs)
  if (!Number.isFinite(ms) || ms <= 0) {
    return Math.ceil(FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS / 60000)
  }
  return Math.max(1, Math.ceil(ms / 60000))
}

export function sumFileSizes(items) {
  if (!Array.isArray(items)) return 0
  return items.reduce((sum, f) => sum + (Number(f?.file_size) || 0), 0)
}

export function formatBytes(bytes) {
  if (bytes == null || !Number.isFinite(Number(bytes)) || Number(bytes) <= 0) return null
  const n = Number(bytes)
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  const rounded = v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)
  return `${rounded} ${units[i]}`
}

/**
 * User-facing message before starting an async download job.
 * Loads /api/ui-config/ first so the “wait up to X minutes” line matches server settings.
 * @param {object} opts
 * @param {number} [opts.fileCount]
 * @param {Array<{ file_size?: number }>} [opts.items] — rows that include optional file_size from API
 * @param {boolean} [opts.sizeIsPartial] — true if items do not cover the full selection (e.g. paginated table)
 */
export async function buildDownloadPrepMessage({ fileCount, items = [], sizeIsPartial = false } = {}) {
  await ensureDownloadJobConfig()
  const lines = []
  if (typeof fileCount === 'number' && fileCount > 0) {
    lines.push(`Download: ${fileCount} file${fileCount === 1 ? '' : 's'}.`)
  }
  const sum = sumFileSizes(items)
  if (sum > 0) {
    const approx = formatBytes(sum)
    if (sizeIsPartial) {
      lines.push(
        `Approximate size from the files currently loaded in the table: ~${approx}. The full selection may be larger.`
      )
    } else {
      lines.push(`Approximate raw data size (sum of file sizes): ~${approx}. The ZIP size may differ.`)
    }
  } else if (typeof fileCount === 'number' && fileCount > 0) {
    lines.push('Exact total size will be known when the archive is ready.')
  }
  const waitMinutes = formatDownloadJobWaitMinutes()
  lines.push(
    `Preparing the archive can take a while for large sets. Please keep this tab open; the download should start automatically within about ${waitMinutes} minute${waitMinutes === 1 ? '' : 's'}. ` +
      `If nothing starts by then, wait a bit longer and try again, as the archive may still be building on the server. ` +
      `If the problem continues, contact the site administrator.`
  )
  return lines.join(' ')
}

export function buildDownloadTimeoutMessage() {
  const waitMinutes = formatDownloadJobWaitMinutes()
  return (
    `This page stopped waiting after about ${waitMinutes} minute${waitMinutes === 1 ? '' : 's'}, ` +
    `but the archive may still be preparing on the server. Please wait a few minutes and try the download again. ` +
    `If it keeps failing, contact the site administrator.`
  )
}
