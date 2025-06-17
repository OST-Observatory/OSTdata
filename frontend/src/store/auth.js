import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token'))

  const isAuthenticated = computed(() => !!token.value)
  const username = computed(() => user.value?.username)

  async function login(credentials) {
    try {
      const response = await fetch('/api/auth/login/', {
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
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  }

  async function logout() {
    try {
      await fetch('/api/auth/logout/', {
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
      const response = await fetch('/api/auth/user/', {
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
    login,
    logout,
    checkAuth,
  }
}) 