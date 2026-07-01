import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import router from '@/router'
import { ADMIN_NAV_PERMS } from '@/constants/acl'
import { csrfHeaders, refreshCsrfToken, clearCsrfToken } from '@/utils/csrf'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const API_BASE_URL = import.meta.env?.VITE_API_BASE || '/api'

  const isAuthenticated = computed(() => !!user.value)
  const username = computed(() => user.value?.username)
  const isSuperuser = computed(() => !!user.value?.is_superuser)
  /** @deprecated Use hasPerm / canAccessAdmin; staff no longer implies extra rights. */
  const isAdmin = computed(() => isSuperuser.value)
  const perms = computed(() => Array.isArray(user.value?.perms) ? user.value.perms : [])
  const hasPerm = (code) => {
    try {
      if (user.value?.is_superuser) return true
      const p = Array.isArray(user.value?.perms) ? user.value.perms : []
      // Accept both 'users.acl_x' and plain 'acl_x'
      return p.includes(code) || p.includes(code.startsWith('users.') ? code : `users.${code}`)
    } catch { return false }
  }
  const hasAnyPerm = (codes) => {
    try {
      if (user.value?.is_superuser) return true
      const list = Array.isArray(codes) ? codes : []
      return list.some((code) => hasPerm(code))
    } catch { return false }
  }
  const canAccessAdmin = computed(() => hasAnyPerm(ADMIN_NAV_PERMS))

  function _clearLegacyToken() {
    try {
      localStorage.removeItem('token')
    } catch { /* ignore */ }
  }

  async function login(credentials) {
    try {
      _clearLegacyToken()
      clearCsrfToken()
      await refreshCsrfToken()

      const response = await fetch(`${API_BASE_URL}/users/auth/login/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...csrfHeaders(),
        },
        credentials: 'include',
        body: JSON.stringify(credentials),
      })

      if (!response.ok) {
        throw new Error('Login failed')
      }

      const data = await response.json()
      user.value = data.user
      // Login rotates the session; CSRF must match the new session.
      await refreshCsrfToken()

      const next = router.currentRoute.value.query?.next
      if (typeof next === 'string' && next) {
        router.replace(next)
      }
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  }

  async function logout() {
    try {
      await refreshCsrfToken()
      await fetch(`${API_BASE_URL}/users/auth/logout/`, {
        method: 'POST',
        headers: {
          ...csrfHeaders(),
        },
        credentials: 'include',
      })
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      user.value = null
      _clearLegacyToken()
      clearCsrfToken()
    }
  }

  async function checkAuth() {
    _clearLegacyToken()

    try {
      const response = await fetch(`${API_BASE_URL}/users/auth/user/`, {
        credentials: 'include',
      })
      const data = await response.json().catch(() => null)

      if (response.ok && data?.username) {
        user.value = data
        await refreshCsrfToken()
        return true
      }

      user.value = null
      clearCsrfToken()
      return false
    } catch {
      user.value = null
      clearCsrfToken()
      return false
    }
  }

  async function changePassword(payload) {
    await refreshCsrfToken()
    const response = await fetch(`${API_BASE_URL}/users/auth/change-password/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
      credentials: 'include',
      body: JSON.stringify(payload),
    })

    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const err = new Error(data.error || 'Failed to change password')
      err.data = data
      throw err
    }

    user.value = null
    _clearLegacyToken()
    clearCsrfToken()
    return data
  }

  return {
    user,
    isAuthenticated,
    username,
    isAdmin,
    isSuperuser,
    perms,
    hasPerm,
    hasAnyPerm,
    canAccessAdmin,
    login,
    logout,
    checkAuth,
    changePassword,
  }
})
