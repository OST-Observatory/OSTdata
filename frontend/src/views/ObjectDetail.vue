<template>
  <v-container fluid>
    <h1 class="text-h4 mb-2">{{ object?.name || 'Object' }}</h1>
    <!-- <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <span class="sr-only">Object summary</span>
          </v-card-title>
        </v-card>
      </v-col>
    </v-row> -->

    <!-- Summary Section -->
    <v-row>
      <!-- Basic Data -->
      <v-col cols="12" md="4">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Basic Data
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              aria-label="Edit basic data"
              @click="openBasicDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="6">
                <v-list>
                  <v-list-item>
                    <v-list-item-title>Right Ascension:</v-list-item-title>
                    <v-list-item-subtitle class="font-mono">{{ formatRA(object?.ra) }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Declination:</v-list-item-title>
                    <v-list-item-subtitle class="font-mono">{{ formatDec(object?.dec) }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Object Type:</v-list-item-title>
                    <v-list-item-subtitle>{{ object?.object_type_display }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Main Target:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.is_main ? 'success' : 'error'" size="small">
                        {{ object?.is_main ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.is_main ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>SIMBAD Resolved:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.simbad_resolved ? 'success' : 'error'" size="small">
                        {{ object?.simbad_resolved ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.simbad_resolved ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>
              <v-col cols="6">
                <v-list>
                  <v-list-item>
                    <v-list-item-title>Spectroscopy:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.spectroscopy ? 'success' : 'error'" size="small">
                        {{ object?.spectroscopy ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.spectroscopy ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Photometry:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.photometry ? 'success' : 'error'" size="small">
                        {{ object?.photometry ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.photometry ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Total Exposure Time:</v-list-item-title>
                    <v-list-item-subtitle>{{ totalExposureTime }}s</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Internal Identifiers:</v-list-item-title>
                    <v-list-item-subtitle>{{ internalIdentifiers }}</v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Notes -->
      <v-col cols="12" md="3">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Notes
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              @click="openNotesDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <div v-if="object?.note" v-html="formatNotes(object.note)"></div>
            <div v-else class="text-grey">No notes available</div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Tags -->
      <v-col cols="12" md="2">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Tags
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              @click="openTagDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <div v-if="normalizedObjectTags.length" class="d-flex flex-wrap gap-2">
              <v-chip
                v-for="(tag, idx) in normalizedObjectTags"
                :key="tag.pk || tag.name || idx"
                :color="tag.color"
                variant="outlined"
                size="small"
              >
                {{ tag.name }}
              </v-chip>
            </div>
            <div v-else class="text-grey">No tags assigned</div>
          </v-card-text>
        </v-card>
      </v-col>
      
      <!-- Aladin Lite Sky Map -->
      <v-col cols="12" md="3">
        <v-card class="uniform-height">
          <v-card-title>Sky Map</v-card-title>
          <v-card-text>
            <div id="aladin-lite-div" style="width: 100%; height: 265px;"></div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Edit Basic Data Dialog -->
    <v-dialog v-model="basicDialog" max-width="520" @keydown.esc.prevent="closeBasicDialog" aria-labelledby="edit-basic-title">
      <v-card>
        <v-card-title id="edit-basic-title">Edit Basic Data</v-card-title>
        <v-card-text>
          <v-form>
            <v-select
              v-model="editObjectType"
              :items="objectTypeOptions"
              item-title="title"
              item-value="value"
              label="Object Type"
              variant="outlined"
              density="comfortable"
              hide-details
            />
            <div class="d-flex align-center mt-3" style="gap: 16px">
              <v-switch v-model="editSpectroscopy" label="Spectroscopy" color="primary" hide-details density="comfortable" />
              <v-switch v-model="editPhotometry" label="Photometry" color="primary" hide-details density="comfortable" />
            </div>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" :loading="savingBasic" @click="saveBasicData">Save</v-btn>
          <v-btn variant="text" @click="closeBasicDialog" ref="basicCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Sky Map and Aliases -->
    <v-row>

      <!-- Aliases -->
      <v-col cols="12" md="12">
        <v-card>
          <v-card-title>Aliases</v-card-title>
          <v-card-text>
            <div v-if="aliases?.length" class="d-flex flex-wrap gap-2">
              <v-chip
                v-for="alias in aliases"
                :key="alias.pk"
                variant="outlined"
                size="small"
              >
                <a v-if="alias.href" :href="alias.href" target="_blank" class="text-decoration-none">
                  {{ alias.name }}
                </a>
                <span v-else>{{ alias.name }}</span>
              </v-chip>
            </div>
            <div v-else class="text-grey">No aliases known</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Observation Runs Section -->
    <v-row @click="expandRunsIfCollapsed" :class="{ 'expand-clickable': !showObservationRuns }">
      <v-col cols="12">
        <v-card>
          <v-card-title class="d-flex justify-space-between align-center">
            Observation Runs ({{ observationRuns.length }})
            <v-btn
              :icon="showObservationRuns ? 'mdi-eye-off' : 'mdi-eye'"
              size="small"
              variant="text"
              @click.stop="toggleObservationRuns"
              :aria-label="showObservationRuns ? 'Collapse section' : 'Expand section'"
              :aria-expanded="showObservationRuns ? 'true' : 'false'"
              aria-controls="object-observation-runs"
            ></v-btn>
          </v-card-title>
          <v-card-subtitle v-if="!showObservationRuns" class="text-caption text-secondary px-4 pt-0 pb-2">
            Click anywhere on this section to expand.
          </v-card-subtitle>
          
          <v-expand-transition>
            <div v-show="showObservationRuns" id="object-observation-runs">
              <div class="px-4">
              <v-data-table
                :headers="observationRunHeaders"
                :items="observationRuns"
                :loading="loadingObservationRuns"
                class="elevation-1"
              >
                <template v-slot:item.name="{ item }">
                  <router-link :to="`/observation-runs/${item.pk}`" class="text-decoration-none">
                    {{ formatRunName(item) }}
                  </router-link>
                </template>
                <template v-slot:item.n_fits="{ item }">
                  {{ item.n_fits }}/{{ item.n_img }}/{{ item.n_ser }}
                </template>
                <template v-slot:item.expo_time="{ item }">
                  {{ formatExposureTime(item.expo_time) }}
                </template>
                <template v-slot:item.tags="{ item }">
                  <div class="d-flex flex-wrap gap-1">
                    <v-chip
                      v-for="tag in item.tags"
                      :key="tag.pk"
                      :color="tag.color"
                      variant="outlined"
                      size="x-small"
                    >
                      {{ tag.name }}
                    </v-chip>
                  </div>
                </template>
                <template v-slot:item.reduction_status="{ item }">
                  <v-icon :color="getStatusColor(item.reduction_status)" size="small">
                    {{ getStatusIcon(item.reduction_status) }}
                  </v-icon>
                </template>
              </v-data-table>
              </div>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>
    </v-row>

    <!-- Data Files Section -->
    <v-row @click="expandDataFilesIfCollapsed" :class="{ 'expand-clickable': !showDataFiles }">
      <v-col cols="12">
        <v-card>
          <v-card-title class="d-flex justify-space-between align-center">
            Data Files ({{ filteredDataFiles.length }})
            <v-btn
              :icon="showDataFiles ? 'mdi-eye-off' : 'mdi-eye'"
              size="small"
              variant="text"
              @click.stop="toggleDataFiles"
              :aria-label="showDataFiles ? 'Collapse section' : 'Expand section'"
              :aria-expanded="showDataFiles ? 'true' : 'false'"
              aria-controls="object-data-files"
            ></v-btn>
          </v-card-title>
          <v-card-subtitle v-if="!showDataFiles" class="text-caption text-secondary px-4 pt-0 pb-2">
            Click anywhere on this section to expand.
          </v-card-subtitle>
          
          <v-expand-transition>
            <div v-show="showDataFiles" id="object-data-files">
              <div class="px-4">
              <!-- Filters -->
              <div class="d-flex align-center flex-wrap mb-1 px-4" style="gap: 12px">
                <v-text-field v-model="dfFilterFileName" label="File name contains" density="comfortable" variant="outlined" style="min-width: 240px" clearable />
                <v-text-field v-model="dfFilterType" label="File type contains" density="comfortable" variant="outlined" style="min-width: 180px" clearable />
                <v-text-field v-model="dfFilterInstrument" label="Instrument contains" density="comfortable" variant="outlined" style="min-width: 200px" clearable />
                <v-select
                  v-model="dfFilterBinning"
                  :items="binningOptions"
                  label="Binning"
                  density="comfortable"
                  variant="outlined"
                  style="min-width: 160px"
                  clearable
                />
                <v-select
                  v-model="dfFilterExposureTypes"
                  :items="exposureTypeOptions"
                  label="Exposure type"
                  multiple
                  chips
                  closable-chips
                  density="comfortable"
                  variant="outlined"
                  style="min-width: 220px"
                  clearable
                />
                <v-select
                  v-model="dfFilterSpectroscopy"
                  :items="spectroscopyOptions"
                  label="Spectroscopy"
                  density="comfortable"
                  variant="outlined"
                  style="min-width: 180px"
                  clearable
                />
                <v-text-field v-model.number="dfFilterExpMin" type="number" label="Exp min [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
                <v-text-field v-model.number="dfFilterExpMax" type="number" label="Exp max [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
              </div>
              <div class="d-flex align-center flex-wrap mb-4" style="gap: 12px">
                <v-btn variant="text" color="primary" @click="resetDfFilters" aria-label="Reset filters" block>Reset</v-btn>
              </div>

              <!-- Downloads -->
              <div class="d-flex align-center flex-wrap mb-2 px-4" style="gap: 12px">
                <v-btn color="primary" variant="flat" @click="downloadAllObjectFiles" :loading="downloadingAll">Download all</v-btn>
                <v-btn color="primary" variant="text" :disabled="!filteredDataFiles.length" @click="downloadFilteredObjectFiles">Download filtered</v-btn>
                <v-btn color="primary" variant="text" :disabled="!selectedIds.length" @click="downloadSelectedObjectFiles">Download selected ({{ selectedIds.length }})</v-btn>
              </div>

              <v-data-table
                :headers="objectDataFileHeaders"
                :items="filteredDataFiles"
                :loading="loadingDataFiles"
                class="elevation-1"
              >
                <template v-slot:item.select="{ item }">
                  <v-checkbox v-model="selectedIds" :value="(item.pk || item.id)" density="compact" hide-details />
                </template>
                <template v-slot:item.file_name="{ item }">
                  {{ item.file_name }}
                </template>
                <template v-slot:item.obs_date="{ item }">
                  {{ formatDate(item.obs_date) }}
                </template>
                <template v-slot:item.coordinates="{ item }">
                  {{ item.ra_hms }} {{ item.dec_dms }}
                </template>
                <template v-slot:item.observation_run="{ item }">
                  <router-link :to="`/observation-runs/${item.observation_run}`" class="text-decoration-none">
                    {{ formatRunNameFromId(item.observation_run_name) }}
                  </router-link>
                </template>
                <template v-slot:item.tools="{ item }">
                  <div class="text-right">
                    <v-btn variant="text" size="small" icon aria-label="Preview" @click="openPreview(item)">
                      <v-icon>mdi-image-search</v-icon>
                    </v-btn>
                    <v-btn variant="text" size="small" icon :href="api.getDataFileDownloadUrl(item.pk || item.id)" :aria-label="`Download ${item.file_name}`">
                      <v-icon>mdi-download</v-icon>
                    </v-btn>
                  </div>
                </template>
              </v-data-table>
              </div>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>
    </v-row>

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
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" color="primary" @click="previewDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Tag Edit Dialog -->
    <v-dialog v-model="tagDialog" max-width="500px" @keydown.esc.prevent="closeTagDialog" aria-labelledby="edit-tags-title">
      <v-card>
        <v-card-title id="edit-tags-title">Edit Tags</v-card-title>
        <v-card-text role="group" aria-labelledby="tags-title">
        <h3 id="tags-title" class="sr-only">Select tags for this object</h3>
        <v-checkbox
            v-for="(tag, idx) in availableTags"
            :key="tag?.pk || tag?.name || idx"
            v-model="selectedTags"
            :value="tag?.pk"
            :label="tag?.name"
            :color="tag?.color"
          ></v-checkbox>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="saveTags">Save</v-btn>
          <v-btn @click="closeTagDialog" ref="tagCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit Notes Dialog -->
    <v-dialog v-model="notesDialog" max-width="640" @keydown.esc.prevent="closeNotesDialog" aria-labelledby="edit-notes-title">
      <v-card>
        <v-card-title id="edit-notes-title">Edit Notes</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="newNote"
            label="Notes"
            variant="outlined"
            rows="8"
            auto-grow
            clearable
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" @click="saveNotes">Save</v-btn>
          <v-btn variant="text" @click="closeNotesDialog" ref="notesCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { useNotifyStore } from '@/store/notify'

const route = useRoute()
const authStore = useAuthStore()
const notify = useNotifyStore()

// Reactive data
const object = ref(null)
const aliases = ref([])
const observationRuns = ref([])
const dataFiles = ref([])
const availableTags = ref([])
const selectedTags = ref([])
const tagDialog = ref(false)
const tagCloseBtn = ref(null)
const notesDialog = ref(false)
const newNote = ref('')
const notesCloseBtn = ref(null)
const showObservationRuns = ref(false)
const showDataFiles = ref(false)
const loadingObservationRuns = ref(false)
const loadingDataFiles = ref(false)
const basicDialog = ref(false)
const savingBasic = ref(false)
const basicCloseBtn = ref(null)
const editObjectType = ref(null)
const editSpectroscopy = ref(false)
const editPhotometry = ref(false)

// Computed properties
const isAuthenticated = computed(() => authStore.isAuthenticated)
const totalExposureTime = computed(() => {
  if (!dataFiles.value.length) return '0.0'
  const total = dataFiles.value
    .filter(file => file.exposure_type === 'LI')
    .reduce((sum, file) => sum + (file.exptime || 0), 0)
  return total.toFixed(1)
})

const internalIdentifiers = computed(() => {
  if (!aliases.value.length) return 'None'
  return aliases.value
    .filter(alias => alias.info_from_header)
    .map(alias => alias.name)
    .join(', ')
})

const objectTypeOptions = [
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star Cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Star', value: 'ST' },
  { title: 'Solar System', value: 'SO' },
  { title: 'Other', value: 'OT' },
  { title: 'Unknown', value: 'UK' },
]

const openBasicDialog = () => {
  editObjectType.value = object.value?.object_type || null
  editSpectroscopy.value = !!object.value?.spectroscopy
  editPhotometry.value = !!object.value?.photometry
  basicDialog.value = true
}

const closeBasicDialog = () => {
  basicDialog.value = false
  try {
    const el = basicCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveBasicData = async () => {
  if (!object.value) return
  try {
    savingBasic.value = true
    const payload = {
      object_type: editObjectType.value,
      spectroscopy: editSpectroscopy.value,
      photometry: editPhotometry.value,
    }
    await api.updateObject(object.value.pk || object.value.id, payload)
    const updated = await api.getObject(object.value.pk || object.value.id)
    object.value = updated
    basicDialog.value = false
    try { notify.success('Basic data updated') } catch {}
  } catch (e) {
    console.error('Error saving basic data', e)
  } finally {
    savingBasic.value = false
  }
}

// Table headers
const observationRunHeaders = [
  { title: 'Date', key: 'name', sortable: true },
  { title: 'Nobs', key: 'n_fits', sortable: true },
  { title: 'Exposure Time [s]', key: 'expo_time', sortable: true },
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Status', key: 'reduction_status', sortable: true }
]

const dataFileHeaders = [
  // replaced by objectDataFileHeaders below
]

const objectDataFileHeaders = [
  { title: '', key: 'select', sortable: false, width: 36 },
  { title: 'File Name', key: 'file_name', sortable: true },
  { title: 'Observation Date', key: 'obs_date', sortable: true },
  { title: 'Target', key: 'main_target', sortable: true },
  { title: 'Coordinates', key: 'coordinates', sortable: false },
  { title: 'File Type', key: 'file_type', sortable: true },
  { title: 'Binning', key: 'binning', sortable: false },
  { title: 'Instrument', key: 'instrument', sortable: true },
  { title: 'Exposure Type', key: 'exposure_type_display', sortable: true },
  { title: 'Exposure Time [s]', key: 'exptime', sortable: true },
  { title: 'Observation Run', key: 'observation_run', sortable: true },
  { title: 'Tools', key: 'tools', sortable: false },
]

// Methods
const loadObject = async () => {
  try {
    const objectId = route.params.id
    object.value = await api.getObject(objectId)
    await loadAliases(objectId)
    await loadObservationRuns(objectId)
    await loadDataFiles(objectId)
    await loadAvailableTags()
    initializeAladinLite()
  } catch (error) {
    console.error('Error loading object:', error)
  }
}

const loadAliases = async (objectId) => {
  try {
    // Try to derive aliases from object.identifiers if provided by API
    if (Array.isArray(object.value?.identifiers)) {
      aliases.value = object.value.identifiers
        .filter(id => id && id.info_from_header === false)
        .map(id => ({ pk: id.pk || id.id, name: id.name, href: id.href }))
    } else if (Array.isArray(object.value?.identifier_set)) {
      aliases.value = object.value.identifier_set
        .filter(id => id && id.info_from_header === false)
        .map(id => ({ pk: id.pk || id.id, name: id.name, href: id.href }))
    } else {
      aliases.value = []
    }
  } catch (error) {
    console.error('Error loading aliases:', error)
    aliases.value = []
  }
}

const loadObservationRuns = async (objectId) => {
  try {
    loadingObservationRuns.value = true
    const response = await api.getObjectObservationRuns(objectId)
    observationRuns.value = response
  } catch (error) {
    console.error('Error loading observation runs:', error)
  } finally {
    loadingObservationRuns.value = false
  }
}

const loadDataFiles = async (objectId) => {
  try {
    loadingDataFiles.value = true
    const response = await api.getObjectDataFiles(objectId)
    dataFiles.value = response
  } catch (error) {
    console.error('Error loading data files:', error)
  } finally {
    loadingDataFiles.value = false
  }
}

const loadAvailableTags = async () => {
  try {
    const data = await api.getTags()
    availableTags.value = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : [])
    if (Array.isArray(object.value?.tags)) {
      selectedTags.value = object.value.tags
        .map(t => (t && typeof t === 'object' ? t.pk : null))
        .filter(v => v != null)
    }
  } catch (error) {
    console.error('Error loading tags:', error)
  }
}

const initializeAladinLite = () => {
  // Wait for both jQuery and Aladin to be available
  const checkAndInitialize = () => {
    if (window.jQuery && window.A && object.value?.ra && object.value?.dec) {
      try {
        const aladin = window.A.aladin('#aladin-lite-div', {
          survey: 'P/DSS2/color',
          fov: 0.5,
          target: `${object.value.ra} ${object.value.dec}`,
          showZoomControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showFrame: false
        })
      } catch (error) {
        console.error('Error initializing Aladin Lite:', error)
        // Fallback: show coordinates as text
        const aladinDiv = document.getElementById('aladin-lite-div')
        if (aladinDiv) {
          aladinDiv.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #666;">
              <p>Sky Map not available</p>
              <p>Coordinates: ${formatRA(object.value.ra)} ${formatDec(object.value.dec)}</p>
            </div>
          `
        }
      }
    } else if (window.jQuery && window.A) {
      // Aladin is loaded but no coordinates, show message
      const aladinDiv = document.getElementById('aladin-lite-div')
      if (aladinDiv) {
        aladinDiv.innerHTML = `
          <div style="padding: 20px; text-align: center; color: #666;">
            <p>No coordinates available for sky map</p>
          </div>
        `
      }
    } else {
      // Retry after a short delay
      setTimeout(checkAndInitialize, 100)
    }
  }
  
  checkAndInitialize()
}

const openTagDialog = () => {
  tagDialog.value = true
}

const closeTagDialog = () => {
  tagDialog.value = false
  try {
    const el = tagCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveTags = async () => {
  try {
    const objectId = route.params.id
    await api.updateObject(objectId, { tag_ids: selectedTags.value })
    await loadObject() // Reload to get updated tags
    tagDialog.value = false
    try { notify.success('Tags updated') } catch {}
  } catch (error) {
    console.error('Error saving tags:', error)
  }
}

const toggleObservationRuns = () => {
  showObservationRuns.value = !showObservationRuns.value
}

const toggleDataFiles = () => {
  showDataFiles.value = !showDataFiles.value
}

const expandRunsIfCollapsed = () => {
  if (!showObservationRuns.value) showObservationRuns.value = true
}

const expandDataFilesIfCollapsed = () => {
  if (!showDataFiles.value) showDataFiles.value = true
}

const openNotesDialog = () => {
  newNote.value = object.value?.note || ''
  notesDialog.value = true
}

const closeNotesDialog = () => {
  notesDialog.value = false
  try {
    const el = notesCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveNotes = async () => {
  try {
    const objectId = route.params.id
    await api.updateObject(objectId, { note: newNote.value })
    await loadObject()
    notesDialog.value = false
    try { notify.success('Notes updated') } catch {}
  } catch (error) {
    console.error('Error saving notes:', error)
  }
}

// Utility functions
const formatRA = (ra) => {
  if (!ra || ra === -1) return 'N/A'
  const hours = Math.floor(ra / 15)
  const minutes = Math.floor((ra % 15) * 4)
  const seconds = ((ra % 15) * 4 - minutes) * 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`
}

const formatDec = (dec) => {
  if (!dec || dec === -1) return 'N/A'
  const sign = dec >= 0 ? '+' : '-'
  const absDec = Math.abs(dec)
  const degrees = Math.floor(absDec)
  const minutes = Math.floor((absDec - degrees) * 60)
  const seconds = ((absDec - degrees) * 60 - minutes) * 60
  return `${sign}${degrees.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`
}

const formatNotes = (notes) => {
  return notes.replace(/\n/g, '<br>')
}

const formatDate = (date) => {
  if (!date) return 'N/A'
  return new Date(date).toLocaleDateString()
}

const formatExposureTime = (time) => {
  if (!time || time === 0) return '-'
  if (time >= 1) return time.toString()
  return time.toFixed(2)
}

const formatRunName = (run) => {
  if (!run.start_time || !run.end_time) return run.name
  const start = run.start_time.split('.')[0]
  const end = run.end_time.split(' ')[1]?.split('.')[0] || run.end_time.split('.')[0]
  return `${start}-${end}`
}

const formatRunNameFromId = (name) => {
  if (!name || name.length < 8) return name
  return `${name.substring(0, 4)}-${name.substring(4, 6)}-${name.substring(6, 8)}`
}

const getStatusColor = (status) => {
  const colors = {
    'FR': 'success',
    'PR': 'warning',
    'ER': 'error',
    'NE': 'grey'
  }
  return colors[status] || 'grey'
}

const getStatusIcon = (status) => {
  const icons = {
    'FR': 'mdi-check-circle',
    'PR': 'mdi-clock',
    'ER': 'mdi-alert-circle',
    'NE': 'mdi-minus-circle'
  }
  return icons[status] || 'mdi-minus-circle'
}

const normalizedObjectTags = computed(() => {
  if (!Array.isArray(object.value?.tags)) return []
  return object.value.tags
    .map(t => (t && typeof t === 'object') ? t : null)
    .filter(Boolean)
})

// Lifecycle
onMounted(() => {
  loadObject()
})

// Filters state and helpers
const dfFilterFileName = ref('')
const dfFilterType = ref('')
const dfFilterInstrument = ref('')
const dfFilterBinning = ref(null)
const dfFilterExposureTypes = ref([])
const dfFilterSpectroscopy = ref(null)
const dfFilterExpMin = ref(null)
const dfFilterExpMax = ref(null)
// removed pixel filters

const exposureTypeOptions = [
  { title: 'Light (LI)', value: 'LI' },
  { title: 'Flat (FL)', value: 'FL' },
  { title: 'Dark (DA)', value: 'DA' },
  { title: 'Bias (BI)', value: 'BI' },
  { title: 'Unknown (UK)', value: 'UK' },
]
const spectroscopyOptions = [
  { title: 'Yes', value: true },
  { title: 'No', value: false },
]

// no pixel count parsing needed anymore

const filteredDataFiles = computed(() => {
  let items = Array.isArray(dataFiles.value) ? dataFiles.value.slice() : []
  const name = (dfFilterFileName.value || '').toLowerCase()
  if (name) items = items.filter(f => (f.file_name || '').toLowerCase().includes(name))
  const ftype = (dfFilterType.value || '').toLowerCase()
  if (ftype) items = items.filter(f => (f.file_type || '').toLowerCase().includes(ftype))
  const instr = (dfFilterInstrument.value || '').toLowerCase()
  if (instr) items = items.filter(f => (f.instrument || '').toLowerCase().includes(instr))
  if (dfFilterBinning.value) {
    items = items.filter(f => (f.binning || '').toLowerCase() === String(dfFilterBinning.value).toLowerCase())
  }
  if (Array.isArray(dfFilterExposureTypes.value) && dfFilterExposureTypes.value.length) {
    const set = new Set(dfFilterExposureTypes.value)
    items = items.filter(f => set.has(f.exposure_type))
  }
  if (dfFilterSpectroscopy.value !== null && dfFilterSpectroscopy.value !== undefined && dfFilterSpectroscopy.value !== '') {
    items = items.filter(f => Boolean(f.spectroscopy) === Boolean(dfFilterSpectroscopy.value))
  }
  if (dfFilterExpMin.value != null && dfFilterExpMin.value !== '') {
    items = items.filter(f => (f.exptime || 0) >= Number(dfFilterExpMin.value))
  }
  if (dfFilterExpMax.value != null && dfFilterExpMax.value !== '') {
    items = items.filter(f => (f.exptime || 0) <= Number(dfFilterExpMax.value))
  }
  return items
})

const resetDfFilters = () => {
  dfFilterFileName.value = ''
  dfFilterType.value = ''
  dfFilterInstrument.value = ''
  dfFilterBinning.value = null
  dfFilterExposureTypes.value = []
  dfFilterSpectroscopy.value = null
  dfFilterExpMin.value = null
  dfFilterExpMax.value = null
}

// Downloads & Preview
const selectedIds = ref([])
const downloadingAll = ref(false)
const downloadAllObjectFiles = async () => {
  try {
    downloadingAll.value = true
    // build ids from all dataFiles for this object
    const ids = (Array.isArray(dataFiles.value) ? dataFiles.value : []).map(f => f.pk || f.id)
    const url = api.getDataFilesZipUrl(ids)
    window.location.href = url
  } finally {
    downloadingAll.value = false
  }
}
const downloadSelectedObjectFiles = () => {
  if (!selectedIds.value.length) return
  const url = api.getDataFilesZipUrl(selectedIds.value)
  window.location.href = url
}
const downloadFilteredObjectFiles = () => {
  const ids = filteredDataFiles.value.map(f => f.pk || f.id)
  if (!ids.length) return
  const url = api.getDataFilesZipUrl(ids)
  window.location.href = url
}

const previewDialog = ref(false)
const previewTitle = ref('')
const previewUrl = ref('')
const previewLoading = ref(false)
const openPreview = (df) => {
  previewTitle.value = df?.file_name || 'Preview'
  previewLoading.value = true
  previewUrl.value = ''
  previewDialog.value = true
  setTimeout(() => {
    previewUrl.value = api.getDataFileThumbnailUrl(df?.pk || df?.id, 800)
  }, 0)
}
const handlePreviewLoad = () => { previewLoading.value = false }
const handlePreviewError = () => { previewLoading.value = false }

// Binning options derived from data
const binningOptions = computed(() => {
  const set = new Set((dataFiles.value || []).map(f => f?.binning).filter(Boolean))
  return Array.from(set)
})

watch(object, (val) => {
  try {
    const base = 'OST Data Archive'
    const name = val?.name || 'Object'
    document.title = `${name} – ${base}`
    const desc = `Details for object ${name}: coordinates, runs, files and tags.`
    let tag = document.querySelector('meta[name="description"]')
    if (!tag) {
      tag = document.createElement('meta')
      tag.setAttribute('name', 'description')
      document.head.appendChild(tag)
    }
    tag.setAttribute('content', desc)
  } catch {}
})
// Preview dialog template is declared implicitly by state; ensure consumers handle open/close
</script>

<style scoped>
.preview-container {
  min-height: 320px;
}
.preview-placeholder {
  height: 300px;
}
.font-mono {
  font-family: 'Courier New', monospace;
}

.gap-1 {
  gap: 4px;
}

.gap-2 {
  gap: 8px;
}

.uniform-height {
  height: 325px;
  display: flex;
  flex-direction: column;
}

.uniform-height .v-card-text {
  flex: 1;
  overflow-y: auto;
}

.expand-clickable {
  cursor: pointer;
}

.expand-clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}
</style> 