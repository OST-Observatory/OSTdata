<template>
  <v-container fluid class="runs">
      <div class="d-flex align-center justify-space-between mb-4 header-bar">
        <h1 class="text-h4">Observation Runs</h1>
        <div class="d-flex align-center" style="gap: 8px">
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              color="primary"
              prepend-icon="mdi-eye"
              :disabled="!selected.length || !canPublish"
              :size="isMobile ? 'default' : undefined"
              @click="bulkPublish(true)"
            >
              <span class="btn-label">Publish ({{ selected.length }})</span>
            </v-btn>
            <v-tooltip v-if="!canPublish || !selected.length" activator="parent" location="top">
              {{ !selected.length ? 'Select runs first' : 'No permission' }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              color="secondary"
              prepend-icon="mdi-eye-off"
              :disabled="!selected.length || !canPublish"
              :size="isMobile ? 'default' : undefined"
              @click="bulkPublish(false)"
            >
              <span class="btn-label">Unpublish ({{ selected.length }})</span>
            </v-btn>
            <v-tooltip v-if="!canPublish || !selected.length" activator="parent" location="top">
              {{ !selected.length ? 'Select runs first' : 'No permission' }}
            </v-tooltip>
          </div>
        </div>
      </div>

      <!-- Filters -->
      <v-card class="mb-4">
        <v-card-text>
          <v-row>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="search"
                label="Search runs"
                prepend-inner-icon="mdi-magnify"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="4">
              <v-select
                v-model="selectedStatus"
                :items="statusItems"
                item-title="title"
                item-value="value"
                label="Status"
                prepend-inner-icon="mdi-filter"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              ></v-select>
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="objectFilter"
                label="Filter by object name"
                prepend-inner-icon="mdi-star"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              ></v-text-field>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12" sm="6">
              <v-select
                v-model="photometryFilter"
                :items="boolFilterItems"
                item-title="title"
                item-value="value"
                label="Photometry"
                prepend-inner-icon="mdi-weather-sunny"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              ></v-select>
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="spectroscopyFilter"
                :items="boolFilterItems"
                item-title="title"
                item-value="value"
                label="Spectroscopy"
                prepend-inner-icon="mdi-chart-bell-curve"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              ></v-select>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12">
              <v-btn
                variant="text"
                color="primary"
                prepend-icon="mdi-filter-remove"
                @click="resetFilters"
                block
              >
                Reset Filters
              </v-btn>
            </v-col>
            </v-row>
        </v-card-text>
      </v-card>

      <!-- Error state -->
      <v-alert v-if="error" type="error" variant="tonal" class="mb-3">{{ error }}</v-alert>

      <!-- Runs table -->
      <v-card>
        <v-data-table
          :headers="headers"
          :items="runs"
          :items-length="totalItems"
          :items-per-page="itemsPerPage === -1 ? totalItems : itemsPerPage"
          :loading="loading"
          :sort-by="tableSort"
          @update:sort-by="handleSort"
          hide-default-footer
          show-select
          select-strategy="page"
          return-object
          item-key="pk"
          item-value="pk"
          v-model="selected"
          v-model:selected="selected"
          v-model:selection="selected"
          @update:selected="onRunsSelected"
          @update:modelValue="onRunsSelected"
          @update:selection="onRunsSelected"
          @click="onRunsTableClick"
          class="custom-table"
        >
          <template #loading>
            <LoadingState type="table" />
          </template>

          <template #no-data>
            <EmptyState text="No runs found." />
          </template>
          <!-- Name column with link -->
          <template v-slot:item.name="{ item }">
            <v-tooltip :text="item.name" location="top">
              <template #activator="{ props }">
                <router-link v-bind="props" :to="`/observation-runs/${item.pk || item.id}`" class="text-decoration-none primary--text cell-truncate">
                  {{ item.name }}
                </router-link>
              </template>
            </v-tooltip>
          </template>

          <template v-slot:item.date="{ item }">
            {{ formatDateTime(item.start_time || item.date, { dateStyle: 'short' }) }}
          </template>

          <template v-slot:item.main_targets="{ item }">
            <div class="d-flex flex-wrap gap-1">
              <v-chip
                v-for="t in getMainTargets(item)"
                :key="t.name"
                size="x-small"
                variant="outlined"
                color="primary"
                class="mr-1"
                :to="t.href"
                link
              >
                {{ t.name }}
              </v-chip>
              <span v-if="getMainTargets(item).length === 0" class="text-secondary text-caption">—</span>
            </div>
          </template>

          <template v-slot:item.photometry="{ item }">
            <v-icon :color="getBool(item, ['photometry', 'has_photometry']) ? 'success' : 'disabled'">{{ getBool(item, ['photometry', 'has_photometry']) ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
          </template>

          <template v-slot:item.spectroscopy="{ item }">
            <v-icon :color="getBool(item, ['spectroscopy', 'has_spectroscopy']) ? 'success' : 'disabled'">{{ getBool(item, ['spectroscopy', 'has_spectroscopy']) ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
          </template>

          <template v-slot:item.n_light="{ item }">
            {{ getCount(item, ['n_light', 'n_lights', 'lights']) ?? '—' }}
          </template>

          <template v-slot:item.n_flat="{ item }">
            {{ getCount(item, ['n_flat', 'n_flats', 'flats']) ?? '—' }}
          </template>

          <template v-slot:item.n_dark="{ item }">
            {{ getCount(item, ['n_dark', 'n_darks', 'darks']) ?? '—' }}
          </template>
          <template v-slot:item.other="{ item }">
            {{ getOtherCount(item) }}
          </template>

          <template v-slot:item.tags="{ item }">
            <div class="d-flex flex-wrap gap-1">
              <v-chip
                v-for="tag in normalizeTags(item.tags)"
                :key="tag.name"
                :color="tag.color || 'primary'"
                size="x-small"
                variant="outlined"
              >
                {{ tag.name }}
              </v-chip>
              <span v-if="!item?.tags || normalizeTags(item.tags).length === 0" class="text-secondary text-caption">—</span>
            </div>
          </template>

          <template v-slot:item.status="{ item }">
            <v-chip :color="getStatusColor(item.status || item.reduction_status)" size="small">
              {{ item.status || item.reduction_status || 'n/a' }}
            </v-chip>
          </template>

          <template v-slot:item.actions="{ item }">
            <v-btn
              v-if="canEditRun"
              icon
              variant="text"
              color="primary"
              class="action-btn"
              @click="openRunEdit(item)"
              :aria-label="`Edit run ${item.name}`"
            >
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn
              v-if="canDeleteRun"
              icon
              variant="text"
              color="error"
              class="action-btn"
              @click="removeRun(item)"
              :aria-label="`Delete run ${item.name}`"
            >
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </template>
        </v-data-table>

        <!-- Custom pagination controls -->
        <v-card-actions class="d-flex align-center justify-space-between px-4 py-2 card-actions-responsive">
          <div class="d-flex align-center actions-left">
            <span class="text-body-2 mr-4">Items per page:</span>
            <v-select
              v-model="itemsPerPage"
              :items="[10, 25, 50, 100, -1]"
              :item-title="item => item === -1 ? 'All' : item.toString()"
              :item-value="item => item"
              density="compact"
              variant="outlined"
              hide-details
              class="items-per-page-select"
              style="width: 100px"
              @update:model-value="handleItemsPerPageChange"
              aria-label="Items per page"
            ></v-select>
          </div>

          <div class="d-flex align-center actions-right">
            <span class="text-body-2 mr-4">
              {{ paginationInfo }}
            </span>
            <v-btn
              icon="mdi-page-first"
              variant="text"
              :disabled="currentPage === 1"
              @click="handlePageChange(1)"
              class="mx-1 pagination-btn"
              aria-label="First page"
            ></v-btn>
            <v-btn
              icon="mdi-chevron-left"
              variant="text"
              :disabled="currentPage === 1"
              @click="handlePageChange(currentPage - 1)"
              class="mx-1 pagination-btn"
              aria-label="Previous page"
            ></v-btn>
            <v-btn
              icon="mdi-chevron-right"
              variant="text"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(currentPage + 1)"
              class="mx-1 pagination-btn"
              aria-label="Next page"
            ></v-btn>
            <v-btn
              icon="mdi-page-last"
              variant="text"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(totalPages)"
              class="mx-1 pagination-btn"
              aria-label="Last page"
            ></v-btn>
            <v-btn
              variant="text"
              color="primary"
              prepend-icon="mdi-content-copy"
              class="ml-2"
              @click="copyShareLink"
              aria-label="Copy link to current view"
            >
              Copy link
            </v-btn>
          </div>
        </v-card-actions>
      </v-card>
      <!-- Edit Run dialog -->
      <v-dialog v-model="runEditOpen" max-width="720">
        <v-card>
          <v-card-title class="text-h6">Edit Observation Run</v-card-title>
          <v-card-text>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6">
                <v-text-field v-model="runEditForm.name" label="Name" density="comfortable" variant="outlined" hide-details />
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="runEditForm.reduction_status"
                  :items="runStatusOptions"
                  item-title="title"
                  item-value="value"
                  label="Reduction status"
                  density="comfortable"
                  variant="outlined"
                  hide-details
                />
              </v-col>
            </v-row>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="4">
                <v-switch class="hi-contrast-switch" v-model="runEditForm.is_public" inset hide-details color="primary" :label="`Public`" />
              </v-col>
              <v-col cols="12" sm="4">
                <v-switch class="hi-contrast-switch" v-model="runEditForm.photometry" inset hide-details color="primary" :label="`Photometry`" />
              </v-col>
              <v-col cols="12" sm="4">
                <v-switch class="hi-contrast-switch" v-model="runEditForm.spectroscopy" inset hide-details color="primary" :label="`Spectroscopy`" />
              </v-col>
            </v-row>
            <v-row dense>
              <v-col cols="12">
                <v-textarea v-model="runEditForm.note" label="Note" rows="3" auto-grow density="comfortable" variant="outlined" hide-details />
              </v-col>
            </v-row>
            <v-row dense class="mt-2">
              <v-col cols="12" sm="7">
                <v-text-field
                  v-model="runEditDateInput"
                  label="Observation date/time (ISO, e.g. 2021-02-24T23:30:00Z)"
                  density="comfortable"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="5">
                <v-text-field
                  v-model.number="runEditJdInput"
                  label="Julian Date (e.g. 2459254.48)"
                  density="comfortable"
                  type="number"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="12">
                <v-btn variant="text" color="primary" @click="runEditRecomputeDate" :loading="runEditSaving">
                  Recompute date from files
                </v-btn>
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="runEditOpen = false">Cancel</v-btn>
            <v-btn color="primary" variant="elevated" @click="saveRunEdit" :loading="runEditSaving">Save</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { api } from '@/services/api'
import { formatDateTime } from '@/utils/datetime'
import { getStatusColor } from '@/utils/status'
import { useQuerySync } from '@/composables/useQuerySync'
import { useNotifyStore } from '@/store/notify'
import { useAuthStore } from '@/store/auth'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const runs = ref([])
const selected = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const sortKey = ref('-mid_observation_jd')
const search = ref('')
const objectFilter = ref('')
const selectedStatus = ref(null)
const photometryFilter = ref(null)
const spectroscopyFilter = ref(null)
const notify = useNotifyStore()
const authStore = useAuthStore()
const display = useDisplay()
const isMobile = computed(() => display.mdAndDown.value)
const canAdmin = computed(() => authStore.isAdmin)
const canEditRun = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_runs_edit') || authStore.hasPerm('acl_runs_edit'))
const canPublish = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_runs_publish') || authStore.hasPerm('acl_runs_publish'))
const canDeleteRun = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_runs_delete') || authStore.hasPerm('acl_runs_delete'))

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Date', key: 'date', sortable: true },
  { title: 'Main Targets', key: 'main_targets', sortable: false },
  { title: 'Photometry', key: 'photometry', sortable: false },
  { title: 'Spectroscopy', key: 'spectroscopy', sortable: false },
  { title: 'Lights', key: 'n_light', sortable: true },
  { title: 'Flats', key: 'n_flat', sortable: true },
  { title: 'Darks', key: 'n_dark', sortable: true },
  { title: 'Other', key: 'other', sortable: false },
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Status', key: 'status', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false },
]

const statusItems = [
  { title: 'Fully reduced', value: 'FR' },
  { title: 'Partly reduced', value: 'PR' },
  { title: 'Reduction error', value: 'ER' },
  { title: 'New', value: 'NE' },
]

const boolFilterItems = [
  { title: 'Not selected', value: null },
  { title: 'Yes', value: true },
  { title: 'No', value: false },
]

const totalPages = computed(() => {
  if (itemsPerPage.value === -1) return 1
  return Math.ceil(totalItems.value / itemsPerPage.value)
})

const paginationInfo = computed(() => {
  if (itemsPerPage.value === -1) return `Showing all ${totalItems.value} items`
  const start = (currentPage.value - 1) * itemsPerPage.value + 1
  const end = Math.min(currentPage.value * itemsPerPage.value, totalItems.value)
  return `${start}-${end} of ${totalItems.value}`
})

// Map backend sort key to table header key
const tableSort = computed(() => {
  const backend = sortKey.value || ''
  const order = backend.startsWith('-') ? 'desc' : 'asc'
  const field = backend.replace('-', '')
  const key = field === 'mid_observation_jd' ? 'date' : field
  return [{ key, order }]
})

const fetchRuns = async () => {
  try {
    loading.value = true
    error.value = null
    const params = {
      page: currentPage.value,
      limit: itemsPerPage.value === -1 ? 10000 : itemsPerPage.value,
      ordering: sortKey.value,
    }
    if (search.value) params.name = search.value
    if (selectedStatus.value) params.status = selectedStatus.value
    if (objectFilter.value) params.target = objectFilter.value
    if (photometryFilter.value !== null && photometryFilter.value !== undefined) params.photometry = photometryFilter.value
    if (spectroscopyFilter.value !== null && spectroscopyFilter.value !== undefined) params.spectroscopy = spectroscopyFilter.value

    const response = await api.getObservationRuns(params)
    // DRF pagination fallback
    if (response && Array.isArray(response.results)) {
      const serverItems = response.results
      const serverCount = typeof response.count === 'number' ? response.count : serverItems.length
      totalItems.value = serverCount
      // If server ignores requested page size (e.g., fixed 10), fetch a larger slice and paginate client-side
      const targetSize = itemsPerPage.value === -1 ? serverCount : itemsPerPage.value
      if (serverItems.length < Math.min(targetSize, serverCount)) {
        const bulkParams = {
          ordering: sortKey.value,
        }
        if (search.value) bulkParams.name = search.value
        if (selectedStatus.value) bulkParams.reduction_status = selectedStatus.value
        // Ask for a large page via both styles
        bulkParams.page = 1
        bulkParams.page_size = Math.max(1000, targetSize)
        bulkParams.limit = Math.max(1000, targetSize)
        const bulk = await api.getObservationRuns(bulkParams)
        const allRaw = Array.isArray(bulk.results) ? bulk.results : (Array.isArray(bulk.items) ? bulk.items : (Array.isArray(bulk) ? bulk : []))
        const all = allRaw.map(it => ({ ...it, pk: it.pk ?? it.id }))
        if (itemsPerPage.value === -1) {
          runs.value = all
        } else {
          const start = (currentPage.value - 1) * itemsPerPage.value
          runs.value = all.slice(start, start + itemsPerPage.value)
        }
      } else {
        runs.value = serverItems.map(it => ({ ...it, pk: it.pk ?? it.id }))
      }
    } else if (Array.isArray(response.items)) {
      runs.value = response.items.map(it => ({ ...it, pk: it.pk ?? it.id }))
      totalItems.value = response.total || response.items.length
    } else if (Array.isArray(response)) {
      runs.value = response.map(it => ({ ...it, pk: it.pk ?? it.id }))
      totalItems.value = response.length
    } else {
      runs.value = []
      totalItems.value = 0
    }
  } catch (e) {
    console.error('Error fetching runs:', e)
    error.value = 'Failed to load observation runs.'
    runs.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}
// Debounced sync for text inputs
import { debounce } from 'lodash'
const debouncedSyncRuns = debounce(() => {
  syncQueryAndFetch()
}, 300)

// Watchers: debounce for search/objectFilter; immediate for selects
watch(search, () => {
  currentPage.value = 1
  debouncedSyncRuns()
})
watch(objectFilter, () => {
  currentPage.value = 1
  debouncedSyncRuns()
})
watch([selectedStatus, photometryFilter, spectroscopyFilter], () => {
  currentPage.value = 1
  syncQueryAndFetch()
})

const handleSort = (newSortBy) => {
  if (newSortBy.length > 0) {
    const sort = newSortBy[0]
    const backendKey = sort.key === 'date' ? 'mid_observation_jd' : sort.key
    sortKey.value = `${sort.order === 'desc' ? '-' : ''}${backendKey}`
  } else {
    sortKey.value = 'mid_observation_jd'
  }
  syncQueryAndFetch()
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    syncQueryAndFetch()
  }
}

const handleItemsPerPageChange = () => {
  currentPage.value = 1
  syncQueryAndFetch()
}

const resetFilters = () => {
  search.value = ''
  objectFilter.value = ''
  selectedStatus.value = null
  photometryFilter.value = null
  spectroscopyFilter.value = null
  currentPage.value = 1
  sortKey.value = '-mid_observation_jd'
  syncQueryAndFetch()
}

const copyShareLink = async () => {
  try {
    await navigator.clipboard.writeText(window.location.href)
    notify.success('Link copied')
  } catch (e) {
    console.error('Copy link failed', e)
  }
}

const removeRun = async (item) => {
  if (!canDeleteRun.value || !(item?.pk || item?.id)) return
  const id = item.pk || item.id
  if (!confirm(`Delete observation run ${item.name}? This cannot be undone.`)) return
  try {
    await api.deleteObservationRun(id)
    notify.success('Run deleted')
    await fetchRuns()
  } catch (e) {
    console.error(e)
    notify.error('Delete failed')
  }
}

const bulkPublish = async (makePublic) => {
  if (!canPublish.value || !selected.value.length) return
  const ids = selected.value.map(x => x.pk || x.id).filter(Boolean)
  try {
    await Promise.all(ids.map(id => api.updateObservationRun(id, { is_public: !!makePublic })))
    notify.success(`${makePublic ? 'Published' : 'Unpublished'} ${ids.length} run(s)`) 
    selected.value = []
    await fetchRuns()
  } catch (e) {
    notify.error('Bulk update failed')
  }
}

// Edit run
const runEditOpen = ref(false)
const runEditSaving = ref(false)
const runEditForm = ref({
  pk: null,
  name: '',
  reduction_status: 'NE',
  is_public: true,
  photometry: false,
  spectroscopy: false,
  note: '',
})
const runEditDateInput = ref('')
const runEditJdInput = ref(null)
const runStatusOptions = [
  { title: 'New', value: 'NE' },
  { title: 'Partly reduced', value: 'PR' },
  { title: 'Fully reduced', value: 'FR' },
  { title: 'Reduction error', value: 'ER' },
]
const openRunEdit = (item) => {
  runEditForm.value = {
    pk: item.pk || item.id,
    name: item.name || '',
    reduction_status: item.reduction_status || 'NE',
    is_public: item.is_public ?? true,
    photometry: item.photometry ?? false,
    spectroscopy: item.spectroscopy ?? false,
    note: item.note || '',
  }
  runEditDateInput.value = ''
  runEditJdInput.value = null
  runEditOpen.value = true
}
const normalizeIso = (s) => {
  if (!s) return ''
  let x = String(s).trim()
  if (/^\d{4}-\d{2}-\d{2}\s/.test(x)) x = x.replace(' ', 'T')
  if (!/[zZ]|[+\-]\d{2}:\d{2}$/.test(x)) x = `${x}Z`
  return x
}
const saveRunEdit = async () => {
  const id = runEditForm.value.pk
  if (!id) { runEditOpen.value = false; return }
  runEditSaving.value = true
  try {
    const payload = {
      name: runEditForm.value.name,
      reduction_status: runEditForm.value.reduction_status,
      is_public: !!runEditForm.value.is_public,
      photometry: !!runEditForm.value.photometry,
      spectroscopy: !!runEditForm.value.spectroscopy,
      note: runEditForm.value.note || '',
    }
    await api.updateObservationRun(id, payload)
    // If date fields set, apply via admin endpoint
    const hasJd = runEditJdInput.value != null && runEditJdInput.value !== ''
    const hasIso = runEditDateInput.value && String(runEditDateInput.value).trim()
    if (hasJd || hasIso) {
      const datePayload = {}
      if (hasJd) datePayload.jd = Number(runEditJdInput.value)
      if (!hasJd && hasIso) datePayload.iso = normalizeIso(runEditDateInput.value)
      await api.adminSetRunDate(id, datePayload)
    }
    notify.success('Run updated')
    runEditOpen.value = false
    await fetchRuns()
  } catch (e) {
    notify.error('Update failed')
  } finally {
    runEditSaving.value = false
  }
}
const runEditRecomputeDate = async () => {
  const id = runEditForm.value.pk
  if (!id) return
  try {
    runEditSaving.value = true
    await api.adminRecomputeRunDate(id)
    notify.success('Observation date recomputed from files')
  } catch (e) {
    notify.error('Failed to recompute observation date')
  } finally {
    runEditSaving.value = false
  }
}

// (Date tools integrated into Edit dialog; standalone dialog removed)

const getMainTargets = (item) => {
  // prefer item.main_targets (array of names or objects), or build from nested objects
  if (Array.isArray(item?.main_targets)) {
    return item.main_targets
      .map(t => typeof t === 'string' ? { name: t, id: undefined } : { name: t?.name || String(t), id: t?.pk || t?.id })
      .map(t => ({ ...t, href: t.id ? `/objects/${t.id}` : undefined }))
      .filter(t => !!t.name)
  }
  // Fallback: some APIs include an objects array with flags
  if (Array.isArray(item?.objects)) {
    return item.objects
      .filter(o => o?.is_main)
      .map(o => ({ name: o?.name, id: o?.pk || o?.id, href: (o?.pk || o?.id) ? `/objects/${o.pk || o.id}` : undefined }))
      .filter(t => !!t.name)
  }
  return []
}

const getBool = (item, keys) => {
  for (const k of keys) {
    if (item?.[k] === true) return true
    if (item?.[k] === false) return false
  }
  return false
}

const getCount = (item, keys) => {
  for (const k of keys) {
    const v = item?.[k]
    if (typeof v === 'number') return v
    // Accept numeric strings (defensive for mixed backends)
    if (typeof v === 'string') {
      const s = v.trim()
      if (s !== '' && !Number.isNaN(Number(s))) return Number(s)
    }
  }
  return 0
}

const getOtherCount = (item) => {
  const total = getCount(item, ['n_datafiles', 'n_files', 'files', 'n_total'])
  const li = getCount(item, ['n_light', 'n_lights', 'lights'])
  const fl = getCount(item, ['n_flat', 'n_flats', 'flats'])
  const da = getCount(item, ['n_dark', 'n_darks', 'darks'])
  const other = total - (li + fl + da)
  return other >= 0 ? other : 0
}

const normalizeTags = (tags) => {
  if (!tags) return []
  if (Array.isArray(tags)) {
    return tags.map(t => {
      if (typeof t === 'string') return { name: t, color: undefined }
      return { name: t?.name || t?.label || String(t), color: t?.color }
    })
  }
  return []
}

const { applyQuery, syncQueryAndFetch } = useQuerySync(
  { page: currentPage, pageSize: itemsPerPage, q: search, object: objectFilter, status: selectedStatus, phot: photometryFilter, spec: spectroscopyFilter, sort: sortKey },
  [
    { key: 'page', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && n > 0 ? n : 1 }, toQuery: (v) => v, defaultValue: 1 },
    { key: 'pageSize', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && (n > 0 || n === -1) ? n : 10 }, toQuery: (v) => v, defaultValue: 10 },
    { key: 'q' },
    { key: 'object', toQuery: (v) => v || undefined, fromQuery: (v) => v || '' },
    { key: 'status' },
    { key: 'phot', toQuery: (v) => (v === true ? '1' : v === false ? '0' : undefined), fromQuery: (v) => (v === '1' ? true : v === '0' ? false : null) },
    { key: 'spec', toQuery: (v) => (v === true ? '1' : v === false ? '0' : undefined), fromQuery: (v) => (v === '1' ? true : v === '0' ? false : null) },
    { key: 'sort', defaultValue: '-mid_observation_jd' },
  ],
  fetchRuns
)

onMounted(() => {
  console.log('[Runs] component mounted')
  applyQuery()
  fetchRuns()
})

// Debug: observe selection changes
watch(selected, (val) => {
  try {
    console.log('[Runs] selected (watch):', Array.isArray(val) ? val.map(v => v?.pk || v?.id) : val)
  } catch (e) {}
}, { deep: true })

// Debug: listen to table's update event
const onRunsSelected = (val) => {
  try {
    console.log('[Runs] update:selected event:', Array.isArray(val) ? val.map(v => v?.pk || v?.id || v) : val)
  } catch (e) {}
}

// Debug: table click events
const onRunsTableClick = (e) => {
  try {
    console.log('[Runs] table click', e?.target?.tagName, e?.target?.className)
  } catch (e) {}
}

// Debug: observe data loading
watch(runs, (val) => {
  try {
    console.log('[Runs] items loaded:', Array.isArray(val) ? val.length : 0, 'first:', val?.[0] ? Object.keys(val[0]) : null)
  } catch (e) {}
})
</script>

<style scoped>
.runs {
  padding: 20px 0;
}

/* Allow title + actions to wrap on small widths */
.header-bar {
  flex-wrap: wrap;
  row-gap: 8px;
}

/* Hide long button labels on small screens to keep action buttons compact */
@media (max-width: 540px) {
  .runs .btn-label {
    display: none;
  }
}

.hi-contrast-switch:not(.v-selection-control--dirty) :deep(.v-switch__track) {
  background-color: rgba(var(--v-theme-on-surface), 0.20) !important;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.35) !important;
}
.hi-contrast-switch:not(.v-selection-control--dirty) :deep(.v-switch__thumb) {
  background-color: rgb(var(--v-theme-surface)) !important;
  border: 2px solid rgba(var(--v-theme-on-surface), 0.55) !important;
}
.hi-contrast-switch.v-selection-control--dirty :deep(.v-switch__track) {
  background-color: rgb(var(--v-theme-primary)) !important;
  border-color: rgb(var(--v-theme-primary)) !important;
  opacity: 1 !important;
}
.hi-contrast-switch.v-selection-control--dirty :deep(.v-switch__thumb) {
  background-color: #ffffff !important;
  border: 2px solid rgb(var(--v-theme-primary)) !important;
}
.hi-contrast-switch :deep(input:checked ~ .v-selection-control__wrapper .v-switch__track) {
  background-color: rgb(var(--v-theme-primary)) !important;
  border-color: rgb(var(--v-theme-primary)) !important;
  opacity: 1 !important;
}
.hi-contrast-switch :deep(input:checked ~ .v-selection-control__wrapper .v-switch__thumb) {
  background-color: #ffffff !important;
  border: 2px solid rgb(var(--v-theme-primary)) !important;
}
.hi-contrast-switch :deep(.v-label) {
  color: rgba(var(--v-theme-on-surface), 0.85) !important;
  font-weight: 500;
}
/* Ensure ON state is visibly blue even when Vuetify applies bg-primary on the track */
.hi-contrast-switch :deep(.v-switch__track.bg-primary) {
  background-color: rgb(var(--v-theme-primary)) !important;
  border-color: rgb(var(--v-theme-primary)) !important;
  opacity: 1 !important;
}

.items-per-page-select {
  max-width: 100px;
}

.pagination-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 50%;
}

/* Make links obvious like on Dashboard tables */
.custom-table :deep(a) {
  color: var(--v-theme-primary);
  text-decoration: none;
  font-weight: 600;
  transition: all var(--v-theme-transition-fast);
  position: relative;
  padding: 2px 4px;
  border-radius: var(--v-theme-radius-sm);
  background-color: rgba(var(--v-theme-primary-light), 0.3);
  display: inline-block;
  margin: -2px -4px;
}

.custom-table :deep(a:hover) {
  color: var(--v-theme-primary-dark);
  background-color: rgba(var(--v-theme-primary-light), 0.9);
  transform: translateY(-1px);
}

.custom-table :deep(a::after) {
  content: '';
  position: absolute;
  width: 100%;
  height: 2px;
  bottom: 0;
  left: 0;
  background-color: var(--v-theme-primary);
  transform: scaleX(0);
  transition: transform var(--v-theme-transition-fast);
  border-radius: var(--v-theme-radius-sm);
}

.custom-table :deep(a:hover::after) {
  transform: scaleX(1);
}

.v-data-table :deep(th) {
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}

.v-data-table :deep(.v-data-table__wrapper) {
  overflow-x: auto;
  overflow-y: visible;
}

/* Align cell padding with Objects overview */
.v-data-table :deep(td) {
  padding: 8px 16px !important;
}

/* Responsive wrapping for action bar */
.card-actions-responsive {
  flex-wrap: wrap;
  gap: 12px;
}
.card-actions-responsive .actions-left,
.card-actions-responsive .actions-right {
  flex-wrap: wrap;
}
.card-actions-responsive .actions-left { row-gap: 8px; }
.card-actions-responsive .actions-right { row-gap: 8px; }
.card-actions-responsive .items-per-page-select { min-width: 96px; }

/* Single-line truncation with ellipsis */
.cell-truncate {
  display: inline-block;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>