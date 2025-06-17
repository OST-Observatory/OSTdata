import { useAuthStore } from '@/store/auth'

const API_BASE_URL = '/api'

async function fetchWithAuth(url, options = {}) {
  const authStore = useAuthStore()
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }

  if (authStore.token) {
    headers['Authorization'] = `Token ${authStore.token}`
  }

  // Handle query parameters
  let fullUrl = `${API_BASE_URL}${url}`
  if (options.params) {
    const searchParams = new URLSearchParams()
    Object.entries(options.params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        // Convert page_size to limit for Django REST Framework
        if (key === 'page_size') {
          searchParams.append('limit', value)
        } else {
          searchParams.append(key, value)
        }
      }
    })
    const queryString = searchParams.toString()
    if (queryString) {
      fullUrl += `?${queryString}`
    }
  }

  const response = await fetch(fullUrl, {
    ...options,
    headers
  })

  if (!response.ok) {
    const error = new Error(`API error: ${response.status}`)
    error.status = response.status
    try {
      const data = await response.json()
      error.data = data
    } catch (e) {
      // Handle non-JSON response silently
    }
    throw error
  }

  return await response.json()
}

export const api = {
  // Dashboard Stats (aggregiert aus verschiedenen Endpunkten)
  getDashboardStats: async () => {
    const response = await fetchWithAuth('/runs/dashboard/stats/')
    return response
  },

  // Observation Runs
  getRecentRuns: () => fetchWithAuth('/runs/runs/?limit=10'),
  getObservationRun: (id) => fetchWithAuth(`/runs/runs/${id}/`),
  getObservationRuns: (params) => fetchWithAuth('/runs/runs/', { params }),
  getAllObservationRuns: () => fetchWithAuth('/runs/runs/?limit=1000'),  // Get all runs for filtering

  // Objects
  getObjects: (params) => {
    // Ensure pagination parameters are properly formatted
    const queryParams = {
      ...params,
      page: params.page || 1
    }

    // Handle limit parameter
    if (params.limit !== undefined) {
      queryParams.limit = params.limit
    }

    // Handle search parameter
    if (params.search) {
      queryParams.name = params.search
    }

    // Handle type filter
    if (params.object_type) {
      queryParams.object_type = params.object_type
    }

    // Handle ordering
    if (params.ordering) {
      queryParams.ordering = params.ordering
    }

    return fetchWithAuth('/objects/', { params: queryParams })
  },
  getObjectsVuetify: (params) => {
    const queryParams = {
      page: params.page || 1,
      limit: params.itemsPerPage === -1 ? 10000 : (params.itemsPerPage || 10),
      sortBy: params.sortBy ? (params.sortBy.startsWith('-') ? params.sortBy.substring(1) : params.sortBy) : 'name',
      sortDesc: params.sortBy ? params.sortBy.startsWith('-') : false,
      search: params.search || '',
      object_type: params.object_type || '',
      observation_run: params.observation_run || ''
    }
    // Add coordinate filter if present
    if (params.ra !== undefined) queryParams.ra = params.ra
    if (params.dec !== undefined) queryParams.dec = params.dec
    if (params.radius !== undefined) queryParams.radius = params.radius
    return fetchWithAuth('/objects/vuetify', { params: queryParams })
  },
  getObject: (id) => fetchWithAuth(`/objects/${id}/`),
  getRecentObjects: () => fetchWithAuth('/objects/?limit=10&ordering=-created_at'),
  createObject: (data) => fetchWithAuth('/objects/', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  updateObject: (id, data) => fetchWithAuth(`/objects/${id}/`, {
    method: 'PUT',
    body: JSON.stringify(data)
  }),
  deleteObject: (id) => fetchWithAuth(`/objects/${id}/`, {
    method: 'DELETE'
  }),

  // Tags
  getTags: () => fetchWithAuth('/tags/'),
  getTag: (id) => fetchWithAuth(`/tags/${id}/`)
} 