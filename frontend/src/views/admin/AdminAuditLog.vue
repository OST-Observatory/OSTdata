<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap" style="gap: 12px">
      <div>
        <h1 class="text-h5 mb-1">Admin · Audit log</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          Last {{ maxEntries }} changes across objects, runs, data files, identifiers, and tags.
        </p>
      </div>
      <v-btn
        color="primary"
        variant="outlined"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="fetchLog"
      >
        Refresh
      </v-btn>
    </div>

    <v-alert v-if="!canView" type="warning" variant="tonal" class="mb-4">
      You don't have permission to view the audit log.
    </v-alert>

    <template v-else>
      <v-card class="mb-4">
        <v-card-text>
          <v-row class="align-center">
            <v-col cols="12" sm="6" md="4">
              <v-text-field
                v-model="filterSearch"
                label="Search"
                placeholder="Entity, user, reason, fields…"
                prepend-inner-icon="mdi-magnify"
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-select
                v-model="filterModelType"
                :items="modelTypeOptions"
                label="Entity type"
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="filterAction"
                :items="actionOptions"
                label="Action"
                hide-details
                density="comfortable"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-select
                v-model="filterDays"
                :items="daysOptions"
                label="Time range"
                hide-details
                density="comfortable"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-switch
                v-model="filterUserOnly"
                label="User changes only"
                color="primary"
                hide-details
                density="comfortable"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-switch
                v-model="filterHideSystemDatafiles"
                label="Hide automated data file updates"
                color="primary"
                hide-details
                density="comfortable"
              />
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-switch
                v-model="filterHideOverrideFields"
                label="Hide override-only changes"
                color="primary"
                hide-details
                density="comfortable"
              />
            </v-col>
            <v-col v-if="filterHideOverrideFields" cols="12">
              <v-alert type="info" variant="tonal" density="compact" class="mb-0">
                This filter compares up to {{ maxEntries }} history entries to detect real field
                changes. Loading can take several seconds.
                <span v-if="slowOverrideLoad"> (last request: {{ lastLoadSeconds }}s)</span>
              </v-alert>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-switch
                v-model="filterGroupBatches"
                label="Group automated data file batches"
                color="primary"
                hide-details
                density="comfortable"
              />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-card>
        <v-card-text>
          <v-data-table
            v-model:expanded="expanded"
            :headers="headers"
            :items="entries"
            :loading="loading"
            item-value="id"
            show-expand
            density="comfortable"
            class="audit-log-table"
          >
            <template #item.timestamp="{ item }">
              <span class="text-no-wrap">{{ formatTimestamp(row(item).timestamp) }}</span>
            </template>

            <template #item.model_label="{ item }">
              <v-chip size="small" variant="tonal" :color="modelColor(row(item).model_type)">
                {{ row(item).model_label }}
              </v-chip>
            </template>

            <template #item.entity_label="{ item }">
              <router-link
                v-if="row(item).entity_path && !row(item).is_batch"
                :to="row(item).entity_path"
                class="text-primary text-decoration-none"
              >
                {{ row(item).entity_label }}
              </router-link>
              <span v-else>{{ row(item).entity_label }}</span>
              <v-chip
                v-if="row(item).is_batch"
                size="x-small"
                class="ml-2"
                color="info"
                variant="tonal"
              >
                batch
              </v-chip>
            </template>

            <template #item.action="{ item }">
              <v-chip size="small" :color="actionColor(row(item).action)" variant="flat">
                {{ row(item).action }}
              </v-chip>
            </template>

            <template #item.user_display="{ item }">
              <span :class="{ 'text-medium-emphasis': row(item).user_display === 'System' }">
                {{ row(item).user_display }}
              </span>
            </template>

            <template #item.changes_summary="{ item }">
              <span class="text-body-2">{{ changesSummary(row(item)) }}</span>
            </template>

            <template #expanded-row="{ columns, item }">
              <tr>
                <td :colspan="columns.length" class="pa-4 bg-grey-lighten-5">
                  <div v-if="row(item).change_reason" class="mb-3">
                    <div class="text-caption text-medium-emphasis mb-1">Context</div>
                    <v-chip size="small" variant="outlined" color="secondary" class="font-mono-chip">
                      {{ row(item).change_reason }}
                    </v-chip>
                  </div>

                  <div class="text-caption text-medium-emphasis mb-2">Field changes</div>
                  <div
                    v-if="row(item).action === 'updated' && !row(item).has_field_changes"
                    class="text-body-2 text-medium-emphasis"
                  >
                    No field changes detected (history entry without a diff).
                  </div>
                  <v-table
                    v-else-if="row(item).changes?.length"
                    density="compact"
                    class="bg-transparent audit-changes-table"
                  >
                    <thead>
                      <tr>
                        <th class="text-left" style="width: 22%">Field</th>
                        <th class="text-left" style="width: 39%">Old</th>
                        <th class="text-left" style="width: 39%">New</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(ch, idx) in row(item).changes" :key="idx">
                        <td><code>{{ formatField(ch.field) }}</code></td>
                        <td class="text-medium-emphasis audit-cell-value">{{ formatValue(ch.old) }}</td>
                        <td class="audit-cell-value">{{ formatValue(ch.new) }}</td>
                      </tr>
                    </tbody>
                  </v-table>
                  <div v-else class="text-body-2 text-medium-emphasis">—</div>
                </td>
              </tr>
            </template>

            <template #bottom>
              <div class="d-flex align-center justify-space-between flex-wrap pa-4" style="gap: 12px">
                <span class="text-caption text-medium-emphasis">
                  {{ totalCount }} entries (max {{ maxEntries }})
                </span>
                <v-pagination
                  v-model="page"
                  :length="pageCount"
                  :total-visible="7"
                  density="comfortable"
                  @update:model-value="fetchLog"
                />
              </div>
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

let searchDebounceTimer = null
import { api } from '@/services/api'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const canView = computed(
  () => auth.hasPerm('users.acl_admin_audit_log_view') || auth.hasPerm('acl_admin_audit_log_view'),
)

const loading = ref(false)
const entries = ref([])
const totalCount = ref(0)
const maxEntries = ref(1000)
const page = ref(1)
const pageSize = ref(25)
const expanded = ref([])
const filterSearch = ref('')
const filterModelType = ref('')
const filterAction = ref('')
const filterDays = ref('')
const filterUserOnly = ref(false)
const filterHideSystemDatafiles = ref(true)
const filterHideOverrideFields = ref(false)
const filterGroupBatches = ref(true)
const slowOverrideLoad = ref(false)
const lastLoadSeconds = ref(null)

const modelTypeOptions = [
  { title: 'All types', value: '' },
  { title: 'Object', value: 'object' },
  { title: 'Identifier', value: 'identifier' },
  { title: 'Observation run', value: 'observation_run' },
  { title: 'Data file', value: 'datafile' },
  { title: 'Tag', value: 'tag' },
  { title: 'ACL', value: 'acl' },
  { title: 'Banner', value: 'banner' },
  { title: 'Download job', value: 'download_job' },
  { title: 'Solar image', value: 'solar_image' },
  { title: 'Tag assignment', value: 'tag_assignment' },
  { title: 'User roles', value: 'user_role' },
]

const actionOptions = [
  { title: 'All actions', value: '' },
  { title: 'Created', value: 'created' },
  { title: 'Updated', value: 'updated' },
  { title: 'Deleted', value: 'deleted' },
  { title: 'Done', value: 'done' },
  { title: 'Failed', value: 'failed' },
]

const daysOptions = [
  { title: 'All time', value: '' },
  { title: 'Last 7 days', value: 7 },
  { title: 'Last 30 days', value: 30 },
  { title: 'Last 90 days', value: 90 },
]

const pageCount = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize.value)))

const headers = [
  { title: 'When', key: 'timestamp', sortable: false, width: '170px' },
  { title: 'Type', key: 'model_label', sortable: false, width: '140px' },
  { title: 'Entity', key: 'entity_label', sortable: false },
  { title: 'Action', key: 'action', sortable: false, width: '110px' },
  { title: 'User', key: 'user_display', sortable: false, width: '140px' },
  { title: 'Changes', key: 'changes_summary', sortable: false },
]

function row(item) {
  return item?.raw ?? item
}

function modelColor(modelType) {
  const map = {
    object: 'deep-purple',
    identifier: 'purple',
    observation_run: 'teal',
    datafile: 'blue-grey',
    tag: 'orange',
    acl: 'red',
    banner: 'amber',
    download_job: 'cyan',
    solar_image: 'indigo',
    tag_assignment: 'orange-darken-2',
    user_role: 'pink',
  }
  return map[modelType] || 'secondary'
}

function actionColor(action) {
  if (action === 'created') return 'success'
  if (action === 'deleted') return 'error'
  if (action === 'done') return 'success'
  if (action === 'failed') return 'error'
  return 'primary'
}

function formatTimestamp(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatField(field) {
  if (field === '__created__') return '(created)'
  if (field === '__deleted__') return '(deleted)'
  if (field === '__batch__') return '(batch)'
  return field
}

function formatValue(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  const s = String(val)
  return s.length > 200 ? `${s.slice(0, 197)}…` : s
}

function changesSummary(item) {
  if (item.is_batch && item.batch_count) {
    const reason = item.change_reason ? ` · ${formatReasonShort(item.change_reason)}` : ''
    return `${item.batch_count} files grouped${reason}`
  }
  if (item.change_reason) {
    const short = item.change_reason.length > 40
      ? `${item.change_reason.slice(0, 37)}…`
      : item.change_reason
    if (item.action === 'updated' && !item.has_field_changes) {
      return short
    }
  }
  const changes = item.changes || []
  if (item.action === 'updated' && !item.has_field_changes) {
    return 'No field changes detected'
  }
  if (!changes.length) return item.change_reason ? formatReasonShort(item.change_reason) : '—'
  if (changes[0].field === '__created__') return 'Record created'
  if (changes[0].field === '__deleted__') return 'Record deleted'
  const names = changes.map((c) => c.field).filter((f) => !f.startsWith('__'))
  if (!names.length) return formatReasonShort(item.change_reason) || '—'
  const fields = names.length <= 3 ? names.join(', ') : `${names.slice(0, 3).join(', ')} +${names.length - 3} more`
  if (item.change_reason) {
    return `${formatReasonShort(item.change_reason)} · ${fields}`
  }
  return fields
}

function formatReasonShort(reason) {
  if (!reason) return ''
  return reason.length > 36 ? `${reason.slice(0, 33)}…` : reason
}

function buildQueryParams() {
  const params = {
    page: page.value,
    page_size: pageSize.value,
    user_only: filterUserOnly.value,
    hide_system_datafiles: filterHideSystemDatafiles.value,
    hide_override_fields: filterHideOverrideFields.value,
    group_batches: filterGroupBatches.value,
  }
  if (filterModelType.value) {
    params.model_type = filterModelType.value
  }
  if (filterDays.value !== '' && filterDays.value != null) {
    params.days = filterDays.value
  }
  if (filterAction.value) {
    params.action = filterAction.value
  }
  const q = (filterSearch.value || '').trim()
  if (q) {
    params.search = q
  }
  return params
}

async function fetchLog() {
  if (!canView.value) return
  loading.value = true
  expanded.value = []
  const t0 = performance.now()
  try {
    const data = await api.adminAuditLog(buildQueryParams())
    entries.value = data.results || []
    totalCount.value = data.count ?? 0
    maxEntries.value = data.max_entries ?? 1000
    pageSize.value = data.page_size ?? pageSize.value
    const elapsed = (performance.now() - t0) / 1000
    lastLoadSeconds.value = elapsed.toFixed(1)
    slowOverrideLoad.value = filterHideOverrideFields.value && elapsed >= 2
  } catch (e) {
    console.error(e)
    entries.value = []
    totalCount.value = 0
    slowOverrideLoad.value = false
  } finally {
    loading.value = false
  }
}

watch(
  [
    filterModelType,
    filterAction,
    filterDays,
    filterUserOnly,
    filterHideSystemDatafiles,
    filterHideOverrideFields,
    filterGroupBatches,
  ],
  () => {
    page.value = 1
    fetchLog()
  },
)

watch(filterSearch, () => {
  page.value = 1
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    fetchLog()
  }, 400)
})

watch(canView, (ok) => {
  if (ok) fetchLog()
})

onMounted(() => {
  if (canView.value) fetchLog()
})
</script>

<style scoped>
.audit-changes-table :deep(td),
.audit-changes-table :deep(th) {
  vertical-align: top;
}

.audit-cell-value {
  word-break: break-word;
  white-space: pre-wrap;
  font-size: 0.8125rem;
}

.font-mono-chip :deep(.v-chip__content) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.75rem;
}
</style>
