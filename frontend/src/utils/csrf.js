/**
 * Django CSRF for session-authenticated SPA requests.
 * Prefer csrfToken from GET /api/users/auth/csrf/ (avoids stale/duplicate cookies under URL prefixes).
 */

const API_BASE_URL = import.meta.env?.VITE_API_BASE || '/api'

let csrfTokenMemory = null

function readCsrfFromCookie() {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : null
}

export function getCsrfToken() {
  return csrfTokenMemory || readCsrfFromCookie()
}

export function clearCsrfToken() {
  csrfTokenMemory = null
}

/** Fetch a fresh CSRF token from Django (also sets csrftoken cookie). */
export async function refreshCsrfToken() {
  const res = await fetch(`${API_BASE_URL}/users/auth/csrf/`, { credentials: 'include' })
  if (!res.ok) {
    throw new Error(`CSRF refresh failed: ${res.status}`)
  }
  const data = await res.json().catch(() => ({}))
  // Cookie after Set-Cookie is what the browser sends on the next POST.
  csrfTokenMemory = readCsrfFromCookie() || data?.csrfToken || null
  return csrfTokenMemory
}

/** Headers for unsafe HTTP methods (POST, PUT, PATCH, DELETE). */
export function csrfHeaders() {
  const token = getCsrfToken()
  return token ? { 'X-CSRFToken': token } : {}
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function withCsrfIfNeeded(method, headers = {}) {
  if (UNSAFE_METHODS.has((method || 'GET').toUpperCase())) {
    return { ...headers, ...csrfHeaders() }
  }
  return headers
}

export function isUnsafeMethod(method) {
  return UNSAFE_METHODS.has((method || 'GET').toUpperCase())
}
