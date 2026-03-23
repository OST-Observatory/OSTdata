/**
 * Central timeouts and copy for async ZIP download jobs (Celery).
 * Prefer values from GET /api/ui-config/ (Django settings / .env); fall back to constants below if the request fails.
 */

const FALLBACK_DOWNLOAD_JOB_POLL_INTERVAL_MS = 2000
const FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS = 45 * 60 * 1000 // 45 minutes

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
        const max = _parsePositiveMs(data.download_job_max_wait_ms, FALLBACK_DOWNLOAD_JOB_MAX_WAIT_MS)
        _cachedConfig = {
          pollIntervalMs: Math.min(Math.max(poll, 500), 120_000),
          maxWaitMs: Math.min(Math.max(max, 10_000), 48 * 60 * 60 * 1000),
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
  const waitMinutes = Math.round(getDownloadJobMaxWaitMs() / 60000)
  lines.push(
    `Preparing the archive can take a long time for large sets. This page waits up to about ${waitMinutes} minutes; keep the tab open until the download starts. If it takes longer, check Admin → Jobs — the job may still be running.`
  )
  return lines.join(' ')
}
