<template>
  <v-container fluid class="runs">
      <div class="d-flex align-center justify-space-between mb-4">
        <h1 class="text-h4">Observation Runs</h1>
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
          :sort-by="[{ key: sortKey.replace('-', ''), order: sortKey.startsWith('-') ? 'desc' : 'asc' }]"
          @update:sort-by="handleSort"
          hide-default-footer
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
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/api'
import { formatDateTime } from '@/utils/datetime'
import { getStatusColor } from '@/utils/status'
import { useQuerySync } from '@/composables/useQuerySync'
import { useNotifyStore } from '@/store/notify'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const runs = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const sortKey = ref('start_time')
const search = ref('')
const objectFilter = ref('')
const selectedStatus = ref(null)
const photometryFilter = ref(null)
const spectroscopyFilter = ref(null)
const notify = useNotifyStore()

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Date', key: 'date', sortable: true },
  { title: 'Main Targets', key: 'main_targets', sortable: false },
  { title: 'Photometry', key: 'photometry', sortable: false },
  { title: 'Spectroscopy', key: 'spectroscopy', sortable: false },
  { title: 'Lights', key: 'n_light', sortable: true },
  { title: 'Flats', key: 'n_flat', sortable: true },
  { title: 'Darks', key: 'n_dark', sortable: true },
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Status', key: 'status', sortable: false },
]

const statusItems = [
  { title: 'Completed', value: 'completed' },
  { title: 'In Progress', value: 'in_progress' },
  { title: 'Error', value: 'error' },
  { title: 'Not Reduced', value: 'not_reduced' },
]

const boolFilterItems = [
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
        const all = Array.isArray(bulk.results) ? bulk.results : (Array.isArray(bulk.items) ? bulk.items : (Array.isArray(bulk) ? bulk : []))
        if (itemsPerPage.value === -1) {
          runs.value = all
        } else {
          const start = (currentPage.value - 1) * itemsPerPage.value
          runs.value = all.slice(start, start + itemsPerPage.value)
        }
      } else {
        runs.value = serverItems
      }
    } else if (Array.isArray(response.items)) {
      runs.value = response.items
      totalItems.value = response.total || response.items.length
    } else if (Array.isArray(response)) {
      runs.value = response
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
  sortKey.value = 'mid_observation_jd'
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

// Helpers to normalize data across possible API shapes
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
  }
  return null
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
    { key: 'sort', defaultValue: 'start_time' },
  ],
  fetchRuns
)

onMounted(() => {
  applyQuery()
  fetchRuns()
})
</script>

<style scoped>
.runs {
  padding: 20px 0;
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