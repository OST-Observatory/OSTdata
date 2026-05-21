<template>
  <v-container class="py-4 admin-page">
    <header class="d-flex align-center justify-space-between flex-wrap mb-4 health-header" style="gap: 12px">
      <div>
        <h1 class="text-h4 mb-1">System Health</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          API, database, Celery, storage, and background task diagnostics.
        </p>
      </div>
      <div class="d-flex align-center flex-wrap health-toolbar" style="gap: 12px">
        <v-chip
          v-if="canView"
          :color="overallStatus.color"
          variant="tonal"
          size="small"
          prepend-icon="mdi-heart-pulse"
        >
          {{ overallStatus.label }}
        </v-chip>
        <v-switch
          v-model="autoRefresh"
          color="primary"
          hide-details
          inset
          density="comfortable"
          :label="`Auto ${refreshSeconds}s`"
          @update:model-value="schedule"
        />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="loading"
          :disabled="!canView"
          @click="fetchHealth"
        >
          Refresh
        </v-btn>
        <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ path: '/admin' }">
          Admin
        </v-btn>
      </div>
    </header>

    <v-alert v-if="!canView" type="warning" variant="tonal" class="mb-4">
      You don't have permission to view system health.
    </v-alert>

    <template v-else>
      <v-skeleton-loader v-if="loading && !healthLoaded" type="article, paragraph@2" class="mb-6" />

      <template v-else>
        <!-- Services: dense grid inside one panel -->
        <v-card variant="outlined" class="admin-health-card mb-3">
          <v-card-title class="health-section-title text-subtitle-2">
            <v-icon icon="mdi-server-network" size="18" class="mr-1" />
            Services
          </v-card-title>
          <v-card-text class="health-section-body">
            <div class="health-service-grid">
              <div
                v-for="card in serviceCards"
                :key="card.key"
                class="health-service-cell"
              >
                <div class="health-service-head">
                  <v-icon :icon="card.icon" :color="card.avatarColor" size="18" />
                  <span class="text-body-2 font-weight-medium">{{ card.title }}</span>
                  <v-chip :color="card.statusColor" size="x-small" variant="flat" class="ml-auto">
                    {{ card.statusLabel }}
                  </v-chip>
                  <span v-if="card.hint" class="text-caption text-medium-emphasis">{{ card.hint }}</span>
                </div>
                <dl v-if="card.rows.length" class="health-kv">
                  <template v-for="(row, idx) in card.rows" :key="idx">
                    <dt>{{ row.label }}</dt>
                    <dd>{{ row.value }}</dd>
                  </template>
                </dl>
                <div v-if="card.error" class="text-error text-caption mt-1">{{ card.error }}</div>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <v-row dense class="mb-3">
          <v-col cols="12" md="8">
            <v-card variant="outlined" class="admin-health-card h-100">
              <v-card-title class="health-section-title text-subtitle-2">
                <v-icon icon="mdi-clock-outline" size="18" class="mr-1" />
                Periodic tasks
              </v-card-title>
              <v-card-text class="health-section-body pt-0">
                <v-table density="compact" class="health-periodic-table bg-transparent">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Status</th>
                      <th>Last run</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="name in periodicTaskNames" :key="name">
                      <td class="text-caption font-weight-medium">{{ name }}</td>
                      <td>
                        <v-chip
                          size="x-small"
                          :color="taskStatusColor(health.periodic?.[name])"
                          variant="flat"
                        >
                          {{ taskStatusLabel(health.periodic?.[name]) }}
                        </v-chip>
                      </td>
                      <td class="text-caption text-medium-emphasis">
                        <span v-if="health.periodic?.[name]?.last_run">
                          {{ formatRelative(health.periodic[name].last_run, health.periodic[name].age_seconds) }}
                        </span>
                        <span v-else>—</span>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
                <v-expansion-panels
                  v-if="periodicWithDetails.length"
                  variant="accordion"
                  density="compact"
                  class="mt-2"
                >
                  <v-expansion-panel
                    v-for="name in periodicWithDetails"
                    :key="name"
                    :title="name"
                    class="text-caption"
                  >
                    <v-expansion-panel-text class="py-2">
                      <div v-if="health.periodic?.[name]?.last_error" class="text-error text-caption mb-1">
                        {{ health.periodic[name].last_error }}
                      </div>
                      <dl class="health-kv health-kv--dense">
                        <template v-for="row in periodicSummary(name)" :key="row.label">
                          <dt>{{ row.label }}</dt>
                          <dd>{{ row.value }}</dd>
                        </template>
                      </dl>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="4">
            <v-card variant="outlined" class="admin-health-card mb-3">
              <v-card-title class="health-section-title text-subtitle-2">
                <v-icon icon="mdi-download-network-outline" size="18" class="mr-1" />
                Download jobs
              </v-card-title>
              <v-card-text class="health-section-body">
                <div class="health-jobs-inline">
                  <div v-for="s in jobStatuses" :key="s" class="health-job-pill">
                    <v-chip :color="jobColor(s)" size="x-small" variant="tonal">{{ s }}</v-chip>
                    <span class="text-body-2 font-weight-medium tabular-nums">{{ health.jobs?.[s] ?? 0 }}</span>
                  </div>
                </div>
              </v-card-text>
            </v-card>

            <v-card variant="outlined" class="admin-health-card admin-health-card--featured">
              <v-card-title class="health-section-title text-subtitle-2">
                <v-icon icon="mdi-tune" size="18" class="mr-1" />
                Config & host
              </v-card-title>
              <v-card-text class="health-section-body">
                <dl class="health-kv health-kv--dense">
                  <template v-for="row in settingsRows" :key="row.label">
                    <dt>{{ row.label }}</dt>
                    <dd>{{ row.value }}</dd>
                  </template>
                  <template v-if="health.system">
                    <dt>CPU</dt>
                    <dd>{{ health.system.cpu_percent }}%</dd>
                    <dt>Memory</dt>
                    <dd>
                      {{ humanBytes(health.system.memory.used_bytes) }} /
                      {{ humanBytes(health.system.memory.total_bytes) }}
                      ({{ health.system.memory.percent }}%)
                    </dd>
                    <template v-if="health.system.disk">
                      <dt>Disk</dt>
                      <dd>
                        {{ humanBytes(health.system.disk.used_bytes) }} /
                        {{ humanBytes(health.system.disk.total_bytes) }}
                        ({{ health.system.disk.percent }}%)
                      </dd>
                    </template>
                  </template>
                  <template v-else>
                    <dt>Host metrics</dt>
                    <dd class="text-medium-emphasis">psutil not available</dd>
                  </template>
                </dl>
                <div class="health-versions mt-2 pt-2">
                  <span
                    v-for="v in versionRows"
                    :key="v.label"
                    class="health-version-pill text-caption"
                  >
                    <span class="text-medium-emphasis">{{ v.label }}</span>
                    {{ v.value }}
                  </span>
                </div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </template>
    </template>
  </v-container>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { useAuthStore } from '@/store/auth'

const loading = ref(false)
const health = ref({})
const notify = useNotifyStore()
const auth = useAuthStore()
const canView = computed(
  () => auth.hasPerm('users.acl_system_health_view') || auth.hasPerm('acl_system_health_view'),
)
const autoRefresh = ref(true)
const refreshSeconds = 10
let intervalId = null

const healthLoaded = computed(() => Object.keys(health.value || {}).length > 0)

const jobStatuses = ['queued', 'running', 'done', 'failed', 'cancelled', 'expired']

const periodicTaskNames = [
  'cleanup_expired_downloads',
  'reconcile_filesystem',
  'cleanup_orphans_hashcheck',
  'scan_missing_filesystem',
  'cleanup_orphan_objects',
  'unlink_non_light_datafiles',
  'plate_solve_pending_files',
  're_evaluate_plate_solved_files',
]

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
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function triStateOk(value) {
  if (value === true) return { statusColor: 'success', statusLabel: 'OK' }
  if (value === false) return { statusColor: 'error', statusLabel: 'ERROR' }
  return { statusColor: 'secondary', statusLabel: 'UNKNOWN' }
}

function boolOk(value, trueLabel = 'OK', falseLabel = 'ERROR') {
  if (value === true) return { statusColor: 'success', statusLabel: trueLabel }
  if (value === false) return { statusColor: 'error', statusLabel: falseLabel }
  return { statusColor: 'secondary', statusLabel: '—' }
}

const overallStatus = computed(() => {
  if (loading.value && !healthLoaded.value) {
    return { color: 'secondary', label: 'Loading…' }
  }
  const h = health.value
  const checks = [
    h.database?.ok,
    h.storage?.ok,
    h.celery?.workers_alive,
    h.redis?.ok,
  ]
  if (checks.some((v) => v === false)) {
    return { color: 'error', label: 'Issues detected' }
  }
  if (checks.some((v) => v !== true)) {
    return { color: 'warning', label: 'Partially unknown' }
  }
  return { color: 'success', label: 'All core checks OK' }
})

function latencyHint(ms) {
  if (ms == null) return ''
  return `${ms}ms`
}

const versionRows = computed(() => {
  const v = health.value.versions || {}
  return [
    { label: 'Python', value: v.python || '—' },
    { label: 'Django', value: v.django || '—' },
    { label: 'Bokeh', value: v.bokeh ?? '—' },
  ]
})

const serviceCards = computed(() => {
  const h = health.value
  const aladin = triStateOk(h.aladin?.ok)
  const ldapConfigured = h.ldap?.configured
  const ldapBind = ldapConfigured
    ? boolOk(h.ldap?.bind_ok, 'OK', 'Failed')
    : { color: 'secondary', label: 'N/A' }

  return [
    {
      key: 'database',
      title: 'Database',
      icon: 'mdi-database',
      avatarColor: 'blue',
      ...boolOk(h.database?.ok),
      hint: latencyHint(h.database?.latency_ms),
      rows: [
        { label: 'Latency', value: h.database?.latency_ms != null ? `${h.database.latency_ms} ms` : '—' },
      ],
      error: h.db_error,
    },
    {
      key: 'aladin',
      title: 'Aladin',
      icon: 'mdi-telescope',
      avatarColor: 'purple',
      statusColor: aladin.statusColor,
      statusLabel: aladin.statusLabel,
      hint: latencyHint(h.aladin?.latency_ms),
      rows: [
        { label: 'HTTP status', value: h.aladin?.status_code ?? '—' },
      ],
      error: h.aladin?.error,
    },
    {
      key: 'redis',
      title: 'Redis broker',
      icon: 'mdi-memory',
      avatarColor: 'red',
      ...triStateOk(h.redis?.ok),
      hint: latencyHint(h.redis?.latency_ms),
      rows: [
        { label: 'Broker URL', value: h.celery?.broker_url || '—' },
      ],
      error: h.redis_error,
    },
    {
      key: 'celery',
      title: 'Celery workers',
      icon: 'mdi-cog-sync',
      avatarColor: 'deep-orange',
      ...boolOk(h.celery?.workers_alive, 'ALIVE', 'NO RESPONSE'),
      hint: '',
      rows: [
        { label: 'Workers', value: Array.isArray(h.celery?.workers) && h.celery.workers.length ? h.celery.workers.join(', ') : '—' },
        {
          label: 'Eager mode',
          value: h.celery?.task_always_eager ? 'ENABLED (disable for prod)' : 'Disabled',
        },
      ],
      error: h.celery_ping_error,
    },
    {
      key: 'storage',
      title: 'Data storage',
      icon: 'mdi-harddisk',
      avatarColor: 'brown',
      ...boolOk(h.storage?.ok),
      hint: h.storage?.exists === false ? 'path missing' : '',
      rows: [
        { label: 'Path', value: h.storage?.path || '—' },
        {
          label: 'Disk usage',
          value: h.storage?.total_bytes != null
            ? `${humanBytes(h.storage.used_bytes)} / ${humanBytes(h.storage.total_bytes)} free ${humanBytes(h.storage.free_bytes)}`
            : '—',
        },
      ],
      error: h.storage?.error,
    },
    {
      key: 'ldap',
      title: 'LDAP',
      icon: 'mdi-account-key',
      avatarColor: 'cyan',
      statusColor: ldapBind.color,
      statusLabel: ldapConfigured ? ldapBind.label : 'Not configured',
      hint: '',
      rows: ldapConfigured
        ? [
            { label: 'Server', value: h.ldap?.server_uri || '—' },
            { label: 'Module', value: h.ldap?.can_import ? 'Available' : 'Missing' },
          ]
        : [{ label: 'Status', value: 'LDAP integration disabled' }],
      error: [h.ldap?.bind_error, h.ldap?.tls_error, h.ldap?.connect_error].filter(Boolean).join(' · '),
    },
  ]
})

const settingsRows = computed(() => {
  const s = health.value.settings || {}
  return [
    { label: 'DOWNLOAD_JOB_TTL_HOURS', value: s.DOWNLOAD_JOB_TTL_HOURS ?? '—' },
    { label: 'DATA_DIRECTORY', value: s.DATA_DIRECTORY || '—' },
    {
      label: 'File watcher',
      value: `debounce ${s.WATCH_DEBOUNCE_SECONDS || '—'}s · delay ${s.WATCH_CREATED_DELAY_SECONDS || '—'}s · stability ${s.WATCH_STABILITY_SECONDS || '—'}s`,
    },
    { label: 'SIMBAD_MIN_INTERVAL', value: s.SIMBAD_MIN_INTERVAL || '—' },
  ]
})

const periodicWithDetails = computed(() =>
  periodicTaskNames.filter((name) => {
    const item = health.value?.periodic?.[name]
    return item?.data && Object.keys(item.data).length > 0
  }),
)

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
  const d = health.value?.periodic?.[name]?.data || {}
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
  if (name === 'unlink_non_light_datafiles') {
    return [
      { label: 'files_found', value: d.files_found ?? 0 },
      { label: 'unlinks_done', value: d.unlinks_done ?? 0 },
      { label: 'objects_updated', value: d.objects_updated ?? 0 },
      { label: 'runs_updated', value: d.runs_updated ?? 0 },
      { label: 'mode', value: d.dry_run ? 'dry' : 'apply' },
    ]
  }
  return Object.keys(d).map((k) => ({ label: k, value: String(d[k]) }))
}

const fetchHealth = async () => {
  loading.value = true
  if (!canView.value) {
    loading.value = false
    return
  }
  try {
    health.value = await api.adminHealth()
  } catch {
    try {
      notify.error('Failed to load system health')
    } catch {
      /* ignore */
    }
  } finally {
    loading.value = false
  }
}

const formatRelative = (iso, ageSec) => {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const diff = typeof ageSec === 'number'
      ? ageSec
      : Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
    if (diff < 60) return `${diff}s ago`
    const m = Math.floor(diff / 60)
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    const days = Math.floor(h / 24)
    return `${days}d ago`
  } catch {
    return iso
  }
}

const stopRefresh = () => {
  if (intervalId) {
    window.clearInterval(intervalId)
    intervalId = null
  }
}

const schedule = () => {
  stopRefresh()
  if (autoRefresh.value) {
    intervalId = window.setInterval(() => {
      fetchHealth()
    }, refreshSeconds * 1000)
  }
}

watch(autoRefresh, () => {
  schedule()
})

onMounted(() => {
  fetchHealth()
  schedule()
})

onBeforeUnmount(() => {
  stopRefresh()
})
</script>

<style scoped>
.admin-page {
  max-width: 1280px;
}

.admin-health-card {
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.admin-health-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.35);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.admin-health-card--featured {
  border-width: 2px;
  border-color: rgba(var(--v-theme-primary), 0.35);
  background: linear-gradient(
    145deg,
    rgba(var(--v-theme-primary), 0.06) 0%,
    rgba(var(--v-theme-surface), 1) 55%
  );
}

.health-section-title {
  padding: 10px 14px 4px;
  min-height: unset;
  line-height: 1.3;
}

.health-section-body {
  padding: 6px 14px 12px;
}

.health-service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.health-service-cell {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.health-service-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin-bottom: 4px;
}

.health-service-head .ml-auto {
  margin-left: auto;
}

.health-kv {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 10px;
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.35;
}

.health-kv dt {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 400;
}

.health-kv dd {
  margin: 0;
  word-break: break-word;
}

.health-kv--dense {
  gap: 1px 8px;
  font-size: 0.75rem;
}

.health-jobs-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.health-job-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.health-versions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.health-version-pill {
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  white-space: nowrap;
}

.health-periodic-table :deep(th),
.health-periodic-table :deep(td) {
  padding: 4px 8px !important;
  height: auto !important;
  font-size: 0.8125rem;
}

.health-periodic-table :deep(th) {
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 600;
}

.admin-health-card :deep(.v-expansion-panel-title) {
  min-height: 36px;
  padding: 8px 12px;
  font-size: 0.8125rem;
}

.admin-health-card :deep(.v-expansion-panel-text__wrapper) {
  padding: 8px 12px 10px;
}
</style>
