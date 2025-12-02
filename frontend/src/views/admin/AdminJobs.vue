<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Download Jobs</h1>
      <div class="d-flex align-center" style="gap: 8px">
        <v-switch
          v-model="autoRefresh"
          color="primary"
          hide-details
          inset
          density="comfortable"
          :label="`Auto refresh ${refreshSeconds}s`"
        />
        <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchJobs">
          Refresh
        </v-btn>
      </div>
    </div>

    <v-card class="mb-3">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="4" md="3">
            <v-select
              v-model="filters.status"
              :items="statusItems"
              item-title="label"
              item-value="value"
              label="Status"
              prepend-inner-icon="mdi-filter"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
            />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-text-field
              v-model="filters.run"
              label="Run ID"
              prepend-inner-icon="mdi-telescope"
              hide-details
              density="comfortable"
              variant="outlined"
              type="number"
              min="1"
              clearable
            />
          </v-col>
          <v-col cols="12" sm="4" md="3" v-if="canViewAll">
            <v-text-field
              v-model="filters.user"
              label="User ID"
              prepend-inner-icon="mdi-account"
              hide-details
              density="comfortable"
              variant="outlined"
              type="number"
              min="1"
              clearable
            />
          </v-col>
          <v-col cols="12" sm="12" md="3" class="d-flex align-end">
            <v-btn color="secondary" variant="text" prepend-icon="mdi-filter-remove" @click="resetFilters">
              Reset Filters
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="mb-3">
      <v-card-text class="d-flex align-center justify-space-between" style="gap: 8px">
        <div class="text-body-2">
          {{ selectedCount }} selected
        </div>
        <div class="d-flex align-center" style="gap: 8px">
          <div class="d-inline-block">
            <v-btn
              color="error"
              variant="outlined"
              :disabled="selectedCount === 0 || !canBatchCancel"
              prepend-icon="mdi-close-octagon"
              @click="batchCancel"
            >
              Cancel ({{ selectedCount }})
            </v-btn>
            <v-tooltip v-if="batchCancelHint" activator="parent" location="top">
              {{ batchCancelHint }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              prepend-icon="mdi-clock-plus"
              :disabled="selectedCount === 0 || !canTTLModify"
              @click="extendDialog = true"
            >
              Extend expiry
            </v-btn>
            <v-tooltip v-if="extendHint" activator="parent" location="top">
              {{ extendHint }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              color="secondary"
              variant="outlined"
              prepend-icon="mdi-timer-off"
              :disabled="selectedCount === 0 || !canTTLModify"
              @click="batchExpireNow"
            >
              Expire now
            </v-btn>
            <v-tooltip v-if="expireHint" activator="parent" location="top">
              {{ expireHint }}
            </v-tooltip>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card>
      <v-data-table
        :headers="headers"
        :items="items"
        item-value="id"
        item-key="id"
        return-object
        show-select
        select-strategy="page"
        v-model="selected"
        v-model:selected="selected"
        v-model:selection="selected"
        @update:selected="onUpdateSelected"
        @update:modelValue="onUpdateSelected"
        @update:selection="onUpdateSelected"
        :loading="loading"
        class="custom-table"
      >
        <template #loading>
          <LoadingState type="table" />
        </template>
        <template #no-data>
          <EmptyState text="No jobs found." />
        </template>

        <template #item.id="{ item }">
          <code>{{ item.id }}</code>
        </template>

        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="flat">
            {{ item.status }}
          </v-chip>
        </template>

        <template #item.progress="{ item }">
          <div class="d-flex align-center" style="gap: 8px; min-width: 180px">
            <v-progress-linear
              :model-value="progressPercent(item)"
              height="8"
              rounded
              color="primary"
              style="flex: 1"
            />
            <span class="text-caption" style="width: 42px; text-align: right">{{ progressPercent(item) }}%</span>
          </div>
          <div class="text-caption text-medium-emphasis mt-1">
            {{ humanBytes(item.bytes_done) }} / {{ humanBytes(item.bytes_total) }}
          </div>
        </template>

        <template #item.created_at="{ item }">
          {{ item.created_at ? formatDateTime(item.created_at) : '—' }}
        </template>
        <template #item.user="{ item }">
          <span>{{ item.user_name || item.user || '—' }}</span>
        </template>
        <template #item.started_at="{ item }">
          {{ item.started_at ? formatDateTime(item.started_at) : '—' }}
        </template>
        <template #item.finished_at="{ item }">
          {{ item.finished_at ? formatDateTime(item.finished_at) : '—' }}
        </template>
        <template #item.expires_at="{ item }">
          {{ item.expires_at ? formatDateTime(item.expires_at) : '—' }}
        </template>

        <template #item.actions="{ item }">
          <div class="d-inline-block">
            <v-btn
              icon
              variant="text"
              :disabled="!canDownload(item)"
              :aria-label="`Download job ${item.id}`"
              @click="download(item)"
            >
              <v-icon>mdi-download</v-icon>
            </v-btn>
          </div>
          <div class="d-inline-block">
            <v-btn
              icon
              variant="text"
              color="error"
              :disabled="!canCancel(item)"
              :aria-label="`Cancel job ${item.id}`"
              @click="cancel(item)"
            >
              <v-icon>mdi-close-circle</v-icon>
            </v-btn>
            <v-tooltip v-if="cancelHint(item)" activator="parent" location="top">
              {{ cancelHint(item) }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              icon
              variant="text"
              :aria-label="`Details for job ${item.id}`"
              @click="openDetails(item)"
            >
              <v-icon>mdi-information</v-icon>
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Details dialog -->
    <v-dialog v-model="detailsOpen" max-width="700">
      <v-card>
        <v-card-title class="text-h6">Job #{{ details?.id }}</v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Status</div>
              <v-chip :color="statusColor(details?.status)" size="small" variant="flat">
                {{ details?.status }}
              </v-chip>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Progress</div>
              <div class="d-flex align-center" style="gap: 8px">
                <v-progress-linear
                  :model-value="progressPercent(details)"
                  height="8"
                  rounded
                  color="primary"
                  style="flex: 1"
                />
                <span class="text-caption">{{ progressPercent(details) }}%</span>
              </div>
              <div class="text-caption text-medium-emphasis mt-1">
                {{ humanBytes(details?.bytes_done) }} / {{ humanBytes(details?.bytes_total) }}
              </div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Run ID</div>
              <div>{{ details?.run ?? '—' }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">User ID</div>
              <div>{{ details?.user ?? '—' }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Created</div>
              <div>{{ formatDateTime(details?.created_at) }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Started</div>
              <div>{{ formatDateTime(details?.started_at) || '—' }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Finished</div>
              <div>{{ formatDateTime(details?.finished_at) || '—' }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis mb-1">Expires</div>
              <div>{{ formatDateTime(details?.expires_at) || '—' }}</div>
            </v-col>
            <v-col cols="12">
              <div class="text-caption text-medium-emphasis mb-1">Error</div>
              <v-alert v-if="details?.error" type="error" variant="tonal" density="comfortable">
                <pre class="mb-0" style="white-space: pre-wrap">{{ details.error }}</pre>
              </v-alert>
              <div v-else>—</div>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailsOpen = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <!-- Extend expiry dialog -->
    <v-dialog v-model="extendDialog" max-width="420">
      <v-card>
        <v-card-title class="text-h6">Extend expiry</v-card-title>
        <v-card-text>
          <div class="mb-2">Extend expiry of {{ selectedCount }} job(s) by:</div>
          <v-text-field
            v-model="extendHours"
            type="number"
            min="1"
            step="1"
            label="Hours"
            density="comfortable"
            variant="outlined"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="extendDialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="confirmExtend">Extend</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
  </template>

  <script setup>
  import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
  import { debounce } from 'lodash'
  import { api } from '@/services/api'
  import LoadingState from '@/components/ui/LoadingState.vue'
  import EmptyState from '@/components/ui/EmptyState.vue'
  import { useNotifyStore } from '@/store/notify'
  import { formatDateTime } from '@/utils/datetime'
  import { useAuthStore } from '@/store/auth'
  
  const loading = ref(false)
  const items = ref([])
  const selected = ref([])
  const notify = useNotifyStore()
  const auth = useAuthStore()
  const myUserId = computed(() => auth?.user?.id)
  const canViewAll = computed(() => auth.isAdmin || auth.hasPerm('users.acl_jobs_view_all') || auth.hasPerm('acl_jobs_view_all'))
  const canBatchCancel = computed(() => auth.isAdmin || auth.hasPerm('users.acl_jobs_cancel_any') || auth.hasPerm('acl_jobs_cancel_any'))
  const canTTLModify = computed(() => auth.isAdmin || auth.hasPerm('users.acl_jobs_ttl_modify') || auth.hasPerm('acl_jobs_ttl_modify'))
  
  const headers = [
    { title: 'ID', key: 'id', sortable: true },
    { title: 'Run', key: 'run', sortable: true },
    { title: 'User', key: 'user', sortable: true },
    { title: 'Status', key: 'status', sortable: true },
    { title: 'Progress', key: 'progress', sortable: false },
    { title: 'Created', key: 'created_at', sortable: true },
    { title: 'Started', key: 'started_at', sortable: true },
    { title: 'Finished', key: 'finished_at', sortable: true },
    { title: 'Expires', key: 'expires_at', sortable: true },
    { title: 'Actions', key: 'actions', sortable: false },
  ]
  
  const statusItems = [
    { label: 'queued', value: 'queued' },
    { label: 'running', value: 'running' },
    { label: 'done', value: 'done' },
    { label: 'failed', value: 'failed' },
    { label: 'cancelled', value: 'cancelled' },
    { label: 'expired', value: 'expired' },
  ]
  
  const filters = ref({
    status: null,
    run: '',
    user: '',
  })
  
  const autoRefresh = ref(true)
  const refreshSeconds = 5
  let intervalId = null
  
  const hasActiveJobs = computed(() => {
    return items.value.some(j => j.status === 'queued' || j.status === 'running')
  })
  
  const scheduleRefresh = () => {
    clearRefresh()
    if (autoRefresh.value && hasActiveJobs.value) {
      intervalId = setInterval(() => {
        fetchJobs()
      }, refreshSeconds * 1000)
    }
  }
  
  const clearRefresh = () => {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }
  
  const progressPercent = (job) => {
    if (!job) return 0
    if (typeof job.progress === 'number' && isFinite(job.progress)) {
      const p = Math.max(0, Math.min(100, Math.round(job.progress)))
      return p
    }
    if (typeof job.bytes_total === 'number' && job.bytes_total > 0 && typeof job.bytes_done === 'number') {
      const p = Math.round((job.bytes_done / job.bytes_total) * 100)
      return Math.max(0, Math.min(100, p))
    }
    return 0
  }
  
  const statusColor = (status) => {
    switch (status) {
      case 'queued': return 'grey'
      case 'running': return 'primary'
      case 'done': return 'success'
      case 'failed': return 'error'
      case 'cancelled': return 'warning'
      case 'expired': return 'secondary'
      default: return 'default'
    }
  }
  
  const humanBytes = (n) => {
    if (!n || typeof n !== 'number' || !isFinite(n) || n < 0) return '0 B'
    const units = ['B','KB','MB','GB','TB']
    let i = 0
    let v = n
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024
      i++
    }
    return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
  }
  
  const fetchJobs = async () => {
    loading.value = true
    try {
      const params = {}
      if (filters.value.status) params.status = filters.value.status
      if (filters.value.run) params.run = filters.value.run
      if (filters.value.user) params.user = filters.value.user
      const res = await api.adminListDownloadJobs(params)
      const arr = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : [])
      items.value = arr
    } catch (e) {
      items.value = []
    } finally {
      loading.value = false
      scheduleRefresh()
    }
  }
  
  // Debounced auto-fetch when filters change
  const debouncedFetch = debounce(() => {
    fetchJobs()
  }, 300)
  watch(filters, () => {
    debouncedFetch()
  }, { deep: true })
  
  const resetFilters = () => {
    filters.value.status = null
    filters.value.run = ''
    filters.value.user = ''
    fetchJobs()
  }
  
  const selectedIds = computed(() => selected.value.map(val => {
    return (val && typeof val === 'object') ? val.id : val
  }).filter(v => v !== null && v !== undefined && v !== ''))
  const selectedCount = computed(() => selectedIds.value.length)

  const onUpdateSelected = (val) => {
    try {
    } catch (e) {}
    selected.value = Array.isArray(val) ? val : []
  }

  // Extra debug: observe selection reactivity
  watch(selected, (val) => {
    try {
    } catch (e) {}
  }, { deep: true })

  const canDownload = (job) => {
    return job?.status === 'done'
  }
  
  const canCancel = (job) => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return false
    // Owners can always cancel own jobs
    if (myUserId.value && job.user === myUserId.value) return true
    // Admins need explicit permission to cancel any
    return !!canBatchCancel.value
  }
  const cancelHint = (job) => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return ''
    if (myUserId.value && job.user === myUserId.value) return ''
    if (!canBatchCancel.value) return 'No permission'
    return ''
  }
  
  const download = async (job) => {
    if (!job?.id) return
    try {
      await api.downloadJobFile(job.id)
    } catch (e) {
      // notification already shown by api helper
    }
  }
  
  const cancel = async (job) => {
    if (!job?.id || !canCancel(job)) return
    if (!confirm(`Cancel job #${job.id}?`)) return
    try {
      await api.adminCancelDownloadJob(job.id)
      await fetchJobs()
    } catch (e) {
      // notify handled
    }
  }
  
  const batchCancel = async () => {
    if (selectedCount.value === 0 || !canBatchCancel.value) return
    if (!confirm(`Cancel ${selectedCount.value} selected job(s)?`)) return
    try {
      await api.adminBatchCancelJobs(selectedIds.value)
      selected.value = []
      await fetchJobs()
    } catch (e) {}
  }
  const batchCancelHint = computed(() => {
    if (selectedCount.value === 0) return 'Select jobs first'
    if (!canBatchCancel.value) return 'No permission'
    return ''
  })

  const extendDialog = ref(false)
  const extendHours = ref(48)
  const confirmExtend = async () => {
    if (selectedCount.value === 0 || !canTTLModify.value) { extendDialog.value = false; return }
    const hours = parseInt(extendHours.value, 10)
    if (!Number.isFinite(hours) || hours <= 0) {
      notify.error('Please enter a positive number of hours')
      return
    }
    try {
      await api.adminBatchExtendJobsExpiry(selectedIds.value, hours)
      extendDialog.value = false
      selected.value = []
      await fetchJobs()
    } catch (e) {}
  }
  const extendHint = computed(() => {
    if (selectedCount.value === 0) return 'Select jobs first'
    if (!canTTLModify.value) return 'No permission'
    return ''
  })

  const batchExpireNow = async () => {
    if (selectedCount.value === 0 || !canTTLModify.value) return
    if (!confirm(`Expire ${selectedCount.value} selected job(s) now? This will delete ZIP files.`)) return
    try {
      await api.adminBatchExpireJobsNow(selectedIds.value)
      selected.value = []
      await fetchJobs()
    } catch (e) {}
  }
  const expireHint = computed(() => {
    if (selectedCount.value === 0) return 'Select jobs first'
    if (!canTTLModify.value) return 'No permission'
    return ''
  })

  const detailsOpen = ref(false)
  const details = ref(null)
  const openDetails = (job) => {
    details.value = job
    detailsOpen.value = true
  }
  
  onMounted(() => {
    fetchJobs()
  })
  
  onBeforeUnmount(() => {
    clearRefresh()
  })
  
  watch([autoRefresh, hasActiveJobs], () => {
    scheduleRefresh()
  })
  </script>
  
  <style scoped>
  .custom-table :deep(th) {
    position: sticky;
    top: 0;
    background: rgb(var(--v-theme-surface));
    z-index: 2;
  }
  .custom-table :deep(td) { padding: 8px 16px !important; }
  </style>
  



