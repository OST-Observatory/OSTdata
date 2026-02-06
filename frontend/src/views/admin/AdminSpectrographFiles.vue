<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Spectrograph Management</h1>
      <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchFiles">
        Refresh
      </v-btn>
    </div>

    <v-card class="mb-3">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="filters.spectrograph"
              :items="spectrographItems"
              item-title="label"
              item-value="value"
              label="Spectrograph"
              prepend-inner-icon="mdi-filter"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-select
              v-model="filters.exposure_type"
              :items="exposureTypeItems"
              item-title="label"
              item-value="value"
              label="Exposure Type"
              prepend-inner-icon="mdi-filter"
              hide-details
              density="comfortable"
              variant="outlined"
              clearable
            />
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-text-field
              v-model="filters.observation_run"
              label="Observation Run ID"
              prepend-inner-icon="mdi-telescope"
              hide-details
              density="comfortable"
              variant="outlined"
              type="number"
              min="1"
              clearable
            />
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

    <v-card class="mb-3" v-if="selectedCount > 0">
      <v-card-text class="d-flex align-center justify-space-between" style="gap: 8px">
        <div class="text-body-2">
          {{ selectedCount }} selected
        </div>
        <div class="d-flex align-center" style="gap: 8px">
          <v-btn
            color="primary"
            variant="outlined"
            prepend-icon="mdi-pencil"
            :disabled="selectedCount === 0"
            @click="openBulkEditDialog"
          >
            Set Spectrograph ({{ selectedCount }})
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

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
        :loading="loading"
        class="custom-table"
        :items-length="totalItems"
        :items-per-page="itemsPerPage === -1 ? totalItems : itemsPerPage"
        hide-default-footer
      >
        <template #loading>
          <LoadingState type="table" />
        </template>
        <template #no-data>
          <EmptyState text="No files found." />
        </template>

        <template #item.file_name="{ item }">
          <span class="cell-truncate">{{ item.file_name }}</span>
        </template>

        <template #item.observation_run_name="{ item }">
          <router-link :to="`/observation-runs/${item.observation_run}`" class="text-primary text-decoration-none">
            {{ item.observation_run_name }}
          </router-link>
        </template>

        <template #item.exposure_type="{ item }">
          <v-chip size="small" :color="getExposureTypeColor(item.exposure_type)" variant="flat">
            {{ item.exposure_type_display || item.exposure_type }}
          </v-chip>
        </template>

        <template #item.spectrograph="{ item }">
          <div v-if="item.spectrograph && item.spectrograph !== 'N'">
            <v-chip size="small" :color="getSpectrographColor(item.spectrograph)" variant="flat">
              {{ getSpectrographLabel(item.spectrograph) }}
            </v-chip>
            <v-chip v-if="item.spectrograph_override" size="x-small" color="info" variant="flat" class="mt-1">
              Override
            </v-chip>
          </div>
          <span v-else class="text-medium-emphasis">None</span>
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
              icon="mdi-pencil"
              size="small"
              variant="text"
              @click="openEditDialog(item)"
              :aria-label="`Edit spectrograph for ${item.file_name}`"
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
                  <th class="text-primary" style="width: 30%">Key</th>
                  <th class="text-primary">Value</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="([k, v], idx) in headerEntries" :key="k || idx">
                  <td class="font-mono">{{ k }}</td>
                  <td class="font-mono">{{ formatHeaderValue(v) }}</td>
                </tr>
              </tbody>
            </v-table>
            <div v-if="!headerEntries.length" class="text-caption text-secondary">No header data.</div>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" color="primary" @click="headerDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit Spectrograph dialog -->
    <v-dialog v-model="editDialog" max-width="500" aria-labelledby="edit-title">
      <v-card>
        <v-card-title id="edit-title">Set Spectrograph</v-card-title>
        <v-card-text>
          <v-select
            v-model="editForm.spectrograph"
            :items="spectrographItems"
            item-title="label"
            item-value="value"
            label="Spectrograph"
            prepend-inner-icon="mdi-telescope"
            variant="outlined"
            clearable
            hint="Leave empty to set to None"
            persistent-hint
          />
          <v-checkbox
            v-model="editForm.spectrograph_override"
            label="Set override flag"
            hint="Prevent automatic updates to this value"
            persistent-hint
            class="mt-2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="editSaving" @click="saveSpectrograph">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Bulk Edit Spectrograph dialog -->
    <v-dialog v-model="bulkEditDialog" max-width="500" aria-labelledby="bulk-edit-title">
      <v-card>
        <v-card-title id="bulk-edit-title">Set Spectrograph ({{ selectedCount }} files)</v-card-title>
        <v-card-text>
          <v-select
            v-model="bulkEditForm.spectrograph"
            :items="spectrographItems"
            item-title="label"
            item-value="value"
            label="Spectrograph"
            prepend-inner-icon="mdi-telescope"
            variant="outlined"
            clearable
            hint="Leave empty to set to None"
            persistent-hint
          />
          <v-checkbox
            v-model="bulkEditForm.spectrograph_override"
            label="Set override flag"
            hint="Prevent automatic updates to this value"
            persistent-hint
            class="mt-2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="bulkEditDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="bulkEditSaving" @click="saveBulkSpectrograph">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import EmptyState from '@/components/ui/EmptyState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const notify = useNotifyStore()
const loading = ref(false)
const items = ref([])
const itemsPerPage = ref(10)
const currentPage = ref(1)
const totalItems = ref(0)
const selected = ref([])

const filters = ref({
  spectrograph: null,
  exposure_type: null,
  observation_run: null,
  file_name: null,
})

const spectrographItems = [
  { label: 'DADOS', value: 'D' },
  { label: 'BACHES', value: 'B' },
  { label: 'EINSTEIN_TOWER', value: 'E' },
  { label: 'None', value: 'N' },
]

const exposureTypeItems = [
  { label: 'Bias', value: 'BI' },
  { label: 'Dark', value: 'DA' },
  { label: 'Flat', value: 'FL' },
  { label: 'Light', value: 'LI' },
  { label: 'Wave', value: 'WA' },
  { label: 'Unknown', value: 'UK' },
]

const headers = [
  { title: 'File Name', key: 'file_name', sortable: true },
  { title: 'Observation Run', key: 'observation_run_name', sortable: true },
  { title: 'Exposure Type', key: 'exposure_type', sortable: true },
  { title: 'Spectrograph', key: 'spectrograph', sortable: true },
  { title: 'Actions', key: 'actions', sortable: false, width: '120px' },
]

// Preview dialog
const previewDialog = ref(false)
const previewTitle = ref('')
const previewUrl = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)

// Header dialog
const headerDialog = ref(false)
const headerTitle = ref('')
const headerData = ref(null)
const headerLoading = ref(false)
const headerError = ref(null)

// Edit dialog
const editDialog = ref(false)
const editSaving = ref(false)
const editForm = ref({
  pk: null,
  spectrograph: null,
  spectrograph_override: false,
})

// Bulk edit dialog
const bulkEditDialog = ref(false)
const bulkEditSaving = ref(false)
const bulkEditForm = ref({
  spectrograph: null,
  spectrograph_override: true, // Default to true for bulk operations
})

const selectedIds = computed(() => {
  return selected.value.map(val => {
    return (val && typeof val === 'object') ? val.pk : val
  }).filter(v => v !== null && v !== undefined && v !== '')
})

const selectedCount = computed(() => selectedIds.value.length)

const onUpdateSelected = (val) => {
  try {
    selected.value = Array.isArray(val) ? val : []
  } catch (e) {
    selected.value = []
  }
}

const headerEntries = computed(() => {
  if (!headerData.value) return []
  // API returns {header: {...}}, so extract the header object
  const headerObj = headerData.value.header || headerData.value
  return Object.entries(headerObj)
})

const totalPages = computed(() => {
  if (itemsPerPage.value === -1) return 1
  return Math.ceil(totalItems.value / itemsPerPage.value)
})

const paginationInfo = computed(() => {
  if (itemsPerPage.value === -1) {
    return `Showing all ${totalItems.value} items`
  }
  const start = (currentPage.value - 1) * itemsPerPage.value + 1
  const end = Math.min(currentPage.value * itemsPerPage.value, totalItems.value)
  return `${start}-${end} of ${totalItems.value}`
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

const getSpectrographColor = (spectrograph) => {
  const colors = {
    'D': 'blue',
    'B': 'green',
    'E': 'purple',
    'N': 'grey',
  }
  return colors[spectrograph] || 'grey'
}

const getSpectrographLabel = (spectrograph) => {
  const item = spectrographItems.find(i => i.value === spectrograph)
  return item ? item.label : spectrograph
}

const formatHeaderValue = (value) => {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const resetFilters = () => {
  filters.value = {
    spectrograph: null,
    exposure_type: null,
    observation_run: null,
    file_name: null,
  }
  currentPage.value = 1
  fetchFiles()
}

const fetchFiles = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.spectrograph) params.spectrograph = filters.value.spectrograph
    if (filters.value.exposure_type) params.exposure_type = filters.value.exposure_type
    if (filters.value.observation_run) params.observation_run = parseInt(filters.value.observation_run)
    if (filters.value.file_name) params.file_name = filters.value.file_name
    
    // Add pagination parameters
    params.page = currentPage.value
    params.limit = itemsPerPage.value === -1 ? 10000 : itemsPerPage.value

    const response = await api.getSpectrographFiles(params)
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
    notify.error('Failed to fetch files', error)
    items.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    fetchFiles()
  }
}

const handleItemsPerPageChange = (value) => {
  currentPage.value = 1
  fetchFiles()
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

const openEditDialog = (item) => {
  editForm.value = {
    pk: item.pk,
    spectrograph: item.spectrograph && item.spectrograph !== 'N' ? item.spectrograph : null,
    spectrograph_override: true, // Default to true (checked)
  }
  editDialog.value = true
}

const saveSpectrograph = async () => {
  if (!editForm.value.pk) return

  editSaving.value = true
  try {
    await api.updateSpectrograph(editForm.value.pk, {
      spectrograph: editForm.value.spectrograph || 'N',
      spectrograph_override: editForm.value.spectrograph_override,
    })
    notify.success('Spectrograph updated')
    editDialog.value = false
    await fetchFiles()
  } catch (error) {
    notify.error('Failed to update spectrograph', error)
  } finally {
    editSaving.value = false
  }
}

const openBulkEditDialog = () => {
  bulkEditForm.value = {
    spectrograph: null,
    spectrograph_override: true, // Default to true for bulk operations
  }
  bulkEditDialog.value = true
}

const saveBulkSpectrograph = async () => {
  if (selectedIds.value.length === 0) return

  bulkEditSaving.value = true
  try {
    // Update all selected files
    const updates = selectedIds.value.map(id =>
      api.updateSpectrograph(id, {
        spectrograph: bulkEditForm.value.spectrograph || 'N',
        spectrograph_override: bulkEditForm.value.spectrograph_override,
      })
    )
    await Promise.all(updates)
    notify.success(`Updated spectrograph for ${selectedIds.value.length} file(s)`)
    bulkEditDialog.value = false
    selected.value = []
    await fetchFiles()
  } catch (error) {
    notify.error('Failed to update spectrographs', error)
  } finally {
    bulkEditSaving.value = false
  }
}

// Watch filters and refetch (reset to page 1 when filters change)
watch(filters, () => {
  currentPage.value = 1
  fetchFiles()
}, { deep: true })

onMounted(() => {
  fetchFiles()
})
</script>

<style scoped>
.preview-container {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-placeholder {
  min-height: 200px;
}

.cell-truncate {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}
</style>
