<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Data Files</h1>
      <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchFiles">
        Refresh
      </v-btn>
    </div>

    <!-- Collapsible Filters -->
    <v-card class="mb-3">
      <v-expansion-panels variant="accordion">
        <v-expansion-panel>
          <v-expansion-panel-title>Filters</v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-row>
              <v-col cols="12" md="4">
                <v-expansion-panels variant="accordion" class="mb-2">
                  <v-expansion-panel>
                    <v-expansion-panel-title density="compact">File & Run</v-expansion-panel-title>
                    <v-expansion-panel-text>
                      <v-autocomplete
                        v-model="filters.observation_run_name"
                        :items="observationRuns"
                        item-title="name"
                        item-value="name"
                        label="Observation Run"
                        density="comfortable"
                        variant="outlined"
                        hide-details
                        clearable
                        class="mb-2"
                      />
                      <v-text-field v-model="filters.file_name" label="File Name" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-text-field v-model="filters.file_type" label="File Type" density="comfortable" variant="outlined" hide-details clearable />
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-col>
              <v-col cols="12" md="4">
                <v-expansion-panels variant="accordion" class="mb-2">
                  <v-expansion-panel>
                    <v-expansion-panel-title density="compact">Exposure & Type</v-expansion-panel-title>
                    <v-expansion-panel-text>
                      <v-select v-model="filters.effective_exposure_type" :items="exposureTypeItems" item-title="label" item-value="value" label="Effective Type" density="comfortable" variant="outlined" hide-details clearable multiple chips class="mb-2" />
                      <v-select v-model="filters.exposure_type" :items="exposureTypeItems" item-title="label" item-value="value" label="Exposure Type" density="comfortable" variant="outlined" hide-details clearable multiple chips class="mb-2" />
                      <v-select v-model="filters.exposure_type_ml" :items="exposureTypeItems" item-title="label" item-value="value" label="ML Type" density="comfortable" variant="outlined" hide-details clearable multiple chips class="mb-2" />
                      <v-select v-model="filters.exposure_type_user" :items="exposureTypeItems" item-title="label" item-value="value" label="User Type" density="comfortable" variant="outlined" hide-details clearable multiple chips class="mb-2" />
                      <v-select v-model="filters.has_user_type" :items="[{ title: 'Yes', value: true }, { title: 'No', value: false }]" item-title="title" item-value="value" label="Has User Exposure Type" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-text-field v-model.number="filters.exptime_min" label="Exp. Time Min" type="number" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-text-field v-model.number="filters.exptime_max" label="Exp. Time Max" type="number" density="comfortable" variant="outlined" hide-details clearable />
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-col>
              <v-col cols="12" md="4">
                <v-expansion-panels variant="accordion" class="mb-2">
                  <v-expansion-panel>
                    <v-expansion-panel-title density="compact">Instrument, Target & More</v-expansion-panel-title>
                    <v-expansion-panel-text>
                      <v-text-field v-model="filters.instrument" label="Instrument" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-text-field v-model="filters.telescope" label="Telescope" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-text-field v-model="filters.main_target" label="Main Target" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-select v-model="filters.spectroscopy" :items="[{ title: 'Yes', value: true }, { title: 'No', value: false }]" item-title="title" item-value="value" label="Spectroscopy" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-select v-model="filters.spectrograph" :items="spectrographItems" item-title="label" item-value="value" label="Spectrograph" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-select v-model="filters.plate_solved" :items="[{ title: 'Yes', value: true }, { title: 'No', value: false }]" item-title="title" item-value="value" label="Plate Solved" density="comfortable" variant="outlined" hide-details clearable class="mb-2" />
                      <v-select v-model="filters.has_error" :items="[{ title: 'Yes', value: true }, { title: 'No', value: false }]" item-title="title" item-value="value" label="Has Plate Error" density="comfortable" variant="outlined" hide-details clearable />
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-col>
            </v-row>
            <div class="d-flex align-center mt-2" style="gap: 8px">
              <v-btn color="primary" variant="outlined" prepend-icon="mdi-filter-check" @click="fetchFiles">Apply Filters</v-btn>
              <v-btn color="secondary" variant="text" prepend-icon="mdi-filter-remove" @click="resetFilters">Reset Filters</v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card>

    <!-- Bulk Actions -->
    <v-card class="mb-3" v-if="selectedCount > 0">
      <v-card-text class="d-flex align-center justify-space-between flex-wrap" style="gap: 8px">
        <div class="text-body-2">{{ selectedCount }} selected</div>
        <div class="d-flex align-center flex-wrap" style="gap: 8px">
          <v-btn color="primary" variant="outlined" prepend-icon="mdi-star-four-points" :loading="busy.plateSolve" @click="bulkPlateSolve">Trigger Plate Solve</v-btn>
          <v-btn color="primary" variant="outlined" prepend-icon="mdi-pencil" @click="openBulkExposureTypeDialog">Set User Type</v-btn>
          <v-btn color="primary" variant="outlined" prepend-icon="mdi-telescope" @click="openBulkSpectrographDialog">Set Spectrograph</v-btn>
          <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="busy.reEvaluate" @click="bulkReEvaluate">Re-evaluate</v-btn>
          <v-btn color="secondary" variant="outlined" prepend-icon="mdi-flag-off" :loading="busy.clearOverrides" @click="bulkClearOverrides">Clear Overrides</v-btn>
          <v-btn color="primary" variant="outlined" prepend-icon="mdi-link" :loading="busy.linkObject" @click="openLinkObjectDialog(null)">Link to Object</v-btn>
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
        @update:modelValue="onUpdateSelected"
        @update:options="handleSortChange"
        :sort-by="[{ key: sortBy, order: sortOrder }]"
        :multi-sort="false"
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
          <EmptyState text="No data files found." />
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
            {{ item.exposure_type_display || item.exposure_type || '—' }}
          </v-chip>
        </template>

        <template #item.exposure_type_ml="{ item }">
          <v-chip v-if="item.exposure_type_ml" size="small" :color="getExposureTypeColor(item.exposure_type_ml)" variant="flat">
            {{ item.exposure_type_ml_display || item.exposure_type_ml }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.exposure_type_user="{ item }">
          <v-chip v-if="item.exposure_type_user" size="small" :color="getExposureTypeColor(item.exposure_type_user)" variant="flat">
            {{ item.exposure_type_user_display || item.exposure_type_user }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.plate_solved="{ item }">
          <v-chip size="x-small" :color="item.plate_solved ? 'success' : 'default'" variant="flat">
            {{ item.plate_solved ? 'Yes' : 'No' }}
          </v-chip>
        </template>

        <template #item.spectrograph="{ item }">
          <span v-if="item.spectrograph && item.spectrograph !== 'N'">{{ getSpectrographLabel(item.spectrograph) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center flex-wrap" style="gap: 2px">
            <v-tooltip text="Preview thumbnail" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-eye" size="x-small" variant="text" @click="openPreview(item)" :aria-label="`Preview ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="View FITS header" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-code-tags" size="x-small" variant="text" @click="openHeader(item)" :aria-label="`Header ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="View WCS information" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-crosshairs-gps" size="x-small" variant="text" @click="openWcs(item)" :aria-label="`WCS ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Trigger plate solving" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-star-four-points" size="x-small" variant="text" :loading="triggeringSingle === item.pk" @click="triggerPlateSolveSingle(item)" :aria-label="`Plate solve ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Set exposure type" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-pencil" size="x-small" variant="text" @click="openExposureTypeDialog(item)" :aria-label="`Set type ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Set spectrograph" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-telescope" size="x-small" variant="text" @click="openSpectrographDialog(item)" :aria-label="`Spectrograph ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Re-evaluate object association" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-refresh" size="x-small" variant="text" :loading="reEvalSingle === item.pk" @click="reEvaluateSingle(item)" :aria-label="`Re-evaluate ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Link to object" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-link" size="x-small" variant="text" :loading="linkObjectSingle === item.pk" @click="openLinkObjectDialog(item)" :aria-label="`Link to object ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Clear override flags" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-flag-off" size="x-small" variant="text" :loading="clearOverrideSingle === item.pk" @click="clearOverrideSingleItem(item)" :aria-label="`Clear overrides ${item.file_name}`" />
              </template>
            </v-tooltip>
            <v-tooltip text="Download file" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-download" size="x-small" variant="text" :href="api.getDataFileDownloadUrl(item.pk)" target="_blank" rel="noopener" :aria-label="`Download ${item.file_name}`" />
              </template>
            </v-tooltip>
          </div>
        </template>
      </v-data-table>

      <v-card-actions class="d-flex align-center justify-space-between px-4 py-2">
        <div class="d-flex align-center">
          <span class="text-body-2 mr-4">Items per page:</span>
          <v-select v-model="itemsPerPage" :items="[10, 25, 50, 100, 500, 1000, -1]" :item-title="x => x === -1 ? 'All' : String(x)" :item-value="x => x" density="compact" variant="outlined" hide-details style="width: 100px" @update:model-value="handleItemsPerPageChange" />
        </div>
        <div class="d-flex align-center">
          <span class="text-body-2 mr-4">{{ paginationInfo }}</span>
          <v-btn icon="mdi-page-first" variant="text" :disabled="currentPage === 1" @click="handlePageChange(1)" class="mx-1" />
          <v-btn icon="mdi-chevron-left" variant="text" :disabled="currentPage === 1" @click="handlePageChange(currentPage - 1)" class="mx-1" />
          <v-btn icon="mdi-chevron-right" variant="text" :disabled="currentPage >= totalPages" @click="handlePageChange(currentPage + 1)" class="mx-1" />
          <v-btn icon="mdi-page-last" variant="text" :disabled="currentPage >= totalPages" @click="handlePageChange(totalPages)" class="mx-1" />
        </div>
      </v-card-actions>
    </v-card>

    <!-- Preview dialog -->
    <v-dialog v-model="previewDialog" max-width="900">
      <v-card>
        <v-card-title>{{ previewTitle }}</v-card-title>
        <v-card-text class="preview-container">
          <div v-if="previewLoading" class="d-flex align-center justify-center preview-placeholder"><v-progress-circular indeterminate color="primary" /></div>
          <v-img v-if="previewUrl" :src="previewUrl" alt="Preview" max-height="600" contain @load="previewLoading = false" @error="previewError = 'Failed to load'" />
          <v-alert v-if="previewError" type="error" variant="tonal" class="mt-2">{{ previewError }}</v-alert>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" color="primary" @click="previewDialog = false">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Header dialog -->
    <v-dialog v-model="headerDialog" max-width="800">
      <v-card>
        <v-card-title>{{ headerTitle }}</v-card-title>
        <v-card-text>
          <v-alert v-if="headerError" type="error" variant="tonal">{{ headerError }}</v-alert>
          <v-skeleton-loader v-else-if="headerLoading" type="table" />
          <template v-else>
            <v-table density="compact">
              <thead><tr><th class="text-primary" style="width:30%">Key</th><th class="text-primary">Value</th></tr></thead>
              <tbody>
                <tr v-for="([k, v], idx) in headerEntries" :key="k || idx"><td class="font-mono">{{ k }}</td><td class="font-mono">{{ formatHeaderValue(v) }}</td></tr>
              </tbody>
            </v-table>
          </template>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" color="primary" @click="headerDialog = false">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- WCS dialog -->
    <v-dialog v-model="wcsDialog" max-width="800">
      <v-card>
        <v-card-title>{{ wcsTitle }}</v-card-title>
        <v-card-text>
          <v-alert v-if="!wcsData?.plate_solved" type="info" variant="tonal">No WCS information (file not plate-solved).</v-alert>
          <template v-else>
            <v-table density="compact">
              <thead><tr><th class="text-primary" style="width:35%">Parameter</th><th class="text-primary">Value</th></tr></thead>
              <tbody>
                <tr v-for="([k, v], idx) in wcsEntries" :key="k || idx"><td class="font-mono">{{ k }}</td><td class="font-mono">{{ formatHeaderValue(v) }}</td></tr>
              </tbody>
            </v-table>
          </template>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" color="primary" @click="wcsDialog = false">Close</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Exposure Type dialog -->
    <v-dialog v-model="exposureTypeDialog" max-width="500">
      <v-card>
        <v-card-title>{{ exposureTypeDialogBulk ? `Set User Type (${selectedCount})` : 'Set User Exposure Type' }}</v-card-title>
        <v-card-text>
          <v-select v-model="exposureTypeForm.exposure_type_user" :items="exposureTypeItems" item-title="label" item-value="value" label="Exposure Type" variant="outlined" clearable class="mb-2" />
          <v-checkbox v-model="exposureTypeForm.exposure_type_user_override" label="Set override flag" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="exposureTypeDialog = false">Cancel</v-btn><v-btn color="primary" :loading="exposureTypeSaving" @click="saveExposureType">Save</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Link to Object dialog -->
    <v-dialog v-model="linkObjectDialog" max-width="520" persistent>
      <v-card>
        <v-card-title>{{ linkObjectDialogBulk ? `Link to Object (${linkObjectDatafileIds.length} files)` : 'Link to Object' }}</v-card-title>
        <v-card-text>
          <v-autocomplete
            v-model="linkObjectForm.selectedObject"
            :items="linkObjectSearchResults"
            :loading="linkObjectSearchLoading"
            item-title="name"
            item-value="pk"
            label="Object"
            placeholder="Search by name (e.g. M67, NGC 7000)"
            variant="outlined"
            clearable
            hide-no-data
            :filter="() => true"
            :no-data-text="linkObjectSearchLoading ? 'Searching…' : 'Type to search objects (min. 2 characters)'"
            @update:search="searchObjectsForLink"
          >
            <template #item="{ props, item }">
              <v-list-item v-bind="props" :subtitle="item.raw?.object_type_display">
                <template #title>{{ item.raw?.name }}</template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="linkObjectDialog = false">Cancel</v-btn><v-btn color="primary" :loading="linkObjectSaving" :disabled="!linkObjectForm.selectedObject" @click="saveLinkObject">Link</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Spectrograph dialog -->
    <v-dialog v-model="spectrographDialog" max-width="500">
      <v-card>
        <v-card-title>{{ spectrographDialogBulk ? `Set Spectrograph (${selectedCount})` : 'Set Spectrograph' }}</v-card-title>
        <v-card-text>
          <v-select v-model="spectrographForm.spectrograph" :items="spectrographItems" item-title="label" item-value="value" label="Spectrograph" variant="outlined" clearable class="mb-2" />
          <v-checkbox v-model="spectrographForm.spectrograph_override" label="Set override flag" />
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="spectrographDialog = false">Cancel</v-btn><v-btn color="primary" :loading="spectrographSaving" @click="saveSpectrograph">Save</v-btn></v-card-actions>
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
const items = ref([])
const itemsPerPage = ref(25)
const currentPage = ref(1)
const totalItems = ref(0)
const selected = ref([])
const sortBy = ref('pk')
const sortOrder = ref('desc')
const ordering = computed(() => (sortOrder.value === 'desc' ? '-' : '') + sortBy.value)

const observationRuns = ref([])
const filters = ref({
  observation_run_name: null,
  file_name: null,
  file_type: null,
  instrument: null,
  telescope: null,
  main_target: null,
  effective_exposure_type: [],
  exposure_type: [],
  exposure_type_ml: [],
  exposure_type_user: [],
  has_user_type: null,
  exptime_min: null,
  exptime_max: null,
  spectroscopy: null,
  spectrograph: null,
  plate_solved: null,
  has_error: null,
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
  { title: 'Run', key: 'observation_run_name', sortable: true },
  { title: 'Type', key: 'file_type', sortable: true },
  { title: 'Target', key: 'main_target', sortable: true },
  { title: 'Instrument', key: 'instrument', sortable: true },
  { title: 'Exp. Type', key: 'exposure_type', sortable: true },
  { title: 'ML Type', key: 'exposure_type_ml', sortable: true },
  { title: 'User Type', key: 'exposure_type_user', sortable: true },
  { title: 'Exp. Time', key: 'exptime', sortable: true },
  { title: 'Plate', key: 'plate_solved', sortable: true },
  { title: 'Spectr.', key: 'spectrograph', sortable: true },
  { title: 'Actions', key: 'actions', sortable: false, width: '200px' },
]

const busy = ref({ plateSolve: false, reEvaluate: false, clearOverrides: false, linkObject: false })
const triggeringSingle = ref(null)
const reEvalSingle = ref(null)
const clearOverrideSingle = ref(null)
const linkObjectSingle = ref(null)

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

const wcsDialog = ref(false)
const wcsTitle = ref('')
const wcsData = ref(null)

const exposureTypeDialog = ref(false)
const exposureTypeDialogBulk = ref(false)
const exposureTypeSaving = ref(false)
const exposureTypeForm = ref({ pk: null, exposure_type_user: null, exposure_type_user_override: true })

const spectrographDialog = ref(false)
const spectrographDialogBulk = ref(false)
const spectrographSaving = ref(false)
const spectrographForm = ref({ pk: null, spectrograph: null, spectrograph_override: true })

const linkObjectDialog = ref(false)
const linkObjectDialogBulk = ref(false)
const linkObjectDatafileIds = ref([])
const linkObjectForm = ref({ selectedObject: null })
const linkObjectSearchResults = ref([])
const linkObjectSearchLoading = ref(false)
const linkObjectSaving = ref(false)

const selectedIds = computed(() => selected.value.map(v => (v && typeof v === 'object') ? v.pk : v).filter(Boolean))
const selectedCount = computed(() => selectedIds.value.length)
const totalPages = computed(() => itemsPerPage.value === -1 ? 1 : Math.max(1, Math.ceil(totalItems.value / itemsPerPage.value)))
const paginationInfo = computed(() => {
  if (itemsPerPage.value === -1) return `Showing all ${totalItems.value}`
  const start = (currentPage.value - 1) * itemsPerPage.value + 1
  const end = Math.min(currentPage.value * itemsPerPage.value, totalItems.value)
  return `${start}-${end} of ${totalItems.value}`
})

const headerEntries = computed(() => {
  if (!headerData.value) return []
  const h = headerData.value.header || headerData.value
  return Object.entries(h)
})

const WCS_LABELS = {
  wcs_ra: 'RA (deg)',
  wcs_dec: 'Dec (deg)',
  wcs_ra_hms: 'RA (hms)',
  wcs_dec_dms: 'Dec (dms)',
  wcs_field_radius: 'Field radius (°)',
  wcs_orientation: 'Orientation (°)',
  wcs_pix_scale: 'Pixel scale ("/px)',
  wcs_parity: 'Parity',
  wcs_field_width: 'Field width (°)',
  wcs_field_height: 'Field height (°)',
  wcs_cd1_1: 'CD1_1',
  wcs_cd1_2: 'CD1_2',
  wcs_cd2_1: 'CD2_1',
  wcs_cd2_2: 'CD2_2',
  wcs_cdelt1: 'CDELT1',
  wcs_cdelt2: 'CDELT2',
  wcs_crota1: 'CROTA1',
  wcs_crota2: 'CROTA2',
  wcs_crpix1: 'CRPIX1',
  wcs_crpix2: 'CRPIX2',
  wcs_crval1: 'CRVAL1',
  wcs_crval2: 'CRVAL2',
  plate_solve_tool: 'Plate solve tool',
}
const wcsEntries = computed(() => {
  if (!wcsData.value) return []
  const d = wcsData.value
  const out = []
  for (const [key, label] of Object.entries(WCS_LABELS)) {
    const v = d[key]
    if (v !== null && v !== undefined && v !== '') out.push([label, v])
  }
  return out
})

function onUpdateSelected(val) { selected.value = Array.isArray(val) ? val : [] }

function getExposureTypeColor(t) {
  const c = { BI: 'blue', DA: 'grey-darken-2', FL: 'green', LI: 'orange', WA: 'purple', UK: 'grey' }
  return c[t] || 'grey'
}

function getSpectrographLabel(v) { return (spectrographItems.find(i => i.value === v) || {}).label || v }

function formatHeaderValue(v) {
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function buildParams() {
  const p = { page: currentPage.value, limit: itemsPerPage.value === -1 ? 10000 : itemsPerPage.value, ordering: ordering.value }
  if (filters.value.observation_run_name) p.observation_run_name = filters.value.observation_run_name
  if (filters.value.file_name) p.file_name = filters.value.file_name
  if (filters.value.file_type) p.file_type = filters.value.file_type
  if (filters.value.instrument) p.instrument = filters.value.instrument
  if (filters.value.telescope) p.telescope = filters.value.telescope
  if (filters.value.main_target) p.main_target = filters.value.main_target
  if (filters.value.effective_exposure_type?.length) p.effective_exposure_type = filters.value.effective_exposure_type
  if (filters.value.exposure_type?.length) p.exposure_type = filters.value.exposure_type
  if (filters.value.exposure_type_ml?.length) p.exposure_type_ml = filters.value.exposure_type_ml
  if (filters.value.exposure_type_user?.length) p.exposure_type_user = filters.value.exposure_type_user
  if (filters.value.has_user_type !== null && filters.value.has_user_type !== undefined) p.has_user_type = filters.value.has_user_type
  if (filters.value.exptime_min != null) p.exptime_min = filters.value.exptime_min
  if (filters.value.exptime_max != null) p.exptime_max = filters.value.exptime_max
  if (filters.value.spectroscopy !== null && filters.value.spectroscopy !== undefined) p.spectroscopy = filters.value.spectroscopy
  if (filters.value.spectrograph) p.spectrograph = filters.value.spectrograph
  if (filters.value.plate_solved !== null && filters.value.plate_solved !== undefined) p.plate_solved = filters.value.plate_solved
  if (filters.value.has_error !== null && filters.value.has_error !== undefined) p.has_error = filters.value.has_error
  return p
}

function resetFilters() {
  filters.value = {
    observation_run_name: null,
    file_name: null,
    file_type: null,
    instrument: null,
    telescope: null,
    main_target: null,
    effective_exposure_type: [],
    exposure_type: [],
    exposure_type_ml: [],
    exposure_type_user: [],
    has_user_type: null,
    exptime_min: null,
    exptime_max: null,
    spectroscopy: null,
    spectrograph: null,
    plate_solved: null,
    has_error: null,
  }
  currentPage.value = 1
  fetchFiles()
}

async function fetchFiles() {
  loading.value = true
  try {
    const res = await api.getAllDataFiles(buildParams())
    items.value = res.results || []
    totalItems.value = res.count ?? res.total ?? items.value.length
  } catch (e) {
    notify.error('Failed to fetch data files')
    items.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

function handlePageChange(p) {
  if (p >= 1 && p <= totalPages.value) {
    currentPage.value = p
    fetchFiles()
  }
}

function handleItemsPerPageChange() {
  currentPage.value = 1
  fetchFiles()
}

const keyMap = {
  file_name: 'datafile',
  observation_run_name: 'observation_run',
  file_type: 'file_type',
  main_target: 'main_target',
  instrument: 'instrument',
  exposure_type: 'exposure_type',
  exptime: 'exptime',
  plate_solved: 'plate_solved',
}

function handleSortChange(opts) {
  if (opts?.sortBy?.length) {
    const s = opts.sortBy[0]
    sortBy.value = keyMap[s.key] || s.key || 'pk'
    sortOrder.value = s.order || 'asc'
    currentPage.value = 1
    fetchFiles()
  }
}

async function openPreview(item) {
  previewDialog.value = true
  previewTitle.value = item.file_name
  previewUrl.value = api.getDataFileThumbnailUrl(item.pk, 512)
  previewLoading.value = true
  previewError.value = null
}

async function openHeader(item) {
  headerDialog.value = true
  headerTitle.value = `FITS Header: ${item.file_name}`
  headerData.value = null
  headerLoading.value = true
  headerError.value = null
  try {
    headerData.value = await api.getDataFileHeader(item.pk)
  } catch (e) {
    headerError.value = 'Failed to load header'
  } finally {
    headerLoading.value = false
  }
}

function openWcs(item) {
  wcsDialog.value = true
  wcsTitle.value = `WCS: ${item.file_name}`
  wcsData.value = item
}

async function triggerPlateSolveSingle(item) {
  triggeringSingle.value = item.pk
  try {
    const res = await api.triggerPlateSolve([item.pk])
    const r = res?.results?.[0]
    if (r?.success) notify.success('Plate solving triggered')
    else notify.warning(r?.error || 'Plate solving failed')
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to trigger plate solving')
  } finally {
    triggeringSingle.value = null
  }
}

async function reEvaluateSingle(item) {
  reEvalSingle.value = item.pk
  try {
    const res = await api.adminReEvaluateDataFiles([item.pk])
    notify.success(`Re-evaluated: ${res.evaluated} success, ${res.skipped} skipped, ${res.errors} errors`)
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to re-evaluate')
  } finally {
    reEvalSingle.value = null
  }
}

async function clearOverrideSingleItem(item) {
  clearOverrideSingle.value = item.pk
  try {
    await api.adminClearAllOverrides('datafile', item.pk)
    notify.success('Override flags cleared')
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to clear overrides')
  } finally {
    clearOverrideSingle.value = null
  }
}

async function bulkPlateSolve() {
  if (selectedIds.value.length === 0) return
  busy.value.plateSolve = true
  try {
    const res = await api.triggerPlateSolve(selectedIds.value)
    const ok = res?.results?.filter(r => r.success).length ?? 0
    notify.success(`Plate solving: ${ok} succeeded`)
    selected.value = []
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to trigger plate solving')
  } finally {
    busy.value.plateSolve = false
  }
}

async function bulkReEvaluate() {
  if (selectedIds.value.length === 0) return
  busy.value.reEvaluate = true
  try {
    const res = await api.adminReEvaluateDataFiles(selectedIds.value)
    notify.success(`Re-evaluated: ${res.evaluated} success, ${res.skipped} skipped${res.errors ? `, ${res.errors} errors` : ''}`)
    selected.value = []
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to re-evaluate')
  } finally {
    busy.value.reEvaluate = false
  }
}

async function bulkClearOverrides() {
  if (selectedIds.value.length === 0) return
  busy.value.clearOverrides = true
  try {
    for (const id of selectedIds.value) {
      await api.adminClearAllOverrides('datafile', id)
    }
    notify.success(`Cleared overrides for ${selectedIds.value.length} file(s)`)
    selected.value = []
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to clear overrides')
  } finally {
    busy.value.clearOverrides = false
  }
}

function openExposureTypeDialog(item) {
  exposureTypeDialogBulk.value = false
  exposureTypeForm.value = { pk: item.pk, exposure_type_user: item.exposure_type_user || null, exposure_type_user_override: true }
  exposureTypeDialog.value = true
}

function openBulkExposureTypeDialog() {
  exposureTypeDialogBulk.value = true
  exposureTypeForm.value = { pk: null, exposure_type_user: null, exposure_type_user_override: true }
  exposureTypeDialog.value = true
}

async function saveExposureType() {
  exposureTypeSaving.value = true
  try {
    if (exposureTypeDialogBulk.value) {
      for (const id of selectedIds.value) {
        await api.updateExposureTypeUser(id, {
          exposure_type_user: exposureTypeForm.value.exposure_type_user,
          exposure_type_user_override: exposureTypeForm.value.exposure_type_user_override,
        })
      }
      notify.success(`Updated ${selectedIds.value.length} file(s)`)
      selected.value = []
    } else {
      await api.updateExposureTypeUser(exposureTypeForm.value.pk, {
        exposure_type_user: exposureTypeForm.value.exposure_type_user,
        exposure_type_user_override: exposureTypeForm.value.exposure_type_user_override,
      })
      notify.success('Exposure type updated')
    }
    exposureTypeDialog.value = false
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to update exposure type')
  } finally {
    exposureTypeSaving.value = false
  }
}

function openSpectrographDialog(item) {
  spectrographDialogBulk.value = false
  spectrographForm.value = { pk: item.pk, spectrograph: item.spectrograph && item.spectrograph !== 'N' ? item.spectrograph : null, spectrograph_override: true }
  spectrographDialog.value = true
}

function openBulkSpectrographDialog() {
  spectrographDialogBulk.value = true
  spectrographForm.value = { pk: null, spectrograph: null, spectrograph_override: true }
  spectrographDialog.value = true
}

function openLinkObjectDialog(item) {
  if (item) {
    linkObjectDialogBulk.value = false
    linkObjectDatafileIds.value = [item.pk]
  } else {
    linkObjectDialogBulk.value = true
    linkObjectDatafileIds.value = selectedIds.value.length ? [...selectedIds.value] : []
  }
  linkObjectForm.value = { selectedObject: null }
  linkObjectSearchResults.value = []
  linkObjectSingle.value = item ? item.pk : null
  linkObjectDialog.value = true
}

async function searchObjectsForLink(q) {
  const search = (q || '').trim()
  if (search.length < 2) {
    linkObjectSearchResults.value = []
    return
  }
  linkObjectSearchLoading.value = true
  try {
    const res = await api.getObjectsVuetify({ page: 1, itemsPerPage: 50, search })
    const list = res?.items || res?.results || []
    linkObjectSearchResults.value = list
  } catch (e) {
    linkObjectSearchResults.value = []
  } finally {
    linkObjectSearchLoading.value = false
  }
}

async function saveLinkObject() {
  const objectId = linkObjectForm.value.selectedObject
  if (!objectId || linkObjectDatafileIds.value.length === 0) return
  linkObjectSaving.value = true
  if (linkObjectDialogBulk.value) busy.value.linkObject = true
  try {
    const res = await api.adminLinkDatafilesToObject(linkObjectDatafileIds.value, objectId)
    const msg = res?.linked > 0
      ? `Linked ${res.linked} file(s) to object${res.already_linked > 0 ? ` (${res.already_linked} already linked)` : ''}`
      : res?.already_linked > 0 ? `${res.already_linked} file(s) were already linked` : 'No files linked'
    notify.success(msg)
    linkObjectDialog.value = false
    selected.value = []
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to link to object')
  } finally {
    linkObjectSaving.value = false
    linkObjectSingle.value = null
    busy.value.linkObject = false
  }
}

async function saveSpectrograph() {
  spectrographSaving.value = true
  try {
    const payload = { spectrograph: spectrographForm.value.spectrograph || 'N', spectrograph_override: spectrographForm.value.spectrograph_override }
    if (spectrographDialogBulk.value) {
      for (const id of selectedIds.value) {
        await api.updateSpectrograph(id, payload)
      }
      notify.success(`Updated ${selectedIds.value.length} file(s)`)
      selected.value = []
    } else {
      await api.updateSpectrograph(spectrographForm.value.pk, payload)
      notify.success('Spectrograph updated')
    }
    spectrographDialog.value = false
    await fetchFiles()
  } catch (e) {
    notify.error('Failed to update spectrograph')
  } finally {
    spectrographSaving.value = false
  }
}

async function loadObservationRuns() {
  try {
    const res = await api.getAllObservationRuns()
    observationRuns.value = res.results ?? res ?? []
  } catch {
    observationRuns.value = []
  }
}

onMounted(() => {
  loadObservationRuns()
  fetchFiles()
})
</script>

<style scoped>
.cell-truncate { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }
.preview-container { min-height: 200px; }
.preview-placeholder { min-height: 200px; }
</style>
