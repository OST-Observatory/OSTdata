<template>
  <div class="objects">
    <div class="container">
      <!-- Header with title -->
      <div class="d-flex align-center justify-space-between mb-4">
        <h1 class="text-h4">Objects</h1>
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
            <v-col cols="12">
              <v-card variant="outlined" class="pa-2 coordinate-filter">
                <v-card-title class="text-subtitle-1 d-flex align-center coordinate-filter-title">
                  <v-icon class="mr-2">mdi-crosshairs-gps</v-icon>
                  Coordinates
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
                      ></v-text-field>
                    </v-col>
                    <v-col cols="12" sm="4">
                      <v-row>
                        <v-col cols="8">
                          <v-text-field
                            v-model="radius"
                            label="Radius"
                            density="comfortable"
                            variant="outlined"
                            hide-details
                            type="number"
                            prepend-inner-icon="mdi-ruler"
                          ></v-text-field>
                        </v-col>
                        <v-col cols="4">
                          <v-select
                            v-model="radiusUnit"
                            :items="['arcsec', 'arcmin', 'deg']"
                            density="comfortable"
                            variant="outlined"
                            hide-details
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
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

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
        >
          <!-- Name column with link -->
          <template v-slot:item.name="{ item }">
            <router-link
              :to="`/objects/${item.pk}`"
              class="text-decoration-none primary--text"
            >
              {{ item.name }}
            </router-link>
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
                :key="run.pk"
                size="small"
                :color="getRunStatusColor(run.reduction_status)"
                class="mr-1"
                :to="run.href"
                link
              >
                {{ run.name }}
                <v-tooltip
                  :text="`Reduction status: ${run.reduction_status_display}\nFITS: ${run.n_fits}\nExposure: ${formatExposureTime(run.expo_time)}`"
                  location="top"
                >
                  <template v-slot:activator="{ props }">
                    <v-icon
                      v-bind="props"
                      size="small"
                      class="ml-1"
                    >
                      mdi-information
                    </v-icon>
                  </template>
                </v-tooltip>
              </v-chip>
            </div>
          </template>
        </v-data-table>

        <!-- Custom pagination controls -->
        <v-card-actions class="d-flex align-center justify-space-between px-4 py-2">
          <div class="d-flex align-center">
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
            ></v-btn>
            <v-btn
              icon="mdi-chevron-left"
              variant="text"
              :disabled="currentPage === 1"
              @click="handlePageChange(currentPage - 1)"
              class="mx-1"
            ></v-btn>
            <v-btn
              icon="mdi-chevron-right"
              variant="text"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(currentPage + 1)"
              class="mx-1"
            ></v-btn>
            <v-btn
              icon="mdi-page-last"
              variant="text"
              :disabled="currentPage >= totalPages"
              @click="handlePageChange(totalPages)"
              class="mx-1"
            ></v-btn>
          </div>
        </v-card-actions>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '@/services/api'
import { debounce } from 'lodash'

// Data
const currentPage = ref(1)
const itemsPerPage = ref(10)
const totalItems = ref(0)
const objects = ref([])
const loading = ref(false)
const search = ref('')
const selectedType = ref(null)
const selectedRun = ref(null)
const sortBy = ref('name')
const sortDesc = ref(false)
const observationRuns = ref([])
const loadingRuns = ref(false)
const ra = ref('')
const dec = ref('')
const radius = ref('')
const radiusUnit = ref('arcsec')

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
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Observation Runs', key: 'observation_runs', sortable: false }
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
const formatDate = (date) => {
  if (!date) return 'N/A'
  return new Date(date).toLocaleDateString()
}

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
      params.ra = convertRAToDegrees(ra.value)
      params.dec = convertDecToDegrees(dec.value)
      
      // Convert radius to arcseconds
      let radiusArcsec = parseFloat(radius.value)
      if (radiusUnit.value === 'arcmin') {
        radiusArcsec *= 60
      } else if (radiusUnit.value === 'deg') {
        radiusArcsec *= 3600
      }
      params.radius = radiusArcsec
    }
    
    const response = await api.getObjectsVuetify(params)
    objects.value = response.items
    totalItems.value = response.total
  } catch (error) {
    console.error('Error fetching objects:', error)
    objects.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    fetchObjects()
  }
}

const handleItemsPerPageChange = (value) => {
  currentPage.value = 1
  fetchObjects()
}

const handleSort = (newSortBy) => {
  if (newSortBy.length > 0) {
    const sort = newSortBy[0]
    sortBy.value = `${sort.order === 'desc' ? '-' : ''}${sort.key}`
  } else {
    sortBy.value = 'name'  // default sorting
  }
  fetchObjects()
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

// Watch for changes in filters
watch([search, selectedType, selectedRun], () => {
  currentPage.value = 1  // Reset to first page when filters change
  fetchObjects()
})

const applyCoordinateFilter = () => {
  // Convert coordinates to decimal degrees
  const raDeg = convertRAToDegrees(ra.value)
  const decDeg = convertDecToDegrees(dec.value)
  
  // Convert radius to arcseconds
  let radiusArcsec = parseFloat(radius.value)
  if (radiusUnit.value === 'arcmin') {
    radiusArcsec *= 60
  } else if (radiusUnit.value === 'deg') {
    radiusArcsec *= 3600
  }
  
  // Update the filter parameters
  currentPage.value = 1
  fetchObjects()
}

const convertRAToDegrees = (ra) => {
  const [hours, minutes, seconds] = ra.split(':').map(Number)
  return (hours + minutes / 60 + seconds / 3600) * 15
}

const convertDecToDegrees = (dec) => {
  const [degrees, minutes, seconds] = dec.split(':').map(Number)
  return degrees + minutes / 60 + seconds / 3600
}

onMounted(() => {
  fetchObjects()
  fetchObservationRuns()
})
</script>

<style scoped>
.objects {
  padding: 20px 0;
}

.v-data-table {
  background: transparent !important;
}

.v-data-table :deep(th) {
  font-weight: bold !important;
  color: var(--v-theme-primary) !important;
}

.v-data-table :deep(td) {
  padding: 8px 16px !important;
}

.v-data-table :deep(.v-data-table__wrapper) {
  overflow-x: auto;
}

.items-per-page-select {
  max-width: 100px;
}

.coordinate-filter {
  /* border-color: rgba(0, 0, 0, 0.12) !important; */
  border-color: rgba(185, 188, 194, 1) !important;
  box-shadow: 0 0 0 rgba(0, 0, 0, 0.1) !important;
}

.coordinate-filter-title {
  color: rgba(144, 150, 159, 1) !important;
}
</style> 