import { useAuthStore } from '@/store/auth'
import router from '@/router'
import { useNotifyStore } from '@/store/notify'

const API_BASE_URL = import.meta.env?.VITE_API_BASE || '/api'

async function fetchWithAuth(url, options = {}) {
  const authStore = useAuthStore()
  const headers = {
    ...options.headers
  }

  // Only set Content-Type if not FormData (browser will set it automatically for FormData)
  if (!(options.body instanceof FormData)) {
    if (!headers['Content-Type'] && !headers['content-type']) {
      headers['Content-Type'] = 'application/json'
    }
  }

  if (authStore.token) {
    headers['Authorization'] = `Token ${authStore.token}`
  }

  // Handle query parameters
  let fullUrl = `${API_BASE_URL}${url}`
  if (options.params) {
    const searchParams = new URLSearchParams()
    const hasLimitProvided = Object.prototype.hasOwnProperty.call(options.params, 'limit')
    Object.entries(options.params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        // Preserve original key; if value is an array, append each entry
        if (Array.isArray(value)) {
          value.forEach((v) => {
            if (v !== undefined && v !== null && v !== '') {
              searchParams.append(key, v)
            }
          })
        } else {
          searchParams.append(key, value)
        }
        // Add compatibility alias when page_size is provided (support both PageNumber and LimitOffset pagination)
        if (key === 'page_size' && !hasLimitProvided) {
          searchParams.append('limit', value)
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
    headers,
    credentials: 'include', // Include cookies for session authentication
  })

  // Global 401 handling: clear auth and redirect to login
  if (response.status === 401) {
    try {
      await authStore.logout()
    } catch (e) {
      // ignore
    }
    try {
      const path = window?.location?.pathname || '/'
      const search = window?.location?.search || ''
      const hash = window?.location?.hash || ''
      const next = `${path}${search}${hash}`
      if (router.currentRoute.value.path !== '/login') {
        router.push({ path: '/login', query: { next } })
      }
    } catch (e) {
      // Router not available (unlikely); hard redirect
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    }
    const error = new Error('Unauthorized')
    error.status = 401
    throw error
  }

  const acceptable = Array.isArray(options.acceptableStatus) ? options.acceptableStatus : []
  if (!response.ok && !acceptable.includes(response.status)) {
    const error = new Error(`API error: ${response.status}`)
    error.status = response.status
    try {
      const data = await response.json()
      error.data = data
    } catch (e) {
      // Handle non-JSON response silently
    }
    try {
      const notify = useNotifyStore()
      const msg = error?.data?.detail || error?.data?.error || `API error ${response.status}`
      notify.error(msg)
    } catch {}
    throw error
  }

  // Try JSON; if no JSON body (e.g., 204 No Content), return empty object
  try {
    return await response.json()
  } catch {
    return {}
  }
}

export const api = {
  // Dashboard Stats (aggregiert aus verschiedenen Endpunkten)
  getDashboardStats: async () => {
    const response = await fetchWithAuth('/runs/dashboard/stats/')
    return response
  },

  // Observation Runs
  // Recent runs: order by newest mid_observation_jd first
  getRecentRuns: () => fetchWithAuth('/runs/runs/?limit=20&ordering=-mid_observation_jd'),
  getObservationRun: (id) => fetchWithAuth(`/runs/runs/${id}/`),
  getObservationRuns: (params) => fetchWithAuth('/runs/runs/', { params }),
  getAllObservationRuns: () => fetchWithAuth('/runs/runs/?limit=1000'),  // Get all runs for filtering
  updateObservationRun: (id, data) => fetchWithAuth(`/runs/runs/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteObservationRun: (id) => fetchWithAuth(`/runs/runs/${id}/`, { method: 'DELETE', acceptableStatus: [404] }),
  // getRunDataFiles: deprecated in favor of paged datafiles endpoint
  getRunDataFilesPaged: (runId, params = {}) => {
    const queryParams = {
      observation_run: runId,
      page: params.page || 1,
      limit: params.limit || 10,
    }
    if (params.file_type) queryParams.file_type = params.file_type
    if (params.binning) queryParams.binning = params.binning
    if (params.instrument) queryParams.instrument = params.instrument
    if (params.main_target) queryParams.main_target = params.main_target
    if (params.exptime_min != null) queryParams.exptime_min = params.exptime_min
    if (params.exptime_max != null) queryParams.exptime_max = params.exptime_max
    if (params.exposure_type && Array.isArray(params.exposure_type) && params.exposure_type.length) {
      // MultipleChoiceFilter: repeated query params
      params.exposure_type.forEach(v => {
        if (v != null && v !== '') {
          if (!queryParams.exposure_type) queryParams.exposure_type = []
          queryParams.exposure_type.push(v)
        }
      })
    }
    if (params.spectroscopy != null) queryParams.spectroscopy = params.spectroscopy
    if (params.file_name) queryParams.file_name = params.file_name
    if (params.obs_date_contains) queryParams.obs_date_contains = params.obs_date_contains
    if (params.plate_solved != null && params.plate_solved !== '') queryParams.plate_solved = params.plate_solved
    if (params.pixel_count_min != null) queryParams.pixel_count_min = params.pixel_count_min
    if (params.pixel_count_max != null) queryParams.pixel_count_max = params.pixel_count_max
    return fetchWithAuth('/runs/datafiles/', { params: queryParams })
  },
  getDataFileThumbnailUrl: (pk, w = 512) => {
    const base = API_BASE_URL
    const url = `${base}/runs/datafiles/${pk}/thumbnail/?w=${encodeURIComponent(w)}`
    return url
  },
  getDataFileHeader: (pk) => fetchWithAuth(`/runs/datafiles/${pk}/header/`),
  getDataFileDownloadUrl: (pk) => {
    const base = API_BASE_URL
    return `${base}/runs/datafiles/${pk}/download/`
  },
  getRunDataFilesZipUrl: (runId, ids = [], filters) => {
    const base = API_BASE_URL
    const params = new URLSearchParams()
    if (ids && ids.length) params.set('ids', ids.join(','))
    // carry over current filters if present (subset used by backend)
    const carry = ['file_type','instrument','main_target','exptime_min','exptime_max','file_name','pixel_count_min','pixel_count_max','exposure_type','spectroscopy','obs_date_contains','plate_solved']
    if (filters && typeof filters === 'object') {
      carry.forEach(k => {
        const v = filters[k]
        if (v == null || v === '') return
        if (Array.isArray(v)) {
          v.forEach(x => params.append(k, x))
        } else {
          params.set(k, v)
        }
      })
    }
    const qs = params.toString()
    return `${base}/runs/runs/${runId}/download/${qs ? `?${qs}` : ''}`
  },
  // Async download jobs for a run
  createRunDownloadJob: (runId, ids = [], filters = {}) => {
    return fetchWithAuth(`/runs/runs/${runId}/download-jobs/`, {
      method: 'POST',
      body: JSON.stringify({ ids, filters })
    })
  },
  getDownloadJobStatus: (jobId) => fetchWithAuth(`/runs/jobs/${jobId}/status`),
  getDownloadJobDownloadUrl: (jobId) => {
    const base = API_BASE_URL
    return `${base}/runs/jobs/${encodeURIComponent(jobId)}/download`
  },
  downloadJobFile: async (jobId) => {
    // Authenticated fetch to download file as blob
    const authStore = useAuthStore()
    const url = `${API_BASE_URL}/runs/jobs/${encodeURIComponent(jobId)}/download`
    const headers = {}
    if (authStore.token) headers['Authorization'] = `Token ${authStore.token}`
    const resp = await fetch(url, { headers })
    if (!resp.ok) {
      let msg = `Download failed (${resp.status})`
      try {
        const data = await resp.json()
        msg = data?.detail || data?.error || msg
      } catch {}
      try { const notify = useNotifyStore(); notify.error(msg) } catch {}
      throw new Error(msg)
    }
    const blob = await resp.blob()
    // Try to get filename from header
    let filename = `download_job_${jobId}.zip`
    const cd = resp.headers.get('Content-Disposition') || resp.headers.get('content-disposition')
    if (cd) {
      const m = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i)
      const val = (m && (m[1] || m[2])) ? decodeURIComponent(m[1] || m[2]) : null
      if (val) filename = val
    }
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    document.body.appendChild(link)
    link.click()
    setTimeout(() => {
      URL.revokeObjectURL(link.href)
      link.remove()
    }, 0)
  },
  getDataFilesZipUrl: (ids = [], filters) => {
    const base = API_BASE_URL
    const params = new URLSearchParams()
    if (ids && ids.length) params.set('ids', ids.join(','))
    const carry = ['file_type','instrument','main_target','exptime_min','exptime_max','file_name','pixel_count_min','pixel_count_max','exposure_type','spectroscopy','obs_date_contains','plate_solved']
    if (filters && typeof filters === 'object') {
      carry.forEach(k => {
        const v = filters[k]
        if (v == null || v === '') return
        if (Array.isArray(v)) {
          v.forEach(x => params.append(k, x))
        } else {
          params.set(k, v)
        }
      })
    }
    const qs = params.toString()
    return `${base}/runs/datafiles/download/${qs ? `?${qs}` : ''}`
  },
  // Async bulk (across runs) download jobs
  createBulkDownloadJob: (ids = [], filters = {}) => {
    return fetchWithAuth('/runs/datafiles/download-jobs/', {
      method: 'POST',
      body: JSON.stringify({ ids, filters })
    })
  },

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
    // Add observation type filters if present
    if (params.photometry !== undefined && params.photometry !== null) queryParams.photometry = params.photometry
    if (params.spectroscopy !== undefined && params.spectroscopy !== null) queryParams.spectroscopy = params.spectroscopy
    // Add lights count filters if present
    if (params.n_light_min !== undefined && params.n_light_min !== null && params.n_light_min !== '') queryParams.n_light_min = params.n_light_min
    if (params.n_light_max !== undefined && params.n_light_max !== null && params.n_light_max !== '') queryParams.n_light_max = params.n_light_max
    return fetchWithAuth('/objects/vuetify', { params: queryParams })
  },
  getObject: (id) => fetchWithAuth(`/objects/${id}/`),
  getObjectObservationRuns: (id) => fetchWithAuth(`/objects/${id}/observation_runs/`),
  getObjectDataFiles: (id) => fetchWithAuth(`/objects/${id}/datafiles/`),
  // Use last_modified (supported server-side) instead of created_at
  getRecentObjects: () => fetchWithAuth('/objects/?limit=10&ordering=-last_modified'),
  createObject: (data) => fetchWithAuth('/objects/', {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  updateObject: (id, data) => fetchWithAuth(`/objects/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  deleteObject: (id) => fetchWithAuth(`/objects/${id}/`, { method: 'DELETE' }),
  mergeObjects: (targetId, sourceIds = [], combineTags = true) => fetchWithAuth('/objects/merge/', {
    method: 'POST',
    body: JSON.stringify({ target_id: targetId, source_ids: sourceIds, combine_tags: !!combineTags })
  }),

  // Tags
  getTags: (params = {}) => fetchWithAuth('/tags/', { params }),
  getTag: (id) => fetchWithAuth(`/tags/${id}/`),
  createTag: (data) => fetchWithAuth('/tags/', { method: 'POST', body: JSON.stringify(data) }),
  updateTag: (id, data) => fetchWithAuth(`/tags/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteTag: (id) => fetchWithAuth(`/tags/${id}/`, { method: 'DELETE' })
,

  // Admin - Users
  adminListUsers: (params = {}) => fetchWithAuth('/users/admin/users/', { params }),
  adminUpdateUser: (id, data) => fetchWithAuth(`/users/admin/users/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  adminDeleteUser: (id) => fetchWithAuth(`/users/admin/users/${id}/`, { method: 'DELETE' }),
  adminLdapTest: (payload = {}) => fetchWithAuth('/users/admin/ldap/test/', { method: 'POST', body: JSON.stringify(payload) })
,
  // Admin - ACL
  adminAclGet: () => fetchWithAuth('/users/admin/acl/'),
  adminAclSet: (matrix = {}) => fetchWithAuth('/users/admin/acl/set', { method: 'POST', body: JSON.stringify({ matrix }) }),

  // Admin - System Health & Maintenance (moved under /api/admin)
  adminHealth: () => fetchWithAuth('/admin/health/'),
  adminMaintenanceCleanup: () => fetchWithAuth('/admin/maintenance/cleanup-downloads/', { method: 'POST' }),
  adminMaintenanceReconcile: (dryRun = true) => fetchWithAuth('/admin/maintenance/reconcile/', { method: 'POST', body: JSON.stringify({ dry_run: !!dryRun }) }),
  adminMaintenanceOrphansHashcheck: (opts = {}) => {
    const body = {
      dry_run: opts.dry_run !== undefined ? !!opts.dry_run : true,
      fix_missing_hashes: opts.fix_missing_hashes !== undefined ? !!opts.fix_missing_hashes : true,
      limit: opts.limit != null ? opts.limit : null,
    }
    return fetchWithAuth('/admin/maintenance/orphans-hashcheck/', { method: 'POST', body: JSON.stringify(body) })
  },
  adminMaintenanceScanMissing: (opts = {}) => {
    const body = {
      dry_run: opts.dry_run !== undefined ? !!opts.dry_run : true,
      limit: opts.limit != null ? opts.limit : null,
    }
    return fetchWithAuth('/admin/maintenance/scan-missing/', { method: 'POST', body: JSON.stringify(body) })
  },
  adminMaintenanceOrphanObjects: (opts = {}) => {
    const body = {
      dry_run: opts.dry_run !== undefined ? !!opts.dry_run : true,
    }
    return fetchWithAuth('/admin/maintenance/orphan-objects/', { method: 'POST', body: JSON.stringify(body) })
  },
  adminMaintenanceUnlinkNonLightDatafiles: (opts = {}) => {
    const body = {
      dry_run: opts.dry_run !== undefined ? !!opts.dry_run : true,
    }
    return fetchWithAuth('/admin/maintenance/unlink-non-light-datafiles/', { method: 'POST', body: JSON.stringify(body) })
  },
  adminMaintenanceRefreshDashboardStats: () => fetchWithAuth('/admin/maintenance/refresh-dashboard-stats/', { method: 'POST' }),
  adminMaintenanceTriggerPlateSolve: () => fetchWithAuth('/admin/maintenance/plate-solving/', { method: 'POST' }),
  adminMaintenanceReEvaluatePlateSolved: () => fetchWithAuth('/admin/maintenance/re-evaluate-plate-solved/', { method: 'POST' }),
  getAllDataFiles: (params = {}) => fetchWithAuth('/admin/datafiles/', { params }),
  adminReEvaluateDataFiles: (ids = []) => fetchWithAuth('/admin/datafiles/re-evaluate/', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  }),
  adminLinkDatafilesToObject: (datafileIds, objectId) => fetchWithAuth('/admin/datafiles/link-objects/', {
    method: 'POST',
    body: JSON.stringify({ datafile_ids: datafileIds, object_id: objectId }),
  }),
  // Admin - Runs date tools
  adminSetRunDate: (runId, payload = {}) => fetchWithAuth(`/admin/runs/${encodeURIComponent(runId)}/set-date/`, { method: 'POST', body: JSON.stringify(payload) }),
  adminRecomputeRunDate: (runId) => fetchWithAuth(`/admin/runs/${encodeURIComponent(runId)}/recompute-date/`, { method: 'POST' }),
  adminReEvaluateRun: (runId) => fetchWithAuth(`/admin/runs/${encodeURIComponent(runId)}/re-evaluate/`, { method: 'POST' }),
  adminClearOverrideFlag: (modelType, instanceId, fieldName) => fetchWithAuth(`/admin/override-flags/${encodeURIComponent(modelType)}/${encodeURIComponent(instanceId)}/${encodeURIComponent(fieldName)}/clear/`, { method: 'POST' }),
  adminClearAllOverrides: (modelType, instanceId) => fetchWithAuth(`/admin/override-flags/${encodeURIComponent(modelType)}/${encodeURIComponent(instanceId)}/clear-all/`, { method: 'POST' }),
  adminListOverrideFlags: () => fetchWithAuth('/admin/override-flags/list/'),
  adminDeleteObjectAliases: (objectId) => fetchWithAuth(`/admin/objects/${encodeURIComponent(objectId)}/delete-aliases/`, { method: 'POST' }),
  adminUpdateObjectIdentifiers: (objectId, matchMethod, dryRun) => fetchWithAuth(`/admin/objects/${encodeURIComponent(objectId)}/update-identifiers/`, {
    method: 'POST',
    body: JSON.stringify({
      match_method: matchMethod,
      dry_run: dryRun,
    }),
  }),
  // Site-wide Banner
  getBanner: () => fetchWithAuth('/runs/banner/'),
  adminGetBanner: () => fetchWithAuth('/admin/banner/'),
  adminSetBanner: (payload = { enabled: true, message: '', level: 'warning' }) => fetchWithAuth('/admin/banner/set', { method: 'POST', body: JSON.stringify(payload) }),
  adminClearBanner: () => fetchWithAuth('/admin/banner/clear', { method: 'POST' }),

  // Admin - Jobs
  adminListDownloadJobs: (params = {}) => fetchWithAuth('/runs/jobs/', { params }),
  adminCancelDownloadJob: (jobId) => fetchWithAuth(`/runs/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  adminBatchCancelJobs: (ids = []) => fetchWithAuth('/runs/jobs/batch/cancel', { method: 'POST', body: JSON.stringify({ ids }) }),
  adminBatchExtendJobsExpiry: (ids = [], hours = 48) => fetchWithAuth('/runs/jobs/batch/extend-expiry', { method: 'POST', body: JSON.stringify({ ids, hours }) }),
  adminBatchExpireJobsNow: (ids = []) => fetchWithAuth('/runs/jobs/batch/expire-now', { method: 'POST', body: JSON.stringify({ ids }) }),

  // Dark Finder
  darkFinderSearch: (params) => fetchWithAuth('/runs/dark-finder/', { 
    method: 'POST', 
    body: JSON.stringify(params) 
  }),
  parseFitsHeader: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return fetchWithAuth('/runs/parse-fits-header/', { 
      method: 'POST', 
      body: formData,
      headers: {} // Kein Content-Type für FormData
    })
  },
  getInstruments: () => fetchWithAuth('/runs/instruments/'),
  getInstrumentCatalog: () => fetchWithAuth('/runs/instrument-catalog/'),

  // Exposure Type Classification (Admin)
  getExposureTypeDiscrepancies: (params = {}) => {
    const queryString = new URLSearchParams(params).toString()
    return fetchWithAuth(`/admin/datafiles/discrepancies/${queryString ? '?' + queryString : ''}`)
  },
  updateExposureTypeUser: (datafileId, data) => fetchWithAuth(`/admin/datafiles/${encodeURIComponent(datafileId)}/exposure-type-user/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }),
  // Spectrograph Management (Admin)
  getSpectrographFiles: (params = {}) => {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const queryString = queryParams.toString()
    return fetchWithAuth(`/admin/datafiles/spectrograph/${queryString ? `?${queryString}` : ''}`)
  },
  updateSpectrograph: (datafileId, data) => fetchWithAuth(`/admin/datafiles/${encodeURIComponent(datafileId)}/spectrograph/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  }),
  // Plate Solving (Admin)
  getUnsolvedPlateFiles: (params = {}) => {
    const queryParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value)
      }
    })
    const queryString = queryParams.toString()
    return fetchWithAuth(`/admin/datafiles/plate-solving/unsolved/${queryString ? `?${queryString}` : ''}`)
  },
  triggerPlateSolve: (fileIds) => fetchWithAuth('/admin/datafiles/plate-solving/trigger/', {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  }),
  getPlateSolveStats: () => fetchWithAuth('/admin/datafiles/plate-solving/stats/'),
  getPlateSolvingTaskEnabled: () => fetchWithAuth('/admin/datafiles/plate-solving/task-enabled/'),
  setPlateSolvingTaskEnabled: (enabled) => fetchWithAuth('/admin/datafiles/plate-solving/task-enabled/set/', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  }),
  getObservationRunsForPlateSolving: () => fetchWithAuth('/admin/datafiles/plate-solving/observation-runs/'),
}