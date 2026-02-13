<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · System Health</h1>
      <div class="d-flex align-center" style="gap: 8px">
        <v-switch
          v-model="autoRefresh"
          color="primary"
          hide-details
          inset
          density="comfortable"
          :label="`Auto refresh ${refreshSeconds}s`"
        />
        <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchHealth">
          Refresh
        </v-btn>
      </div>
    </div>

    <v-row>
      <v-col cols="12" md="6">
        <v-card class="mb-4">
          <v-card-title class="text-h6">Overview</v-card-title>
          <v-card-text>
            <div class="d-flex flex-wrap" style="gap: 10px">
              <div>
                <div class="text-caption text-medium-emphasis mb-1">Python</div>
                <div>{{ health.versions?.python || '—' }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis mb-1">Django</div>
                <div>{{ health.versions?.django || '—' }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis mb-1">Bokeh</div>
                <div>{{ health.versions?.bokeh ?? '—' }}</div>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <v-card class="mb-4">
          <v-card-title class="text-h6">Database</v-card-title>
          <v-card-text>
            <v-chip :color="health.database?.ok ? 'success' : 'error'" size="small" class="mr-2">
              {{ health.database?.ok ? 'OK' : 'ERROR' }}
            </v-chip>
            <span v-if="health.database?.latency_ms != null" class="text-caption text-medium-emphasis">
              latency {{ health.database.latency_ms }}ms
            </span>
            <div v-if="health.db_error" class="text-error mt-2 text-caption">{{ health.db_error }}</div>
          </v-card-text>
        </v-card>

        <v-card class="mb-4">
          <v-card-title class="text-h6">Aladin</v-card-title>
          <v-card-text>
            <v-chip
              :color="health.aladin?.ok === true ? 'success' : (health.aladin?.ok === false ? 'error' : 'secondary')"
              size="small"
              class="mr-2"
            >
              {{ health.aladin?.ok === true ? 'OK' : (health.aladin?.ok === false ? 'ERROR' : 'UNKNOWN') }}
            </v-chip>
            <span v-if="health.aladin?.latency_ms != null" class="text-caption text-medium-emphasis">
              latency {{ health.aladin.latency_ms }}ms
            </span>
            <div v-if="health.aladin?.status_code != null" class="text-caption text-medium-emphasis mt-1">
              status {{ health.aladin.status_code }}
            </div>
            <div v-if="health.aladin?.error" class="text-error text-caption mt-1">
              {{ health.aladin.error }}
            </div>
          </v-card-text>
        </v-card>

        <v-card class="mb-4">
          <v-card-title class="text-h6">Redis (Broker)</v-card-title>
          <v-card-text>
            <div class="mb-2 text-caption text-medium-emphasis">{{ health.celery?.broker_url || '—' }}</div>
            <v-chip
              :color="health.redis?.ok === true ? 'success' : (health.redis?.ok === false ? 'error' : 'secondary')"
              size="small"
              class="mr-2"
            >
              {{ health.redis?.ok === true ? 'OK' : (health.redis?.ok === false ? 'ERROR' : 'UNKNOWN') }}
            </v-chip>
            <span v-if="health.redis?.latency_ms != null" class="text-caption text-medium-emphasis">
              latency {{ health.redis.latency_ms }}ms
            </span>
            <div v-if="health.redis_error" class="text-error mt-2 text-caption">{{ health.redis_error }}</div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card class="mb-4">
          <v-card-title class="text-h6">Celery</v-card-title>
          <v-card-text>
            <div class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Workers</div>
              <v-chip :color="health.celery?.workers_alive ? 'success' : 'error'" size="small" class="mr-2">
                {{ health.celery?.workers_alive ? 'ALIVE' : 'NO RESPONSE' }}
              </v-chip>
              <span v-if="Array.isArray(health.celery?.workers) && health.celery.workers.length" class="text-caption">
                {{ health.celery.workers.join(', ') }}
              </span>
            </div>
            <div class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Eager Mode</div>
              <v-chip :color="health.celery?.task_always_eager ? 'error' : 'success'" size="small">
                {{ health.celery?.task_always_eager ? 'ENABLED (disable for prod)' : 'DISABLED' }}
              </v-chip>
            </div>
            <div v-if="health.celery_ping_error" class="text-error text-caption">
              {{ health.celery_ping_error }}
            </div>
          </v-card-text>
        </v-card>

        <v-card class="mb-4">
          <v-card-title class="text-h6">Storage</v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-1">Path</div>
            <div class="mb-2"><code>{{ health.storage?.path || '—' }}</code></div>
            <v-chip
              :color="health.storage?.ok ? 'success' : 'error'"
              size="small"
              class="mr-2"
            >
              {{ health.storage?.ok ? 'OK' : 'ERROR' }}
            </v-chip>
            <span v-if="health.storage?.exists === false" class="text-caption text-error">path does not exist</span>
            <div v-if="health.storage?.total_bytes != null" class="text-caption text-medium-emphasis mt-2">
              Total: {{ humanBytes(health.storage.total_bytes) }} ·
              Used: {{ humanBytes(health.storage.used_bytes) }} ·
              Free: {{ humanBytes(health.storage.free_bytes) }}
            </div>
            <div v-if="health.storage?.error" class="text-error mt-2 text-caption">{{ health.storage.error }}</div>
          </v-card-text>
        </v-card>

        <v-card class="mb-4">
          <v-card-title class="text-h6">LDAP</v-card-title>
          <v-card-text>
            <div class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Configured</div>
              <v-chip :color="health.ldap?.configured ? 'success' : 'secondary'" size="small">
                {{ health.ldap?.configured ? 'Yes' : 'No' }}
              </v-chip>
            </div>
            <div v-if="health.ldap?.configured" class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Server</div>
              <div class="text-caption">{{ health.ldap?.server_uri || '—' }}</div>
            </div>
            <div v-if="health.ldap?.configured" class="mb-2">
              <div class="text-caption text-medium-emphasis mb-1">Module</div>
              <v-chip :color="health.ldap?.can_import ? 'success' : 'error'" size="small">
                {{ health.ldap?.can_import ? 'Available' : 'Missing' }}
              </v-chip>
            </div>
            <div v-if="health.ldap?.configured">
              <div class="text-caption text-medium-emphasis mb-1">Bind</div>
              <v-chip :color="health.ldap?.bind_ok ? 'success' : 'error'" size="small">
                {{ health.ldap?.bind_ok ? 'OK' : 'Failed' }}
              </v-chip>
              <div v-if="health.ldap?.bind_error" class="text-error text-caption mt-1">{{ health.ldap.bind_error }}</div>
              <div v-if="health.ldap?.tls_error" class="text-error text-caption mt-1">{{ health.ldap.tls_error }}</div>
              <div v-if="health.ldap?.connect_error" class="text-error text-caption mt-1">{{ health.ldap.connect_error }}</div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card>
      <v-card-title class="text-h6">Download Jobs</v-card-title>
      <v-card-text>
        <div class="d-flex flex-wrap" style="gap: 10px">
          <div v-for="s in jobStatuses" :key="s" class="d-flex align-center" style="gap: 6px">
            <v-chip :color="jobColor(s)" size="small" variant="flat">{{ s }}</v-chip>
            <span class="text-body-2">{{ health.jobs?.[s] ?? 0 }}</span>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-row class="mt-4">
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title class="text-h6">Periodic Tasks</v-card-title>
          <v-card-text>
            <div v-for="name in ['cleanup_expired_downloads', 'reconcile_filesystem', 'cleanup_orphans_hashcheck', 'scan_missing_filesystem', 'cleanup_orphan_objects', 'plate_solve_pending_files', 're_evaluate_plate_solved_files']" :key="name" class="mb-3">
              <div class="d-flex align-center" style="gap: 8px">
                <div class="text-subtitle-2">{{ name }}</div>
                <v-chip
                  size="x-small"
                  :color="taskStatusColor(health.periodic?.[name])"
                  variant="flat"
                >
                  {{ taskStatusLabel(health.periodic?.[name]) }}
                </v-chip>
              </div>
              <div class="text-caption text-medium-emphasis">
                Last run:
                <span v-if="health.periodic?.[name]?.last_run">{{ formatRelative(health.periodic[name].last_run, health.periodic[name].age_seconds) }}</span>
                <span v-else>—</span>
              </div>
              <div v-if="health.periodic?.[name]?.last_error" class="text-error text-caption mt-1">
                {{ health.periodic[name].last_error }}
              </div>
              <div v-if="health.periodic?.[name]?.data" class="text-caption mt-1">
                <div v-for="row in periodicSummary(name)" :key="row.label">
                  <span class="text-medium-emphasis">{{ row.label }}:</span>
                  <span> {{ row.value }}</span>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title class="text-h6">Settings</v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-1">DOWNLOAD_JOB_TTL_HOURS</div>
            <div class="mb-2">{{ health.settings?.DOWNLOAD_JOB_TTL_HOURS ?? '—' }}</div>
            <div class="text-caption text-medium-emphasis mb-1">DATA_DIRECTORY</div>
            <div class="mb-2"><code>{{ health.settings?.DATA_DIRECTORY || '—' }}</code></div>
            <div class="text-caption text-medium-emphasis mb-1">Watcher</div>
            <div class="mb-2">
              debounce={{ health.settings?.WATCH_DEBOUNCE_SECONDS || '—' }},
              created_delay={{ health.settings?.WATCH_CREATED_DELAY_SECONDS || '—' }},
              stability={{ health.settings?.WATCH_STABILITY_SECONDS || '—' }}
            </div>
            <div class="text-caption text-medium-emphasis mb-1">SIMBAD_MIN_INTERVAL</div>
            <div class="mb-2">{{ health.settings?.SIMBAD_MIN_INTERVAL || '—' }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-card class="mt-4">
      <v-card-title class="text-h6">System</v-card-title>
      <v-card-text>
        <div v-if="health.system">
          <div class="mb-2">
            <div class="text-caption text-medium-emphasis mb-1">CPU</div>
            <div>{{ health.system.cpu_percent }}%</div>
          </div>
          <div>
            <div class="text-caption text-medium-emphasis mb-1">Memory</div>
            <div class="text-caption text-medium-emphasis">
              {{ humanBytes(health.system.memory.used_bytes) }} / {{ humanBytes(health.system.memory.total_bytes) }} ({{ health.system.memory.percent }}%)
            </div>
          </div>
              <div class="mt-2" v-if="health.system.disk">
                <div class="text-caption text-medium-emphasis mb-1">Disk<span v-if="health.system.disk.path"> ({{ health.system.disk.path }})</span></div>
                <div class="text-caption text-medium-emphasis">
                  {{ humanBytes(health.system.disk.used_bytes) }} / {{ humanBytes(health.system.disk.total_bytes) }} ({{ health.system.disk.percent }}%)
                </div>
              </div>
        </div>
        <div v-else class="text-medium-emphasis text-caption">
          psutil not available
        </div>
      </v-card-text>
    </v-card>
  </v-container>
  </template>

  <script setup>
  import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
  import { api } from '@/services/api'
  import { useNotifyStore } from '@/store/notify'
  import { useAuthStore } from '@/store/auth'
  
  const loading = ref(false)
  const health = ref({})
  const notify = useNotifyStore()
  const auth = useAuthStore()
  const canView = computed(() => auth.isAdmin || auth.hasPerm('users.acl_system_health_view') || auth.hasPerm('acl_system_health_view'))
  const autoRefresh = ref(true)
  const refreshSeconds = 10
  let intervalId = null

  const jobStatuses = ['queued','running','done','failed','cancelled','expired']
  const jobColor = (s) => {
    switch (s) {
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
    const units = ['B','KB','MB','GB','TB','PB']
    let i = 0
    let v = n
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024
      i++
    }
    return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
  }

  const taskStatusColor = (item) => {
    if (!item) return 'secondary'
    if (item.last_error) return 'error'
    if (item.last_run) return 'success'
    return 'secondary'
  }
  const taskStatusLabel = (item) => {
    if (!item) return '—'
    if (item.last_error) return 'ERROR'
    if (item.last_run) return 'OK'
    return '—'
  }
  const periodicSummary = (name) => {
    const d = (health.value?.periodic?.[name]?.data) || {}
    if (name === 'cleanup_expired_downloads') {
      return [
        { label: 'checked', value: d.checked ?? 0 },
        { label: 'cleaned', value: d.cleaned ?? 0 },
        { label: 'freed', value: humanBytes(d.freed_bytes || 0) },
      ]
    }
    if (name === 'reconcile_filesystem') {
      return [
        { label: 'updated', value: d.updated ?? 0 },
        { label: 'files_checked', value: d.files_checked ?? 0 },
        { label: 'already_ok', value: d.already_ok ?? 0 },
        { label: 'prefix_rewrites', value: d.prefix_rewrites ?? 0 },
        { label: 'hash_recoveries', value: d.hash_recoveries ?? 0 },
        { label: 'ambiguous', value: d.ambiguous_matches ?? 0 },
        { label: 'failures', value: d.recovery_failures ?? 0 },
        { label: 'runs_missing', value: d.runs_missing ?? 0 },
        { label: 'mode', value: d.dry_run ? 'dry' : 'apply' },
      ]
    }
    if (name === 'scan_missing_filesystem') {
      return [
        { label: 'added', value: d.added ?? 0 },
        { label: 'checked', value: d.checked ?? 0 },
        { label: 'skipped_known', value: d.skipped_known ?? 0 },
        { label: 'skipped_unknown_type', value: d.skipped_unknown_type ?? 0 },
        { label: 'runs_seen', value: d.runs_seen ?? 0 },
        { label: 'runs_created', value: d.runs_created ?? 0 },
        { label: 'mode', value: d.dry_run ? 'dry' : 'apply' },
      ]
    }
    if (name === 'cleanup_orphan_objects') {
      return [
        { label: 'objects_checked', value: d.objects_checked ?? 0 },
        { label: 'orphans_found', value: d.orphans_found ?? 0 },
        { label: 'orphans_deleted', value: d.orphans_deleted ?? 0 },
        { label: 'first_hjd_updated', value: d.first_hjd_updated ?? 0 },
        { label: 'run_links_cleaned', value: d.observation_run_cleaned ?? 0 },
        { label: 'mode', value: d.dry_run ? 'dry' : 'apply' },
      ]
    }
    // Default generic renderer
    return Object.keys(d).map(k => ({ label: k, value: String(d[k]) }))
  }

  const fetchHealth = async () => {
    loading.value = true
    if (!canView.value) {
      loading.value = false
      return
    }
    try {
      health.value = await api.adminHealth()
    } catch (e) {
      try { notify.error('Failed to load system health') } catch {}
    } finally {
      loading.value = false
    }
  }

  const formatRelative = (iso, ageSec) => {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      const diff = typeof ageSec === 'number' ? ageSec : Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
      if (diff < 60) return `${diff}s ago`
      const m = Math.floor(diff / 60)
      if (m < 60) return `${m}m ago`
      const h = Math.floor(m / 60)
      if (h < 24) return `${h}h ago`
      const days = Math.floor(h / 24)
      return `${days}d ago`
    } catch { return iso }
  }

  const schedule = () => {
    clear()
    if (autoRefresh.value) {
      intervalId = setInterval(() => {
        fetchHealth()
      }, refreshSeconds * 1000)
    }
  }
  const clear = () => {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  onMounted(() => {
    fetchHealth()
    schedule()
  })
  onBeforeUnmount(() => {
    clear()
  })
  </script>

  <style scoped>
  </style>


