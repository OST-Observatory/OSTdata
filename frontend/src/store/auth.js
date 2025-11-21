import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token'))
  const API_BASE_URL = import.meta.env?.VITE_API_BASE || '/api'

  const isAuthenticated = computed(() => !!token.value)
  const username = computed(() => user.value?.username)
  const isAdmin = computed(() => {
    const u = user.value
    return !!(u && (u.is_staff || u.is_superuser))
  })

  async function login(credentials) {
    try {
      const response = await fetch(`${API_BASE_URL}/users/auth/login/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      })

      if (!response.ok) {
        throw new Error('Login failed')
      }

      const data = await response.json()
      token.value = data.token
      user.value = data.user
      localStorage.setItem('token', data.token)

      // Navigate back to intended page if present
      const next = router.currentRoute.value.query?.next
      if (typeof next === 'string' && next) {
        router.replace(next)
      } else {
        // stay on current route; optionally redirect to dashboard
      }
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  }

  async function logout() {
    try {
      await fetch(`${API_BASE_URL}/users/auth/logout/`, {
        method: 'POST',
        headers: {
          'Authorization': `Token ${token.value}`,
        },
      })
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
    }
  }

  async function checkAuth() {
    if (!token.value) return false

    try {
      const response = await fetch(`${API_BASE_URL}/users/auth/user/`, {
        headers: {
          'Authorization': `Token ${token.value}`,
        },
      })

      if (!response.ok) {
        throw new Error('Auth check failed')
      }

      user.value = await response.json()
      return true
    } catch (error) {
      console.error('Auth check error:', error)
      token.value = null
      user.value = null
      localStorage.removeItem('token')
      return false
    }
  }

  return {
    user,
    token,
    isAuthenticated,
    username,
    isAdmin,
    login,
    logout,
    checkAuth,
  }
}) 