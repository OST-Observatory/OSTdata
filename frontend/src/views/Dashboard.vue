<template>
  <v-container fluid class="dashboard">
      <div class="d-flex align-center justify-space-between mb-4">
        <h1 class="text-h4">Dashboard</h1>
      </div>
      <v-alert
        v-if="error"
        type="error"
        variant="tonal"
        class="mb-4"
      >
        {{ error }}
        <v-btn class="ml-2" size="small" color="primary" @click="handleRetry">Retry</v-btn>
      </v-alert>
      <!-- Overview -->
      <v-card class="mt-4 overview-card">
        <v-card-title class="py-2 primary white--text">Overview</v-card-title>
        <v-card-text class="pt-0">
          <template v-if="loading">
            <v-row dense>
              <v-col cols="12" sm="6" md="4" v-for="n in 3" :key="`ov1-${n}`">
                <v-skeleton-loader type="card"></v-skeleton-loader>
              </v-col>
            </v-row>
            <v-row dense class="mt-2">
              <v-col cols="12" sm="6" md="2" v-for="n in 6" :key="`ov2-${n}`">
                <v-skeleton-loader type="card"></v-skeleton-loader>
              </v-col>
            </v-row>
          </template>
          <!-- First Row: Observation Runs and Total Objects -->
          <v-row dense v-else>
            <v-col cols="12" sm="6" md="4">
              <v-card variant="outlined" class="h-100 stat-card" :to="{ path: '/observation-runs' }" link>
                <v-card-text class="text-center pa-2">
                  <div class="text-subtitle-2 mb-1 text-primary">Observation Runs</div>
                  <div class="text-h6 primary--text">{{ stats.runs?.total || 0 }}</div>
                  <div class="text-caption text-secondary">
                    {{ stats.runs?.total_last_week || 0 }} new in last 7 days
                  </div>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" sm="6" md="4">
              <v-card variant="outlined" class="h-100 stat-card" :to="{ path: '/objects' }" link>
                <v-card-text class="text-center pa-2">
                  <div class="text-subtitle-2 mb-1 text-primary">Total Objects</div>
                  <div class="text-h6 primary--text">{{ stats.objects?.total || 0 }}</div>
                  <div class="text-caption text-secondary">
                    {{ stats.objects?.total_last_week || 0 }} new in last 7 days
                  </div>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" sm="6" md="4">
              <v-card variant="outlined" class="h-100 stat-card">
                <v-card-text class="text-center pa-2">
                  <div class="text-subtitle-2 mb-1 text-primary">Files</div>
                  <div class="text-h6 primary--text">{{ stats.files?.total || 0 }}</div>
                  <div class="text-caption text-secondary">
                    {{ stats.files?.storage_size?.toFixed(2) || 0 }} TB
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <!-- Second Row: All other object statistics -->
          <v-row dense class="mt-2" v-if="!loading">
            <v-col cols="12" sm="6" md="2" v-for="(count, type) in objectTypes" :key="type">
              <v-card
                variant="outlined"
                class="h-100 stat-card"
                :to="{ path: '/objects', query: { type: mapObjectTypeToCode(type) } }"
                link
              >
                <v-card-text class="text-center pa-2">
                  <div class="text-subtitle-2 mb-1 text-primary">{{ type }}</div>
                  <div class="text-h6 primary--text">{{ stats.objects?.[count] || 0 }}</div>
                  <div class="text-caption text-secondary">
                    {{ Math.round((stats.objects?.[count] || 0) / (stats.objects?.total || 1) * 100) }}% of total
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- Recent Objects and Observation Runs -->
      <v-row class="mt-4">
        <v-col cols="12" md="6">
          <v-card class="recent-card">
            <v-card-title class="primary white--text">Recent Objects</v-card-title>
            <v-card-text>
              <template v-if="loading">
                <v-skeleton-loader type="table"></v-skeleton-loader>
              </template>
              <template v-else>
                <v-table class="custom-table" v-if="recentObjects && recentObjects.length">
                  <thead>
                    <tr>
                      <th class="text-primary" scope="col">Name</th>
                      <th class="text-primary" scope="col">Type</th>
                      <th class="text-primary" scope="col">Last Modified</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="object in recentObjects" :key="object.pk || object.id">
                      <td>
                        <v-tooltip :text="object.name" location="top">
                          <template #activator="{ props }">
                            <router-link v-bind="props" :to="`/objects/${object.pk || object.id}`" class="text-decoration-none primary--text cell-truncate">
                              {{ object.name }}
                            </router-link>
                          </template>
                        </v-tooltip>
                      </td>
                      <td class="text-secondary">{{ object.object_type_display }}</td>
                      <td class="text-secondary">{{ formatDate(object.last_modified) }}</td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-else class="text-caption text-secondary">No recent objects.</div>
              </template>
            </v-card-text>
            <v-card-actions class="justify-end">
              <v-btn variant="text" color="primary" to="/objects">View all</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>

        <v-col cols="12" md="6">
          <v-card class="recent-card">
            <v-card-title class="primary white--text">Recent Observation Runs</v-card-title>
            <v-card-text>
              <template v-if="loading">
                <v-skeleton-loader type="table"></v-skeleton-loader>
              </template>
              <template v-else>
                <v-table class="custom-table" v-if="recentRuns && recentRuns.length">
                  <thead>
                    <tr>
                      <th class="text-primary" scope="col">Name</th>
                      <th class="text-primary" scope="col">Date</th>
                      <th class="text-primary" scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="run in recentRuns" :key="run.pk || run.id">
                      <td>
                        <v-tooltip :text="run.name" location="top">
                          <template #activator="{ props }">
                            <router-link v-bind="props" :to="`/observation-runs/${run.pk || run.id}`" class="text-decoration-none primary--text cell-truncate">
                              {{ run.name }}
                            </router-link>
                          </template>
                        </v-tooltip>
                      </td>
                      <td class="text-secondary">{{ formatDate(run.start_time || run.date) }}</td>
                      <td>
                        <v-chip
                          :color="getStatusColor(run.status || run.reduction_status)"
                          size="small"
                          class="status-chip"
                        >
                          {{ run.status || run.reduction_status || 'n/a' }}
                        </v-chip>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-else class="text-caption text-secondary">No recent runs.</div>
              </template>
            </v-card-text>
            <v-card-actions class="justify-end">
              <v-btn variant="text" color="primary" to="/observation-runs">View all</v-btn>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <!-- Data reduction statistics -->
      <v-card class="mt-4 reduction-card">
        <v-card-title class="py-2 primary white--text">Data Reduction</v-card-title>
        <v-card-text class="pt-0">
          <v-row dense>
            <v-col cols="12" sm="6" md="3" v-for="(count, status) in reductionStatuses" :key="status">
              <v-card variant="outlined" class="h-100 stat-card">
                <v-card-text class="text-center pa-2">
                  <div class="text-subtitle-2 mb-1 text-primary">{{ status }}</div>
                  <div class="text-h6 primary--text">{{ stats.runs?.[count] || 0 }}</div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- File Statistics -->
      <v-card class="mt-4 file-stats-card">
        <v-card-title class="py-2 primary white--text">File Statistics</v-card-title>
        <v-card-text class="pt-0">
          <!-- File Types -->
          <div class="stat-section">
            <div class="stat-section-title text-subtitle-2 text-primary mb-2">File Formats</div>
            <v-row dense>
              <v-col cols="12" sm="6" md="2" class="file-stat-col" v-for="(count, type) in fileTypes" :key="type">
                <v-card variant="outlined" class="h-100 stat-card">
                  <v-card-text class="text-center pa-2">
                    <div class="text-subtitle-2 mb-1 text-primary">{{ type }}</div>
                    <div class="text-h6 primary--text">{{ stats.files?.[count] || 0 }}</div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </div>

          <!-- Data Types -->
          <div class="stat-section">
            <div class="stat-section-title text-subtitle-2 text-primary mb-2">Data Types</div>
            <v-row dense>
              <v-col cols="12" sm="6" md="2" class="file-stat-col" v-for="(count, type) in dataTypes" :key="type">
                <v-card variant="outlined" class="h-100 stat-card">
                  <v-card-text class="text-center pa-2">
                    <div class="text-subtitle-2 mb-1 text-primary">{{ type }}</div>
                    <div class="text-h6 primary--text">{{ stats.files?.[count] || 0 }}</div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </div>
        </v-card-text>
      </v-card>

      <!-- Activity over time (optional) -->
      <v-card class="mt-4">
        <v-card-title class="d-flex align-center justify-space-between">
          Activity over time
          <div class="d-flex align-center">
            <v-select
              v-model="timeDistModel"
              :items="[{ title: 'Runs', value: 'run' }, { title: 'Objects', value: 'object' }]"
              style="max-width: 140px"
              density="compact"
              variant="outlined"
              hide-details
              class="mr-2"
            />
            <v-select
              v-model="timeDistMonths"
              :items="timeDistMonthItems"
              style="max-width: 160px"
              density="compact"
              variant="outlined"
              hide-details
              class="mr-2"
            />
            <v-btn v-if="!timeDistVisible" variant="text" color="primary" @click="handleShowPlot" :loading="timeDistLoading">Load</v-btn>
            <v-btn v-else variant="text" color="primary" @click="handleHidePlot">Hide</v-btn>
          </div>
        </v-card-title>
        <v-card-text>
          <v-alert v-if="timeDistError" type="error" variant="tonal">{{ timeDistError }}</v-alert>
          <v-skeleton-loader v-else-if="timeDistLoading" type="image" />
          <div v-else :class="['time-dist-wrapper', { hidden: !timeDistVisible }]">
            <div id="time-dist-container"></div>
          </div>
        </v-card-text>
      </v-card>
  </v-container>
</template>

<script>
import { ref, onMounted, watch } from 'vue'
import { api } from '@/services/api'
import { getStatusColor } from '@/utils/status'
import { useNotifyStore } from '@/store/notify'
import { formatDateTime } from '@/utils/datetime'
import { useQuerySync } from '@/composables/useQuerySync'

export default {
  name: 'Dashboard',
  setup() {
    const notify = useNotifyStore()
    const stats = ref({
      files: {
        total: 0,
        total_last_week: 0,
        bias: 0,
        darks: 0,
        flats: 0,
        lights: 0,
        fits: 0,
        jpeg: 0,
        cr2: 0,
        tiff: 0,
        ser: 0,
        storage_size: 0
      },
      objects: {
        total: 0,
        total_last_week: 0,
        galaxies: 0,
        star_clusters: 0,
        nebulae: 0,
        stars: 0,
        solar_system: 0,
        other: 0,
        unknown: 0
      },
      runs: {
        total: 0,
        total_last_week: 0,
        partly_reduced: 0,
        fully_reduced: 0,
        reduction_error: 0,
        not_reduced: 0
      }
    })

    const loading = ref(true)
    const error = ref(null)
    const recentRuns = ref([])
    const recentObjects = ref([])
    const headers = [
      { title: 'Name', key: 'name' },
      { title: 'Date', key: 'start_time' },
      { title: 'Status', key: 'reduction_status_display' },
      { title: 'Actions', key: 'actions', sortable: false }
    ]

    const formatDate = (date) => formatDateTime(date, { dateStyle: 'short' })

    const fetchStats = async () => {
      try {
        loading.value = true
        error.value = null
        const response = await api.getDashboardStats()
        console.log('API Response:', response)
        if (response) {
          // Verarbeite die Objektstatistiken
          let objectStats = response.objects
          if (typeof objectStats === 'string') {
            try {
              objectStats = JSON.parse(objectStats)
            } catch (e) {
              console.error('Error parsing object stats:', e)
              objectStats = {}
            }
          }
          
          stats.value.objects = {
            total: objectStats?.total || 0,
            total_last_week: objectStats?.total_last_week || 0,
            galaxies: objectStats?.galaxies || 0,
            star_clusters: objectStats?.star_clusters || 0,
            nebulae: objectStats?.nebulae || 0,
            stars: objectStats?.stars || 0,
            solar_system: objectStats?.solar_system || 0,
            other: objectStats?.other || 0,
            unknown: objectStats?.unknown || 0
          }

          // Verarbeite die Dateistatistiken
          if (response.files) {
            stats.value.files = {
              total: response.files.total || 0,
              total_last_week: response.files.total_last_week || 0,
              bias: response.files.bias || 0,
              darks: response.files.darks || 0,
              flats: response.files.flats || 0,
              lights: response.files.lights || 0,
              fits: response.files.fits || 0,
              jpeg: response.files.jpeg || 0,
              cr2: response.files.cr2 || 0,
              tiff: response.files.tiff || 0,
              ser: response.files.ser || 0,
              storage_size: response.files.storage_size || 0
            }
          }

          // Verarbeite die Run-Statistiken
          if (response.runs) {
            stats.value.runs = {
              total: response.runs.total || 0,
              total_last_week: response.runs.total_last_week || 0,
              partly_reduced: response.runs.partly_reduced || 0,
              fully_reduced: response.runs.fully_reduced || 0,
              reduction_error: response.runs.reduction_error || 0,
              not_reduced: response.runs.not_reduced || 0
            }
          }

          console.log('Updated stats:', stats.value)
        }
      } catch (error) {
        console.error('Error fetching dashboard stats:', error)
        error.value = 'Failed to load dashboard data. Please try again later.'
      } finally {
        loading.value = false
      }
    }

    const fetchRecentRuns = async () => {
      try {
        const response = await api.getRecentRuns()
        const items = response.results || response || []
        // Exclude runs without valid date (mid_observation_jd <= 0 or missing)
        const filtered = items.filter(r => {
          const jd = typeof r?.mid_observation_jd === 'number' ? r.mid_observation_jd : Number(r?.mid_observation_jd)
          return Number.isFinite(jd) && jd > 0
        })
        // Keep only top 10 after filtering
        recentRuns.value = filtered.slice(0, 10)
      } catch (error) {
        console.error('Error fetching recent runs:', error)
      }
    }

    const fetchRecentObjects = async () => {
      try {
        const response = await api.getRecentObjects()
        recentObjects.value = response.results || response
      } catch (error) {
        console.error('Error fetching recent objects:', error)
      }
    }

    const handleRetry = () => {
      fetchStats()
      fetchRecentRuns()
      fetchRecentObjects()
    }

    onMounted(() => {
      handleRetry()
    })

    const objectTypes = {
      'Galaxies': 'galaxies',
      'Star Clusters': 'star_clusters',
      'Nebulae': 'nebulae',
      'Stars': 'stars',
      'Solar System': 'solar_system',
      'Other': 'other'
    }

    const mapObjectTypeToCode = (label) => {
      const map = {
        'Galaxies': 'GA',
        'Star Clusters': 'SC',
        'Nebulae': 'NE',
        'Stars': 'ST',
        'Solar System': 'SO',
        'Other': 'OT',
        'Unknown': 'UK',
      }
      return map[label] || ''
    }

    const reductionStatuses = {
      'Fully Reduced runs': 'fully_reduced',
      'Partly Reduced runs': 'partly_reduced',
      'Reduction Errors': 'reduction_error',
      'Not Reduced runs': 'not_reduced'
    }

    const dataTypes = {
      'Bias Frames': 'bias',
      'Dark Frames': 'darks',
      'Flat Frames': 'flats',
      'Light Frames': 'lights',
      '2D spectra': 'spectra',
      'Other Frames': 'other'
    }

    const fileTypes = {
      'FITS': 'fits',
      'JPEG': 'jpeg',
      'CR2': 'cr2',
      'TIFF': 'tiff',
      'SER': 'ser',
      'Other': 'other'
    }

    

    // Time distribution state and loader
    const timeDistModel = ref('run')
    const timeDistLoading = ref(false)
    const timeDistError = ref('')
    const timeDistVisible = ref(false)
    const timeDistCache = new Map()
    const timeDistMonths = ref('12')
    const timeDistMonthItems = [
      { title: 'Last 12 months', value: '12' },
      { title: 'Last 24 months', value: '24' },
      { title: 'Last 60 months', value: '60' },
      { title: 'Since start', value: 'all' },
    ]

    const ensureBokeh = async () => {
      if (window.Bokeh) return
      await new Promise((resolve, reject) => {
        const script = document.createElement('script')
        const ver = import.meta.env.VITE_BOKEH_VERSION || '3.8.0'
        script.src = `https://cdn.bokeh.org/bokeh/release/bokeh-${ver}.min.js`
        script.onload = resolve
        script.onerror = reject
        document.head.appendChild(script)
      })
    }

    const loadTimeDistribution = async () => {
      timeDistError.value = ''
      timeDistLoading.value = true
      try {
        await ensureBokeh()
        const key = `${timeDistModel.value}:${timeDistMonths.value}`
        let item = timeDistCache.get(key)
        if (!item) {
          const base = import.meta.env.VITE_API_BASE || '/api'
          const params = new URLSearchParams({ model: timeDistModel.value, months: timeDistMonths.value, label: timeDistModel.value === 'run' ? 'Runs' : 'Objects' })
          const res = await fetch(`${base}/runs/time-distribution/?${params.toString()}`)
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          item = await res.json()
          timeDistCache.set(key, item)
        }
        const container = document.getElementById('time-dist-container')
        if (container) container.innerHTML = ''
        window.Bokeh.embed.embed_item(item, 'time-dist-container')
        try { notify.success('Activity plot loaded') } catch {}
        timeDistVisible.value = true
      } catch (e) {
        console.error(e)
        timeDistError.value = 'Failed to load activity plot.'
      } finally {
        timeDistLoading.value = false
      }
    }

    const { applyQuery, syncQueryAndFetch } = useQuerySync(
      { model: timeDistModel, months: timeDistMonths, showPlot: timeDistVisible },
      [
        { key: 'model', defaultValue: 'run' },
        { key: 'months', defaultValue: '12' },
        { key: 'showPlot', fromQuery: (v) => v === '1', toQuery: (v) => (v ? '1' : undefined) },
      ],
      () => {
        if (timeDistVisible.value && !timeDistLoading.value) {
          loadTimeDistribution()
        }
      }
    )

    watch([timeDistModel, timeDistMonths], () => {
      syncQueryAndFetch()
    })

    const handleShowPlot = async () => {
      timeDistVisible.value = true
      await loadTimeDistribution()
      syncQueryAndFetch()
    }

    const handleHidePlot = () => {
      timeDistVisible.value = false
      syncQueryAndFetch()
    }

    applyQuery()

    return {
      stats,
      loading,
      error,
      recentRuns,
      recentObjects,
      headers,
      formatDate,
      objectTypes,
      mapObjectTypeToCode,
      reductionStatuses,
      fileTypes,
      dataTypes,
      getStatusColor,
      timeDistModel,
      timeDistLoading,
      timeDistError,
      timeDistVisible,
      timeDistMonths,
      timeDistMonthItems,
      loadTimeDistribution,
      handleShowPlot,
      handleHidePlot,
      handleRetry
    }
  }
}
</script>

<style scoped>
.dashboard-container {
  padding: var(--v-theme-spacing-md);
  background-color: var(--v-theme-background);
  min-height: 100vh;
}

.reduction-card, .file-stats-card, .overview-card {
  border-radius: var(--v-theme-radius-md);
  box-shadow: var(--v-theme-shadow-card);
  transition: all var(--v-theme-transition-fast);
}

.reduction-card:hover, .file-stats-card:hover, .overview-card:hover {
  box-shadow: var(--v-theme-shadow-card-hover);
}

.stat-card {
  border: var(--v-theme-border-card);
  border-radius: var(--v-theme-radius-md);
  transition: all var(--v-theme-transition-fast);
  background-color: var(--v-theme-surface);
}

.stat-card:hover {
  box-shadow: var(--v-theme-shadow-card-hover);
  transform: translateY(-2px);
}

.stat-section {
  border-radius: var(--v-theme-radius-sm);
  background-color: var(--v-theme-surface);
  padding: var(--v-theme-spacing-md);
  transition: background-color var(--v-theme-transition-fast);
}

.stat-section:hover {
  background-color: var(--v-theme-surface-variant);
}

.stat-value {
  color: var(--v-theme-primary);
  font-weight: 500;
  transition: color var(--v-theme-transition-fast);
}

.stat-card:hover .stat-value {
  color: var(--v-theme-primary-dark);
}

.stat-label {
  color: var(--v-theme-on-surface);
  opacity: 0.7;
  transition: opacity var(--v-theme-transition-fast);
}

.stat-card:hover .stat-label {
  opacity: 1;
}

/* Table styles */
.custom-table {
  width: 100%;
  margin: var(--v-theme-spacing-md) 0;
}

.custom-table :deep(th) {
  background-color: var(--v-theme-surface);
  color: var(--v-theme-on-surface);
  font-weight: 500;
  text-align: left;
  padding: var(--v-theme-spacing-sm) var(--v-theme-spacing-md);
  border-bottom: 2px solid var(--v-theme-primary);
}

.custom-table :deep(td) {
  padding: var(--v-theme-spacing-sm) var(--v-theme-spacing-md);
  border-bottom: 1px solid var(--v-theme-border-card);
  color: var(--v-theme-on-surface);
}

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

/* Single-line truncation with ellipsis */
.cell-truncate {
  display: inline-block;
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}

.custom-table :deep(.status) {
  padding: 4px 8px;
  border-radius: var(--v-theme-radius-sm);
  font-size: 0.875rem;
  font-weight: 500;
}

.custom-table :deep(.status.success) {
  background-color: var(--v-theme-success);
  color: var(--v-theme-on-success);
}

.custom-table :deep(.status.warning) {
  background-color: var(--v-theme-warning);
  color: var(--v-theme-on-warning);
}

.custom-table :deep(.status.error) {
  background-color: var(--v-theme-error);
  color: var(--v-theme-on-error);
}

/* Responsive table */
@media (max-width: 600px) {
  .custom-table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }
  
  .custom-table :deep(th),
  .custom-table :deep(td) {
    padding: var(--v-theme-spacing-xs) var(--v-theme-spacing-sm);
  }
}

.status-chip {
  font-weight: 500;
}

.stat-section-title {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
}

.file-stat-col {
  margin-bottom: var(--v-theme-spacing-md);
}

.time-dist-wrapper {
  width: 100%;
}
.time-dist-wrapper.hidden {
  display: none;
}

/* Responsive adjustments */
@media (max-width: 600px) {
  .dashboard-container {
    padding: var(--v-theme-spacing-sm);
  }
  
  .stat-section {
    padding: var(--v-theme-spacing-sm);
  }
}
</style> 