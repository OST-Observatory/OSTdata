<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Plate Solving</h1>
      <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchUnsolvedFiles">
        Refresh
      </v-btn>
    </div>

    <!-- Statistics Card -->
    <v-card class="mb-3" v-if="stats">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="3">
            <div class="text-caption text-medium-emphasis">Total Light Frames</div>
            <div class="text-h6">{{ stats.total_light || 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <div class="text-caption text-medium-emphasis">Solved</div>
            <div class="text-h6 text-success">{{ stats.solved || 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <div class="text-caption text-medium-emphasis">Unsolved</div>
            <div class="text-h6 text-warning">{{ stats.unsolved || 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <div class="text-caption text-medium-emphasis">Attempted</div>
            <div class="text-h6">{{ stats.attempted || 0 }}</div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Filters -->
    <v-card class="mb-3">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="filters.observation_run_name"
              :items="observationRuns"
              item-title="name"
              item-value="id"
              label="Observation Run"
              prepend-inner-icon="mdi-telescope"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
              @update:model-value="handleFilterChange"
            >
              <template #item="{ item, props }">
                <v-list-item v-bind="props">
                  <template #title>
                    <div class="d-flex flex-column">
                      <span>{{ item.raw.name }}</span>
                      <span class="text-caption text-medium-emphasis">{{ formatDate(item.raw.obs_date) }}</span>
                    </div>
                  </template>
                </v-list-item>
              </template>
            </v-select>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model="filters.file_name"
              label="File Name"
              prepend-inner-icon="mdi-file"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model="filters.instrument"
              label="Instrument"
              prepend-inner-icon="mdi-camera"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model="filters.file_type"
              label="File Type"
              prepend-inner-icon="mdi-file-code"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="filters.status"
              :items="statusOptions"
              label="Status"
              prepend-inner-icon="mdi-filter"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
              @update:model-value="handleFilterChange"
            />
          </v-col>
          <v-col cols="12" class="d-flex align-end">
            <v-btn color="secondary" variant="text" prepend-icon="mdi-filter-remove" @click="resetFilters">
              Reset Filters
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Bulk Actions -->
    <v-card class="mb-3" v-if="selectedCount > 0">
      <v-card-text class="d-flex align-center justify-space-between" style="gap: 8px">
        <div class="text-body-2">
          {{ selectedCount }} selected
        </div>
        <div class="d-flex align-center" style="gap: 8px">
          <v-btn
            color="primary"
            variant="outlined"
            prepend-icon="mdi-star-four-points"
            :disabled="selectedCount === 0"
            :loading="triggering"
            @click="triggerSolve"
          >
            Trigger Solve ({{ selectedCount }})
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- Data Table -->
    <v-card>
      <v-data-table
        :headers="headers"
        :items="items"
        item-value="pk"
        item-key="pk"
        return-object
        show-select
        select-strategy="page"
        v-model="selected"
        v-model:selected="selected"
        v-model:selection="selected"
        @update:selected="onUpdateSelected"
        @update:modelValue="onUpdateSelected"
        @update:selection="onUpdateSelected"
        @update:options="handleSortChange"
        :loading="loading"
        class="custom-table"
        :items-length="totalItems"
        :items-per-page="itemsPerPage === -1 ? totalItems : itemsPerPage"
        hide-default-footer
        :sort-by="[{ key: sortBy, order: sortOrder }]"
        :multi-sort="false"
      >
        <template #loading>
          <LoadingState type="table" />
        </template>
        <template #no-data>
          <EmptyState text="No unsolved files found." />
        </template>

        <template #item.file_name="{ item }">
          <span class="cell-truncate">{{ item.file_name }}</span>
        </template>

        <template #item.observation_run_name="{ item }">
          <router-link :to="`/observation-runs/${item.observation_run}`" class="text-primary text-decoration-none">
            {{ item.observation_run_name }}
          </router-link>
        </template>

        <template #item.instrument="{ item }">
          <span>{{ item.instrument || '—' }}</span>
        </template>

        <template #item.file_type="{ item }">
          <v-chip size="small" variant="outlined">{{ item.file_type || '—' }}</v-chip>
        </template>

        <template #item.exposure_type="{ item }">
          <v-chip size="small" :color="getExposureTypeColor(item.effective_exposure_type || item.exposure_type)" variant="flat">
            {{ item.exposure_type_display || item.exposure_type }}
          </v-chip>
        </template>

        <template #item.plate_solve_attempted_at="{ item }">
          <span v-if="item.plate_solve_attempted_at" class="text-caption">
            {{ formatDate(item.plate_solve_attempted_at) }}
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.plate_solve_error="{ item }">
          <span v-if="item.plate_solve_error" class="text-error text-caption">
            {{ truncateError(item.plate_solve_error) }}
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center" style="gap: 4px">
            <v-btn
              icon="mdi-eye"
              size="small"
              variant="text"
              @click="openPreview(item)"
              :aria-label="`Preview ${item.file_name}`"
            />
            <v-btn
              icon="mdi-code-tags"
              size="small"
              variant="text"
              @click="openHeader(item)"
              :aria-label="`View header for ${item.file_name}`"
            />
            <v-btn
              icon="mdi-star-four-points"
              size="small"
              variant="text"
              @click="triggerSolveSingle(item)"
              :loading="triggeringSingle === item.pk"
              :aria-label="`Trigger solve for ${item.file_name}`"
            />
          </div>
        </template>
      </v-data-table>

      <!-- Custom pagination controls -->
      <v-card-actions class="d-flex align-center justify-space-between px-4 py-2">
        <div class="d-flex align-center">
          <span class="text-body-2 mr-4">Items per page:</span>
          <v-select
            v-model="itemsPerPage"
            :items="[10, 25, 50, 100, 500, 1000, -1]"
            :item-title="item => item === -1 ? 'All' : item.toString()"
            :item-value="item => item"
            density="compact"
            variant="outlined"
            hide-details
            style="width: 100px"
            @update:model-value="handleItemsPerPageChange"
            aria-label="Items per page"
          ></v-select>
        </div>

        <div class="d-flex align-center">
          <span class="text-body-2 mr-4">
            {{ paginationInfo }}
          </span>
          <v-btn
            icon="mdi-page-first"
            variant="text"
            :disabled="currentPage === 1"
            @click="handlePageChange(1)"
            class="mx-1"
            aria-label="First page"
          ></v-btn>
          <v-btn
            icon="mdi-chevron-left"
            variant="text"
            :disabled="currentPage === 1"
            @click="handlePageChange(currentPage - 1)"
            class="mx-1"
            aria-label="Previous page"
          ></v-btn>
          <v-btn
            icon="mdi-chevron-right"
            variant="text"
            :disabled="currentPage >= totalPages"
            @click="handlePageChange(currentPage + 1)"
            class="mx-1"
            aria-label="Next page"
          ></v-btn>
          <v-btn
            icon="mdi-page-last"
            variant="text"
            :disabled="currentPage >= totalPages"
            @click="handlePageChange(totalPages)"
            class="mx-1"
            aria-label="Last page"
          ></v-btn>
        </div>
      </v-card-actions>
    </v-card>

    <!-- Preview dialog -->
    <v-dialog v-model="previewDialog" max-width="900" aria-labelledby="preview-title">
      <v-card>
        <v-card-title id="preview-title">{{ previewTitle }}</v-card-title>
        <v-card-text class="preview-container">
          <div v-if="previewLoading" class="d-flex align-center justify-center preview-placeholder">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-img
            v-if="previewUrl"
            :src="previewUrl"
            alt="Preview"
            max-height="600"
            contain
            @load="handlePreviewLoad"
            @error="handlePreviewError"
          />
          <v-alert v-if="previewError" type="error" variant="tonal" class="mt-2">{{ previewError }}</v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" color="primary" @click="previewDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- FITS Header dialog -->
    <v-dialog v-model="headerDialog" max-width="800" aria-labelledby="header-title">
      <v-card>
        <v-card-title id="header-title">{{ headerTitle || 'FITS Header' }}</v-card-title>
        <v-card-text>
          <v-alert v-if="headerError" type="error" variant="tonal">{{ headerError }}</v-alert>
          <v-skeleton-loader v-else-if="headerLoading" type="table" />
          <template v-else>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(value, key) in headerEntries" :key="key">
                  <td><code>{{ key }}</code></td>
                  <td><code>{{ formatHeaderValue(value) }}</code></td>
                </tr>
              </tbody>
            </v-table>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" color="primary" @click="headerDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import EmptyState from '@/components/ui/EmptyState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const notify = useNotifyStore()
const loading = ref(false)
const triggering = ref(false)
const triggeringSingle = ref(null)
const items = ref([])
const selected = ref([])
const totalItems = ref(0)
const currentPage = ref(1)
const itemsPerPage = ref(25)
const stats = ref(null)

const filters = ref({
  observation_run_name: null,
  file_name: null,
  instrument: null,
  file_type: null,
  status: null,
})

const observationRuns = ref([])
const statusOptions = [
  { title: 'Unsolved', value: 'unsolved' },
  { title: 'Solved', value: 'solved' },
  { title: 'Attempted', value: 'attempted' },
  { title: 'Error', value: 'error' },
]

const sortBy = ref('pk')
const sortOrder = ref('asc')

const headers = [
  { title: 'File Name', key: 'file_name', sortable: true },
  { title: 'Observation Run', key: 'observation_run_name', sortable: true },
  { title: 'Instrument', key: 'instrument', sortable: true },
  { title: 'File Type', key: 'file_type', sortable: true },
  { title: 'Exposure Type', key: 'exposure_type', sortable: false },
  { title: 'Last Attempt', key: 'plate_solve_attempted_at', sortable: true },
  { title: 'Error', key: 'plate_solve_error', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false, width: '120px' },
]

const previewDialog = ref(false)
const previewTitle = ref('')
const previewUrl = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)

const headerDialog = ref(false)
const headerTitle = ref('')
const headerData = ref(null)
const headerLoading = ref(false)
const headerError = ref(null)

const selectedCount = computed(() => selected.value.length)

const totalPages = computed(() => {
  if (itemsPerPage.value === -1) return 1
  return Math.ceil(totalItems.value / itemsPerPage.value)
})

const paginationInfo = computed(() => {
  if (totalItems.value === 0) return '0-0 of 0'
  const start = (currentPage.value - 1) * (itemsPerPage.value === -1 ? totalItems.value : itemsPerPage.value) + 1
  const end = Math.min(start + (itemsPerPage.value === -1 ? totalItems.value : itemsPerPage.value) - 1, totalItems.value)
  return `${start}-${end} of ${totalItems.value}`
})

const headerEntries = computed(() => {
  if (!headerData.value) return {}
  // Extract nested header object if present
  if (headerData.value.header && typeof headerData.value.header === 'object') {
    return headerData.value.header
  }
  return headerData.value
})

const getExposureTypeColor = (type) => {
  const colors = {
    'BI': 'blue',
    'DA': 'grey-darken-2',
    'FL': 'green',
    'LI': 'orange',
    'WA': 'purple',
    'UK': 'grey',
  }
  return colors[type] || 'grey'
}

const formatHeaderValue = (value) => {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const formatDate = (dateString) => {
  if (!dateString) return '—'
  try {
    const date = new Date(dateString)
    return date.toLocaleString()
  } catch {
    return dateString
  }
}

const truncateError = (error) => {
  if (!error) return '—'
  return error.length > 100 ? error.substring(0, 100) + '...' : error
}

const resetFilters = () => {
  filters.value = {
    observation_run_name: null,
    file_name: null,
    instrument: null,
    file_type: null,
    status: null,
  }
  sortBy.value = 'pk'
  sortOrder.value = 'asc'
  currentPage.value = 1
  fetchUnsolvedFiles()
}

const handleFilterChange = () => {
  currentPage.value = 1
  fetchUnsolvedFiles()
}

const handleSortChange = (options) => {
  // Handle sort changes from v-data-table
  if (options && options.sortBy && options.sortBy.length > 0) {
    const sort = options.sortBy[0]
    // Map frontend keys to backend keys
    const keyMap = {
      'file_name': 'datafile',
      'observation_run_name': 'observation_run',
      'plate_solve_attempted_at': 'plate_solve_attempted_at',
      'instrument': 'instrument',
      'file_type': 'file_type',
    }
    sortBy.value = keyMap[sort.key] || sort.key || 'pk'
    sortOrder.value = sort.order || 'asc'
  } else {
    sortBy.value = 'pk'
    sortOrder.value = 'asc'
  }
  currentPage.value = 1
  fetchUnsolvedFiles()
}

const fetchStats = async () => {
  try {
    stats.value = await api.getPlateSolveStats()
  } catch (error) {
    notify.error('Failed to fetch statistics', error)
  }
}

const fetchObservationRuns = async () => {
  try {
    const response = await api.getObservationRunsForPlateSolving()
    if (response.results) {
      observationRuns.value = response.results
    }
  } catch (error) {
    notify.error('Failed to fetch observation runs', error)
  }
}

const fetchUnsolvedFiles = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.observation_run_name) params.observation_run_name = filters.value.observation_run_name
    if (filters.value.file_name) params.file_name = filters.value.file_name
    if (filters.value.instrument) params.instrument = filters.value.instrument
    if (filters.value.file_type) params.file_type = filters.value.file_type
    if (filters.value.status) params.status = filters.value.status
    
    // Add sorting parameters
    params.sort_by = sortBy.value
    params.sort_order = sortOrder.value
    
    // Add pagination parameters
    params.page = currentPage.value
    params.limit = itemsPerPage.value === -1 ? 10000 : itemsPerPage.value

    const response = await api.getUnsolvedPlateFiles(params)
    if (response.results) {
      items.value = response.results
      totalItems.value = response.count || response.total || response.results.length
    } else if (Array.isArray(response)) {
      items.value = response
      totalItems.value = response.length
    } else {
      items.value = []
      totalItems.value = 0
    }
  } catch (error) {
    notify.error('Failed to fetch unsolved files', error)
    items.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    fetchUnsolvedFiles()
  }
}

const handleItemsPerPageChange = (value) => {
  currentPage.value = 1
  fetchUnsolvedFiles()
}

const onUpdateSelected = () => {
  // Handle selection updates
}

const openPreview = async (item) => {
  previewDialog.value = true
  previewTitle.value = item.file_name
  previewUrl.value = null
  previewLoading.value = true
  previewError.value = null

  try {
    const url = api.getDataFileThumbnailUrl(item.pk, 512)
    previewUrl.value = url
  } catch (error) {
    previewError.value = 'Failed to load preview'
    notify.error('Failed to load preview', error)
  } finally {
    previewLoading.value = false
  }
}

const handlePreviewLoad = () => {
  previewLoading.value = false
}

const handlePreviewError = () => {
  previewLoading.value = false
  previewError.value = 'Failed to load preview image'
}

const openHeader = async (item) => {
  headerDialog.value = true
  headerTitle.value = `FITS Header: ${item.file_name}`
  headerData.value = null
  headerLoading.value = true
  headerError.value = null

  try {
    const data = await api.getDataFileHeader(item.pk)
    headerData.value = data
  } catch (error) {
    headerError.value = 'Failed to load header'
    notify.error('Failed to load header', error)
  } finally {
    headerLoading.value = false
  }
}

const triggerSolve = async () => {
  if (selected.value.length === 0) return
  
  triggering.value = true
  try {
    const fileIds = selected.value.map(item => item.pk)
    const response = await api.triggerPlateSolve(fileIds)
    
    if (response.results) {
      const succeeded = response.results.filter(r => r.success).length
      const failed = response.results.filter(r => !r.success).length
      
      if (succeeded > 0) {
        notify.success(`Plate solving triggered: ${succeeded} succeeded, ${failed} failed`)
      } else {
        notify.warning(`Plate solving failed for all ${fileIds.length} files`)
      }
      
      // Refresh data
      await fetchUnsolvedFiles()
      await fetchStats()
      selected.value = []
    } else {
      notify.error('Unexpected response format')
    }
  } catch (error) {
    notify.error('Failed to trigger plate solving', error)
  } finally {
    triggering.value = false
  }
}

const triggerSolveSingle = async (item) => {
  triggeringSingle.value = item.pk
  try {
    const response = await api.triggerPlateSolve([item.pk])
    
    if (response.results && response.results.length > 0) {
      const result = response.results[0]
      if (result.success) {
        notify.success(`Plate solving succeeded for ${item.file_name}`)
      } else {
        notify.warning(`Plate solving failed: ${result.error || 'Unknown error'}`)
      }
      
      // Refresh data
      await fetchUnsolvedFiles()
      await fetchStats()
    } else {
      notify.error('Unexpected response format')
    }
  } catch (error) {
    notify.error('Failed to trigger plate solving', error)
  } finally {
    triggeringSingle.value = null
  }
}

onMounted(() => {
  fetchStats()
  fetchObservationRuns()
  fetchUnsolvedFiles()
})
</script>

<style scoped>
.cell-truncate {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.preview-container {
  min-height: 200px;
}

.preview-placeholder {
  min-height: 200px;
}
</style>
