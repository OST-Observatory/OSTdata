/**
 * Read Django CSRF cookie set by GET /api/users/auth/csrf/.
 */
export function getCsrfToken() {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : null
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
