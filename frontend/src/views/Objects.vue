<template>
  <v-container fluid class="objects">
      <!-- Header with title -->
      <div class="d-flex align-center justify-space-between mb-4">
        <h1 class="text-h4">Objects</h1>
        <div class="d-flex align-center" style="gap: 8px" v-if="canAdmin">
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              color="primary"
              prepend-icon="mdi-eye"
              :disabled="!selected.length || !canPublish"
              @click="bulkPublishObjects(true)"
            >Publish ({{ selected.length }})</v-btn>
            <v-tooltip v-if="!canPublish || !selected.length" activator="parent" location="top">
              {{ !selected.length ? 'Select objects first' : 'No permission' }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              color="secondary"
              prepend-icon="mdi-eye-off"
              :disabled="!selected.length || !canPublish"
              @click="bulkPublishObjects(false)"
            >Unpublish ({{ selected.length }})</v-btn>
            <v-tooltip v-if="!canPublish || !selected.length" activator="parent" location="top">
              {{ !selected.length ? 'Select objects first' : 'No permission' }}
            </v-tooltip>
          </div>
          <div class="d-inline-block">
            <v-btn
              variant="outlined"
              color="warning"
              prepend-icon="mdi-merge"
              :disabled="selected.length < 2 || !canMerge"
              @click="openMergeDialog"
            >Merge ({{ selected.length }})</v-btn>
            <v-tooltip v-if="selected.length < 2 || !canMerge" activator="parent" location="top">
              {{ selected.length < 2 ? 'Select at least two objects' : 'No permission' }}
            </v-tooltip>
          </div>
        </div>
      </div>

      <!-- Search and filter bar -->
      <v-card class="mb-4">
        <v-card-text>
          <v-row>
            <v-col cols="12" sm="4">
              <v-text-field
                v-model="search"
                label="Search objects"
                prepend-inner-icon="mdi-magnify"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="4">
              <v-select
                v-model="selectedType"
                :items="objectTypes"
                item-title="title"
                item-value="value"
                label="Object Type"
                prepend-inner-icon="mdi-filter"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
              ></v-select>
            </v-col>
            <v-col cols="12" sm="4">
              <v-autocomplete
                v-model="selectedRun"
                :items="observationRuns"
                item-title="name"
                item-value="pk"
                label="Observation Run"
                prepend-inner-icon="mdi-telescope"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                :loading="loadingRuns"
                :filter="customFilter"
                clearable
                return-object
              >
              </v-autocomplete>
            </v-col>
          </v-row>
          <v-row class="mt-2">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="nLightMin"
                type="number"
                label="Lights min"
                prepend-inner-icon="mdi-brightness-5"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
                clearable
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model.number="nLightMax"
                type="number"
                label="Lights max"
                prepend-inner-icon="mdi-brightness-7"
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
              <v-card variant="outlined" class="pa-2 coordinate-filter" role="group" aria-labelledby="coord-title">
                <v-card-title class="text-subtitle-1 d-flex align-center coordinate-filter-title">
                  <v-icon class="mr-2" aria-hidden="true">mdi-crosshairs-gps</v-icon>
                  <span id="coord-title">Coordinates</span>
                </v-card-title>
                <v-card-text>
                  <v-row>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model="ra"
                        label="RA"
                        density="comfortable"
                        variant="outlined"
                        hide-details
                        placeholder="HH:MM:SS"
                        prepend-inner-icon="mdi-alpha-r-circle"
                        :rules="raRules"
                        autocomplete="off"
                        inputmode="text"
                      ></v-text-field>
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-text-field
                        v-model="dec"
                        label="Dec"
                        density="comfortable"
                        variant="outlined"
                        hide-details
                        placeholder="DD:MM:SS"
                        prepend-inner-icon="mdi-alpha-d-circle"
                        :rules="decRules"
                        autocomplete="off"
                        inputmode="text"
                      ></v-text-field>
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-row>
                        <v-col cols="8" sm="7" xs="8">
                          <v-text-field
                            v-model="radius"
                            label="Radius"
                            density="comfortable"
                            variant="outlined"
                            hide-details
                            type="number"
                            prepend-inner-icon="mdi-ruler"
                            :rules="radiusRules"
                            autocomplete="off"
                            inputmode="decimal"
                          ></v-text-field>
                        </v-col>
                        <v-col cols="4" sm="5" xs="4">
                          <v-select
                            v-model="radiusUnit"
                            :items="['arcsec', 'arcmin', 'deg']"
                            density="comfortable"
                            variant="outlined"
                            hide-details
                            autocomplete="off"
                          ></v-select>
                        </v-col>
                      </v-row>
                    </v-col>
                  </v-row>
                  <v-row class="mt-2">
                    <v-col cols="12">
                      <v-btn
                        block
                        color="primary"
                        @click="applyCoordinateFilter"
                        :disabled="!ra || !dec || !radius"
                        prepend-icon="mdi-filter-check"
                      >
                        Apply Coordinates Filter
                      </v-btn>
                    </v-col>
                    <v-col cols="12" class="mt-1">
                      <v-btn
                        block
                        variant="text"
                        color="secondary"
                        @click="resetFilters"
                        prepend-icon="mdi-filter-remove"
                      >
                        Reset Filters
                      </v-btn>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- Error state -->
      <v-alert v-if="objectsError" type="error" variant="tonal" class="mb-3">{{ objectsError }}</v-alert>

      <!-- Objects table -->
      <v-card>
        <v-data-table
          :headers="headers"
          :items="objects"
          :items-length="totalItems"
          :items-per-page="itemsPerPage === -1 ? totalItems : itemsPerPage"
          :loading="loading"
          :sort-by="[{ key: sortBy.replace('-', ''), order: sortBy.startsWith('-') ? 'desc' : 'asc' }]"
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
          @update:selected="onObjectsSelected"
          @update:modelValue="onObjectsSelected"
          @update:selection="onObjectsSelected"
          @click="onObjectsTableClick"
          class="custom-table"
        >
          <template #loading>
            <LoadingState type="table" />
          </template>

          <template #no-data>
            <EmptyState text="No objects found." />
          </template>
          <!-- Name column with link -->
          <template v-slot:item.name="{ item }">
            <v-tooltip :text="item.name" location="top">
              <template #activator="{ props }">
                <router-link
                  v-bind="props"
                  :to="`/objects/${item.pk}`"
                  class="text-decoration-none primary--text table-link cell-truncate"
                >
                  {{ item.name }}
                </router-link>
              </template>
            </v-tooltip>
          </template>

          <!-- Type column with chip -->
          <template v-slot:item.object_type="{ item }">
            {{ item.object_type_display }}
          </template>

          <!-- RA column -->
          <template v-slot:item.ra="{ item }">
            {{ formatRA(item.ra) }}
          </template>

          <!-- Dec column -->
          <template v-slot:item.dec="{ item }">
            {{ formatDec(item.dec) }}
          </template>

          <!-- Lights column -->
          <template v-slot:item.n_light="{ item }">
            {{ item.n_light ?? '—' }}
          </template>

          <!-- Light exposure time column -->
          <template v-slot:item.light_expo_time="{ item }">
            {{ formatExposureTime(item.light_expo_time || 0) }}
          </template>

          <!-- Photometry column -->
          <template v-slot:item.photometry="{ item }">
            <v-icon :color="item.photometry ? 'success' : 'disabled'">{{ item.photometry ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
          </template>

          <!-- Spectroscopy column -->
          <template v-slot:item.spectroscopy="{ item }">
            <v-icon :color="item.spectroscopy ? 'success' : 'disabled'">{{ item.spectroscopy ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
          </template>

          <!-- Created at column -->
          <template v-slot:item.created_at="{ item }">
            {{ formatDate(item.created_at) }}
          </template>

          <!-- Tags column -->
          <template v-slot:item.tags="{ item }">
            <v-chip
              v-for="tag in item.tags"
              :key="tag"
              size="small"
              class="mr-1"
            >
              {{ tag }}
            </v-chip>
          </template>

          <!-- Observation Runs column -->
          <template v-slot:item.observation_runs="{ item }">
            <div class="d-flex flex-wrap gap-1">
              <v-chip
                v-for="run in item.observation_run"
                :key="run.pk || run.id || run.name"
                size="x-small"
                variant="outlined"
                color="primary"
                class="mr-1"
                :to="(run.pk || run.id) ? (`/observation-runs/${run.pk || run.id}`) : undefined"
                link
              >
                {{ run.name }}
              </v-chip>
            </div>
          </template>

          <template v-slot:item.actions="{ item }">
            <v-btn
              v-if="canEdit"
              icon
              variant="text"
              color="primary"
              class="action-btn"
              @click="openEditDialog(item)"
              :aria-label="`Edit object ${item.name}`"
            >
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn
              v-if="canDelete"
              icon
              variant="text"
              color="error"
              class="action-btn"
              @click="removeObject(item)"
              :aria-label="`Delete object ${item.name}`"
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
      <!-- Merge dialog -->
      <v-dialog v-model="mergeOpen" max-width="520">
        <v-card>
          <v-card-title class="text-h6">Merge Objects</v-card-title>
          <v-card-text>
            <div class="mb-2">Select the target object to keep:</div>
            <v-radio-group v-model="mergeTargetId" density="comfortable">
              <v-radio
                v-for="it in selected"
                :key="it.pk"
                :label="`${it.name} (#${it.pk})`"
                :value="it.pk"
              />
            </v-radio-group>
            <v-checkbox
              v-model="mergeCombineTags"
              label="Combine tags"
              density="comfortable"
              hide-details
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="mergeOpen = false">Cancel</v-btn>
            <v-btn color="primary" @click="confirmMerge" :disabled="!mergeTargetId">Merge</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
      <!-- Edit dialog -->
      <v-dialog v-model="editOpen" max-width="720">
        <v-card>
          <v-card-title class="text-h6">Edit Object</v-card-title>
          <v-card-text>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6">
                <v-text-field v-model="editForm.name" label="Name" density="comfortable" variant="outlined" hide-details />
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="editForm.object_type"
                  :items="objectTypeItems"
                  item-title="title"
                  item-value="value"
                  label="Object Type"
                  density="comfortable"
                  variant="outlined"
                  hide-details
                  clearable
                />
              </v-col>
            </v-row>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6">
                <v-text-field v-model.number="editForm.ra" type="number" step="0.0001" label="RA (deg)" density="comfortable" variant="outlined" hide-details />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field v-model.number="editForm.dec" type="number" step="0.0001" label="Dec (deg)" density="comfortable" variant="outlined" hide-details />
              </v-col>
            </v-row>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6">
                <v-switch class="hi-contrast-switch" v-model="editForm.is_public" inset hide-details color="primary" :label="`Public`" />
              </v-col>
              <v-col cols="12" sm="6">
                <v-switch class="hi-contrast-switch" v-model="editForm.is_main" inset hide-details color="primary" :label="`Main target`" />
              </v-col>
              <v-col cols="12" sm="6">
                <v-switch class="hi-contrast-switch" v-model="editForm.photometry" inset hide-details color="primary" :label="`Photometry`" />
              </v-col>
              <v-col cols="12" sm="6">
                <v-switch class="hi-contrast-switch" v-model="editForm.spectroscopy" inset hide-details color="primary" :label="`Spectroscopy`" />
              </v-col>
            </v-row>
            <v-row dense>
              <v-col cols="12">
                <v-textarea v-model="editForm.note" label="Note" rows="3" auto-grow density="comfortable" variant="outlined" hide-details />
              </v-col>
              <v-col cols="12">
                <v-autocomplete
                  v-model="editForm.tag_ids"
                  :items="allTags"
                  item-title="name"
                  item-value="id"
                  label="Tags"
                  multiple
                  chips
                  closable-chips
                  density="comfortable"
                  variant="outlined"
                  hide-details
                />
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="editOpen = false">Cancel</v-btn>
            <v-btn color="primary" variant="elevated" @click="saveEdit" :loading="editSaving">Save</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useQuerySync } from '@/composables/useQuerySync'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { debounce } from 'lodash'
import { formatDateTime } from '@/utils/datetime'
import { useNotifyStore } from '@/store/notify'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

// Data
const router = useRouter()
const route = useRoute()

const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const objects = ref([])
const selected = ref([])
const loading = ref(false)
const objectsError = ref('')
const search = ref('')
const selectedType = ref(null)
const selectedRun = ref(null)
const sortBy = ref('name')
const sortDesc = ref(false)
const observationRuns = ref([])
const loadingRuns = ref(false)
const photometryFilter = ref(null)
const spectroscopyFilter = ref(null)
const nLightMin = ref(null)
const nLightMax = ref(null)
const ra = ref('')
const dec = ref('')
const radius = ref('')
const radiusUnit = ref('arcsec')
const notify = useNotifyStore()
const authStore = useAuthStore()
const canAdmin = computed(() => authStore.isAdmin)
const canEdit = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_objects_edit') || authStore.hasPerm('acl_objects_edit'))
const canMerge = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_objects_merge') || authStore.hasPerm('acl_objects_merge'))
const canDelete = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_objects_delete') || authStore.hasPerm('acl_objects_delete'))
const canPublish = canEdit
const boolFilterItems = [
  { title: 'Not selected', value: null },
  { title: 'Yes', value: true },
  { title: 'No', value: false },
]

// Query param helpers
const parseIntParam = (v, fallback) => {
  const n = Number.parseInt(String(v))
  return Number.isFinite(n) && n > 0 ? n : fallback
}

const truthy = (v) => v !== undefined && v !== null && v !== ''

const serializeQuery = () => {
  const q = {}
  q.page = currentPage.value
  q.pageSize = itemsPerPage.value
  if (search.value) q.q = search.value
  if (selectedType.value) q.type = selectedType.value
  if (selectedRun.value?.pk) q.run = selectedRun.value.pk
  if (sortBy.value) q.sort = sortBy.value
  if (sortDesc.value) q.desc = '1'
  if (ra.value) q.ra = ra.value
  if (dec.value) q.dec = dec.value
  if (radius.value) q.radius = radius.value
  if (radiusUnit.value && radiusUnit.value !== 'arcsec') q.runit = radiusUnit.value
  return q
}

const applyQuery = () => {
  const q = route.query
  currentPage.value = parseIntParam(q.page, 1)
  itemsPerPage.value = parseIntParam(q.pageSize, 10)
  if (truthy(q.q)) search.value = String(q.q)
  if (truthy(q.type)) selectedType.value = String(q.type)
  if (truthy(q.run)) selectedRun.value = { pk: String(q.run), name: String(q.run) }
  if (truthy(q.sort)) sortBy.value = String(q.sort)
  sortDesc.value = q.desc === '1'
  if (truthy(q.ra)) ra.value = String(q.ra)
  if (truthy(q.dec)) dec.value = String(q.dec)
  if (truthy(q.radius)) radius.value = String(q.radius)
  if (truthy(q.runit)) radiusUnit.value = String(q.runit)
}

// Computed properties
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

// Headers for the data table
const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Object Type', key: 'object_type', sortable: true },
  { title: 'RA', key: 'ra', sortable: true },
  { title: 'Dec', key: 'dec', sortable: true },
  { title: 'Lights', key: 'n_light', sortable: false },
  { title: 'Light Exp. Time', key: 'light_expo_time', sortable: false },
  { title: 'Photometry', key: 'photometry', sortable: false },
  { title: 'Spectroscopy', key: 'spectroscopy', sortable: false },
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Observation Runs', key: 'observation_runs', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false }
]

// Object types for the filter
const objectTypes = [
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star Cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Star', value: 'ST' },
  { title: 'Solar System', value: 'SO' },
  { title: 'Other', value: 'OT' },
  { title: 'Unknown', value: 'UK' }
]

// Sort options
const sortOptions = [
  { title: 'Name', value: 'name' },
  { title: 'Object Type', value: 'object_type' },
  { title: 'RA', value: 'ra' },
  { title: 'Dec', value: 'dec' }
]

// Methods
const formatDate = (date) => formatDateTime(date, { dateStyle: 'short' })

const formatRA = (ra) => {
  if (ra === undefined || ra === null) return 'N/A'
  const hours = Math.floor(ra / 15)
  const minutes = Math.floor((ra % 15) * 4)
  const seconds = ((ra % 15) * 4 - minutes) * 60
  return `${hours.toString().padStart(2, '0')}h ${minutes.toString().padStart(2, '0')}m ${seconds.toFixed(1)}s`
}

const formatDec = (dec) => {
  if (dec === undefined || dec === null) return 'N/A'
  const sign = dec >= 0 ? '+' : '-'
  const absDec = Math.abs(dec)
  const degrees = Math.floor(absDec)
  const minutes = Math.floor((absDec - degrees) * 60)
  const seconds = ((absDec - degrees) * 60 - minutes) * 60
  return `${sign}${degrees.toString().padStart(2, '0')}° ${minutes.toString().padStart(2, '0')}' ${seconds.toFixed(1)}"`
}

const fetchObservationRuns = async () => {
  try {
    loadingRuns.value = true
    const response = await api.getAllObservationRuns()
    
    // Create a Map to ensure unique names
    const uniqueRuns = new Map()
    response.results.forEach(run => {
      if (!uniqueRuns.has(run.name)) {
        uniqueRuns.set(run.name, run)
      }
    })
    
    // Convert Map values back to array
    observationRuns.value = Array.from(uniqueRuns.values())
  } catch (error) {
    console.error('Error fetching observation runs:', error)
    observationRuns.value = []
  } finally {
    loadingRuns.value = false
  }
}

const fetchObjects = async () => {
  try {
    loading.value = true
    objectsError.value = ''
    const params = {
      page: currentPage.value,
      itemsPerPage: itemsPerPage.value === -1 ? 10000 : itemsPerPage.value,
      sortBy: sortBy.value,
      sortDesc: sortDesc.value,
      search: search.value,
      object_type: selectedType.value
    }
    
    // Add observation run filter if a run is selected
    if (selectedRun.value) {
      params.observation_run = selectedRun.value.pk
    }
    
    // Add coordinate filter if coordinates are provided
    if (ra.value && dec.value && radius.value) {
      const raDeg = safeConvertRA(ra.value)
      const decDeg = safeConvertDec(dec.value)
      const rad = Number.parseFloat(String(radius.value))
      if (raDeg !== null && decDeg !== null && Number.isFinite(rad) && rad > 0) {
        params.ra = raDeg
        params.dec = decDeg
        let radiusArcsec = rad
        if (radiusUnit.value === 'arcmin') radiusArcsec *= 60
        else if (radiusUnit.value === 'deg') radiusArcsec *= 3600
        params.radius = radiusArcsec
      }
    }
    if (photometryFilter.value !== null && photometryFilter.value !== undefined) {
      params.photometry = photometryFilter.value
    }
    if (spectroscopyFilter.value !== null && spectroscopyFilter.value !== undefined) {
      params.spectroscopy = spectroscopyFilter.value
    }
    if (nLightMin.value !== null && nLightMin.value !== undefined && nLightMin.value !== '') {
      params.n_light_min = nLightMin.value
    }
    if (nLightMax.value !== null && nLightMax.value !== undefined && nLightMax.value !== '') {
      params.n_light_max = nLightMax.value
    }
    
    const response = await api.getObjectsVuetify(params)
    const items = Array.isArray(response?.items) ? response.items : []
    // Normalize primary key for selection handling
    objects.value = items.map(it => ({ ...it, pk: it.pk ?? it.id }))
    totalItems.value = response.total || objects.value.length
  } catch (error) {
    console.error('Error fetching objects:', error)
    objects.value = []
    totalItems.value = 0
    objectsError.value = 'Failed to load objects.'
  } finally {
    loading.value = false
  }
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    syncQueryAndFetch()
  }
}

const handleItemsPerPageChange = (value) => {
  currentPage.value = 1
  syncQueryAndFetch()
}

const handleSort = (newSortBy) => {
  if (newSortBy.length > 0) {
    const sort = newSortBy[0]
    sortBy.value = `${sort.order === 'desc' ? '-' : ''}${sort.key}`
  } else {
    sortBy.value = 'name'  // default sorting
  }
  syncQueryAndFetch()
}

const getRunStatusColor = (status) => {
  const statusColors = {
    'NE': 'grey',      // New
    'PR': 'blue',      // Processing
    'CO': 'green',     // Complete
    'FA': 'red',       // Failed
    'PA': 'orange'     // Partial
  }
  return statusColors[status] || 'grey'
}

const formatExposureTime = (seconds) => {
  if (!seconds) return '0s'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  
  let result = ''
  if (hours > 0) result += `${hours}h `
  if (minutes > 0) result += `${minutes}m `
  if (remainingSeconds > 0 || result === '') result += `${remainingSeconds}s`
  return result.trim()
}

// Add this new function for custom filtering
const customFilter = (item, queryText, itemText) => {
  const textOne = item.raw.name.toLowerCase()
  const searchText = queryText.toLowerCase()
  return textOne.indexOf(searchText) > -1
}

// Debounced sync for text search
const debouncedSyncQuery = debounce(() => {
  syncQueryAndFetch()
}, 300)

// Watchers: debounce text search; others immediately
watch(search, () => {
  currentPage.value = 1
  debouncedSyncQuery()
})

watch([selectedType, selectedRun], () => {
  currentPage.value = 1
  syncQueryAndFetch()
})

const applyCoordinateFilter = () => {
  currentPage.value = 1
  syncQueryAndFetch()
}

const resetFilters = () => {
  search.value = ''
  selectedType.value = null
  selectedRun.value = null
  ra.value = ''
  dec.value = ''
  radius.value = ''
  radiusUnit.value = 'arcsec'
  currentPage.value = 1
  sortBy.value = 'name'
  sortDesc.value = false
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

const removeObject = async (item) => {
  if (!canEdit.value || !item?.pk) return
  if (!confirm(`Delete object ${item.name}? This cannot be undone.`)) return
  try {
    await api.deleteObject(item.pk)
    notify.success('Object deleted')
    await fetchObjects()
  } catch (e) {
    console.error(e)
    notify.error('Delete failed')
  }
}

const bulkPublishObjects = async (makePublic) => {
  if (!canMerge.value || !selected.value.length) return
  const ids = selected.value.map(x => x.pk).filter(Boolean)
  try {
    await Promise.all(ids.map(id => api.updateObject(id, { is_public: !!makePublic })))
    notify.success(`${makePublic ? 'Published' : 'Unpublished'} ${ids.length} object(s)`) 
    selected.value = []
    await fetchObjects()
  } catch (e) {
    notify.error('Bulk update failed')
  }
}

const mergeOpen = ref(false)
const mergeTargetId = ref(null)
const mergeCombineTags = ref(true)
const openMergeDialog = () => {
  if (!selected.value.length) return
  mergeTargetId.value = selected.value[0]?.pk || null
  mergeCombineTags.value = true
  mergeOpen.value = true
}
const confirmMerge = async () => {
  const ids = selected.value.map(x => x.pk).filter(Boolean)
  const tgt = mergeTargetId.value
  if (!tgt || ids.length < 2) {
    mergeOpen.value = false
    return
  }
  const sources = ids.filter(id => id !== tgt)
  if (!confirm(`Merge ${sources.length} object(s) into #${tgt}? This will move relations and delete sources.`)) return
  try {
    await api.mergeObjects(tgt, sources, mergeCombineTags.value)
    notify.success(`Merged ${sources.length} object(s) into #${tgt}`)
    mergeOpen.value = false
    selected.value = []
    await fetchObjects()
  } catch (e) {
    notify.error('Merge failed')
  }
}
const safeConvertRA = (value) => {
  if (!value || typeof value !== 'string') return null
  const m = value.trim().match(/^([0-1]?\d|2[0-3]):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$/)
  if (!m) return null
  const hours = Number(m[1])
  const minutes = Number(m[2])
  const seconds = Number(m[3])
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) return null
  if (minutes >= 60 || seconds >= 60) return null
  return (hours + minutes / 60 + seconds / 3600) * 15
}

const safeConvertDec = (value) => {
  if (!value || typeof value !== 'string') return null
  const m = value.trim().match(/^([+\-]?)(\d{1,2}):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$/)
  if (!m) return null
  const sign = m[1] === '-' ? -1 : 1
  const degrees = Number(m[2])
  const minutes = Number(m[3])
  const seconds = Number(m[4])
  if (!Number.isFinite(degrees) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) return null
  if (degrees > 90 || minutes >= 60 || seconds >= 60) return null
  const dec = degrees + minutes / 60 + seconds / 3600
  return sign * dec
}

const { applyQuery: applyQuerySync, syncQueryAndFetch } = useQuerySync(
  { page: currentPage, pageSize: itemsPerPage, q: search, type: selectedType, run: selectedRun, phot: photometryFilter, spec: spectroscopyFilter, nlmin: nLightMin, nlmax: nLightMax, sort: sortBy, desc: sortDesc, ra, dec, radius, runit: radiusUnit },
  [
    { key: 'page', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && n > 0 ? n : 1 }, defaultValue: 1 },
    { key: 'pageSize', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && (n > 0 || n === -1) ? n : 10 }, defaultValue: 10 },
    { key: 'q' },
    { key: 'type' },
    { key: 'run', toQuery: (v) => v?.pk || v, fromQuery: (v) => v ? { pk: String(v), name: String(v) } : null },
    { key: 'phot', toQuery: (v) => (v === true ? '1' : v === false ? '0' : undefined), fromQuery: (v) => (v === '1' ? true : v === '0' ? false : null) },
    { key: 'spec', toQuery: (v) => (v === true ? '1' : v === false ? '0' : undefined), fromQuery: (v) => (v === '1' ? true : v === '0' ? false : null) },
    { key: 'nlmin', toQuery: (v) => (v || v === 0 ? String(v) : undefined), fromQuery: (v) => (v !== undefined ? Number(v) : null) },
    { key: 'nlmax', toQuery: (v) => (v || v === 0 ? String(v) : undefined), fromQuery: (v) => (v !== undefined ? Number(v) : null) },
    { key: 'sort', defaultValue: 'name' },
    { key: 'desc', fromQuery: (v) => v === '1', toQuery: (v) => (v ? '1' : undefined) },
    { key: 'ra' },
    { key: 'dec' },
    { key: 'radius' },
    { key: 'runit', defaultValue: 'arcsec' },
  ],
  fetchObjects
)

// Vuetify rules for inputs
const raRules = [
  (v) => !v || /^([0-1]?\d|2[0-3]):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$/.test(String(v).trim()) || 'Format HH:MM:SS'
]
const decRules = [
  (v) => !v || /^[+\-]?(\d{1,2}):([0-5]?\d):([0-5]?\d(?:\.\d+)?)$/.test(String(v).trim()) || 'Format ±DD:MM:SS'
]
const radiusRules = [
  (v) => !v || (Number.isFinite(Number(v)) && Number(v) > 0) || 'Enter a positive number'
]

onMounted(() => {
  console.log('[Objects] component mounted')
  applyQuerySync()
  fetchObjects()
  fetchObservationRuns()
})

// Debug: observe selection changes
watch(selected, (val) => {
  try {
    console.log('[Objects] selected (watch):', Array.isArray(val) ? val.map(v => v?.pk || v?.id) : val)
  } catch (e) {}
}, { deep: true })

// Debug: listen to table's update event
const onObjectsSelected = (val) => {
  try {
    console.log('[Objects] update:selected event:', Array.isArray(val) ? val.map(v => v?.pk || v?.id || v) : val)
  } catch (e) {}
}

// Debug: table click events
const onObjectsTableClick = (e) => {
  try {
    console.log('[Objects] table click', e?.target?.tagName, e?.target?.className)
  } catch (e) {}
}

// Debug: observe data loading
watch(objects, (val) => {
  try {
    console.log('[Objects] items loaded:', Array.isArray(val) ? val.length : 0, 'first:', val?.[0] ? Object.keys(val[0]) : null)
  } catch (e) {}
})

// Edit meta
const editOpen = ref(false)
const editSaving = ref(false)
const editForm = ref({
  pk: null,
  name: '',
  object_type: '',
  ra: null,
  dec: null,
  is_public: true,
  is_main: true,
  photometry: false,
  spectroscopy: false,
  note: '',
  tag_ids: [],
})
const objectTypeItems = [
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star Cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Star', value: 'ST' },
  { title: 'Solar System', value: 'SO' },
  { title: 'Other', value: 'OT' },
  { title: 'Unknown', value: 'UK' },
]
const allTags = ref([])
const loadTagsIfNeeded = async () => {
  if (allTags.value.length) return
  try {
    const res = await api.getTags({ limit: 1000 })
    const items = Array.isArray(res?.results) ? res.results : (Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []))
    allTags.value = items.map(t => ({ id: t.id ?? t.pk, name: t.name }))
  } catch (e) {
    allTags.value = []
  }
}
const openEditDialog = async (item) => {
  await loadTagsIfNeeded()
  editForm.value = {
    pk: item.pk,
    name: item.name || '',
    object_type: item.object_type || null,
    ra: item.ra ?? null,
    dec: item.dec ?? null,
    is_public: item.is_public ?? true,
    is_main: item.is_main ?? true,
    photometry: item.photometry ?? false,
    spectroscopy: item.spectroscopy ?? false,
    note: item.note || '',
    tag_ids: Array.isArray(item.tag_ids) ? item.tag_ids.map(x => (x?.id ?? x)) : [],
  }
  editOpen.value = true
}
const saveEdit = async () => {
  const id = editForm.value.pk
  if (!id) { editOpen.value = false; return }
  editSaving.value = true
  try {
    const payload = {
      name: editForm.value.name,
      object_type: editForm.value.object_type,
      ra: editForm.value.ra,
      dec: editForm.value.dec,
      is_public: !!editForm.value.is_public,
      is_main: !!editForm.value.is_main,
      photometry: !!editForm.value.photometry,
      spectroscopy: !!editForm.value.spectroscopy,
      note: editForm.value.note || '',
      tag_ids: editForm.value.tag_ids || [],
    }
    await api.updateObject(id, payload)
    notify.success('Object updated')
    editOpen.value = false
    await fetchObjects()
  } catch (e) {
    notify.error('Update failed')
  } finally {
    editSaving.value = false
  }
}
</script>

<style scoped>
.objects {
  padding: 20px 0;
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

.v-data-table {
  background: transparent !important;
}

.v-data-table :deep(th) {
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}

.v-data-table :deep(td) {
  padding: 8px 16px !important;
}

.v-data-table :deep(.v-data-table__wrapper) {
  overflow-x: auto;
  overflow-y: visible;
}

/* Unify link hover/focus styles like other tables */
:deep(.table-link) {
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

:deep(.table-link:hover) {
  color: var(--v-theme-primary-dark);
  background-color: rgba(var(--v-theme-primary-light), 0.9);
  transform: translateY(-1px);
}

:deep(.table-link::after) {
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

:deep(.table-link:hover::after) {
  transform: scaleX(1);
}

.items-per-page-select {
  max-width: 100px;
}

/* Focus ring for pagination and important controls */
.pagination-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 50%;
}

.coordinate-filter {
  /* border-color: rgba(0, 0, 0, 0.12) !important; */
  border-color: rgba(185, 188, 194, 1) !important;
  box-shadow: 0 0 0 rgba(0, 0, 0, 0.1) !important;
}

.coordinate-filter-title {
  color: rgba(144, 150, 159, 1) !important;
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