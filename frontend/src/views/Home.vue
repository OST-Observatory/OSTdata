<template>
  <v-container fluid class="home">
    <v-row>
      <v-col cols="12" class="mb-4">
        <h1 class="text-h4 mb-2">Overwhelmingly Small Telescope Data Archive</h1>
        <p class="text-body-1 mb-2">
          Explore the plethora of observations made with the telescopes of the Overwhelmingly Small Telescope (OST) Observatory at the University of Potsdam. Search by object name or by sky coordinates to quickly jump into details.
        </p>
      </v-col>
    </v-row>

    <v-row class="mb-4">
      <v-col cols="12" md="12">
        <v-text-field
          v-model="query"
          class="home-search-field"
          variant="outlined"
          density="comfortable"
          hide-details
          clearable
          :loading="searching"
          label="Search by name (e.g. M67, NGC 7000) or coordinates: RA hh:mm:ss, Dec ±dd:mm:ss, Radius (e.g. 60&quot;, 2&apos;, 0.1 deg)"
          placeholder="Examples: M67 • 10:45:03 +12:34:56 60&quot; • 05:35:17.3 -05:23:28 2&apos;"
          @keyup.enter="doSearch"
        />
      </v-col>
    </v-row>

    <v-row class="mb-2">
      <v-col cols="12" class="d-flex justify-center">
        <v-btn color="primary" variant="flat" :loading="searching" @click="doSearch" size="default">
          Search
        </v-btn>
      </v-col>
    </v-row>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <v-row v-if="hasSearched && (objects.length || runs.length)">
      <v-col cols="12">
        <v-card class="mb-4">
          <v-card-title class="d-flex justify-space-between align-center">
            Objects ({{ objects.length }})
          </v-card-title>
          <v-card-text class="px-0">
            <v-skeleton-loader v-if="searching" type="table" />
            <v-data-table
              v-else
              :headers="objectHeaders"
              :items="objects"
              :items-per-page="10"
              class="custom-table"
            >
              <template #item.name="{ item }">
                <router-link :to="`/objects/${item.pk}`" class="text-decoration-none text-primary table-link cell-truncate">
                  {{ item.name }}
                </router-link>
              </template>
              <template #item.object_type="{ item }">{{ item.object_type_display }}</template>
              <template #item.ra="{ item }">{{ formatRA(item.ra) }}</template>
              <template #item.dec="{ item }">{{ formatDec(item.dec) }}</template>
              <template #item.photometry="{ item }">
                <v-icon :color="item.photometry ? 'success' : 'disabled'">{{ item.photometry ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
              </template>
              <template #item.spectroscopy="{ item }">
                <v-icon :color="item.spectroscopy ? 'success' : 'disabled'">{{ item.spectroscopy ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
              </template>
              <template #item.tags="{ item }">
                <div class="d-flex flex-wrap gap-1">
                  <v-chip v-for="tag in (item.tags || [])" :key="tag?.name || tag" size="x-small" class="mr-1">{{ tag?.name || tag }}</v-chip>
                </div>
              </template>
              <template #item.observation_runs="{ item }">
                <div class="d-flex flex-wrap gap-1">
                  <v-chip
                    v-for="run in (item.observation_run || [])"
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
              <template #no-data>
                <div class="text-secondary text-caption">No objects found.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" v-if="runs.length">
        <v-card class="mb-4">
          <v-card-title class="d-flex justify-space-between align-center">
            Observation Runs ({{ runs.length }})
          </v-card-title>
          <v-card-text class="px-0">
            <v-skeleton-loader v-if="searchingRuns" type="table" />
            <v-data-table
              v-else
              :headers="runHeaders"
              :items="runs"
              :items-per-page="10"
              class="custom-table"
            >
              <template #item.name="{ item }">
                <router-link :to="`/observation-runs/${item.pk || item.id}`" class="text-decoration-none text-primary table-link cell-truncate">
                  {{ item.name }}
                </router-link>
              </template>
              <template #item.date="{ item }">
                <template v-if="item.mid_observation_jd && item.mid_observation_jd > 0">
                  {{ formatDate(jdToDate(item.mid_observation_jd)) }}
                </template>
                <template v-else>
                  {{ formatDate(item.start_time || item.date) }}
                </template>
              </template>
              <template #item.main_targets="{ item }">
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
              <template #item.photometry="{ item }">
                <v-icon :color="getBool(item, ['photometry', 'has_photometry']) ? 'success' : 'disabled'">{{ getBool(item, ['photometry', 'has_photometry']) ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
              </template>
              <template #item.spectroscopy="{ item }">
                <v-icon :color="getBool(item, ['spectroscopy', 'has_spectroscopy']) ? 'success' : 'disabled'">{{ getBool(item, ['spectroscopy', 'has_spectroscopy']) ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
              </template>
              <template #item.n_light="{ item }">{{ getCount(item, ['n_light', 'n_lights', 'lights']) ?? '—' }}</template>
              <template #item.n_flat="{ item }">{{ getCount(item, ['n_flat', 'n_flats', 'flats']) ?? '—' }}</template>
              <template #item.n_dark="{ item }">{{ getCount(item, ['n_dark', 'n_darks', 'darks']) ?? '—' }}</template>
              <template #item.tags="{ item }">
                <div class="d-flex flex-wrap gap-1">
                  <v-chip
                    v-for="tag in normalizeTags(item.tags)"
                    :key="tag.name"
                    size="x-small"
                    variant="outlined"
                    :color="tag.color || 'primary'"
                  >
                    {{ tag.name }}
                  </v-chip>
                  <span v-if="!item?.tags || normalizeTags(item.tags).length === 0" class="text-secondary text-caption">—</span>
                </div>
              </template>
              <template #item.status="{ item }">
                <v-chip :color="getStatusColor(item.status || item.reduction_status)" size="small">
                  {{ item.status || item.reduction_status || 'n/a' }}
                </v-chip>
              </template>
              <template #no-data>
                <div class="text-secondary text-caption">No runs found.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-row v-else-if="hasSearched">
      <v-col cols="12">
        <v-alert type="info" variant="tonal">No results. Try another name or coordinates.</v-alert>
      </v-col>
    </v-row>
  </v-container>
  
</template>

<script setup>
import { ref } from 'vue'
import { api } from '@/services/api'
import { getStatusColor } from '@/utils/status'
import { formatDateTime, jdToDate } from '@/utils/datetime'

const query = ref('')
const searching = ref(false)
const searchingRuns = ref(false)
const hasSearched = ref(false)
const error = ref('')
const objects = ref([])
const runs = ref([])

const objectHeaders = [
  { title: 'Name', key: 'name' },
  { title: 'Object Type', key: 'object_type' },
  { title: 'RA', key: 'ra' },
  { title: 'Dec', key: 'dec' },
  { title: 'Lights', key: 'n_light' },
  { title: 'Light Exp. Time', key: 'light_expo_time' },
  { title: 'Photometry', key: 'photometry' },
  { title: 'Spectroscopy', key: 'spectroscopy' },
  { title: 'Tags', key: 'tags' },
  { title: 'Observation Runs', key: 'observation_runs' },
]

const runHeaders = [
  { title: 'Name', key: 'name' },
  { title: 'Date', key: 'date' },
  { title: 'Main Targets', key: 'main_targets' },
  { title: 'Photometry', key: 'photometry' },
  { title: 'Spectroscopy', key: 'spectroscopy' },
  { title: 'Lights', key: 'n_light' },
  { title: 'Flats', key: 'n_flat' },
  { title: 'Darks', key: 'n_dark' },
  { title: 'Tags', key: 'tags' },
  { title: 'Status', key: 'status' },
]

const doSearch = async () => {
  error.value = ''
  searching.value = true
  searchingRuns.value = true
  objects.value = []
  runs.value = []
  try {
    const parsed = parseCoordinates(query.value)
    if (parsed) {
      const { raDeg, decDeg, radiusArcsec } = parsed
      const res = await api.getObjectsVuetify({ page: 1, itemsPerPage: 50, ra: raDeg, dec: decDeg, radius: radiusArcsec })
      objects.value = res.items || []
      await fetchRunsForObjects(objects.value)
    } else {
      const search = String(query.value || '').trim()
      const res = await api.getObjectsVuetify({ page: 1, itemsPerPage: 50, search })
      objects.value = res.items || []
      await fetchRunsByTarget(search)
    }
  } catch (e) {
    error.value = 'Search failed.'
    console.error(e)
  } finally {
    searching.value = false
    hasSearched.value = true
  }
}

const fetchRunsByTarget = async (name) => {
  try {
    if (!name) { runs.value = []; searchingRuns.value = false; return }
    // Ask server for runs containing this target (name icontains)
    const res = await api.getObservationRuns({ page: 1, limit: 200, target: name })
    if (Array.isArray(res?.results)) {
      runs.value = res.results
    } else if (Array.isArray(res?.items)) {
      runs.value = res.items
    } else if (Array.isArray(res)) {
      runs.value = res
    } else {
      runs.value = []
    }
  } catch (e) {
    console.error(e)
    runs.value = []
  } finally {
    searchingRuns.value = false
  }
}

const fetchRunsForObjects = async (objs) => {
  try {
    const names = Array.from(new Set((objs || []).map(o => o?.name).filter(Boolean)))
    if (names.length === 0) { runs.value = []; return }
    // Fetch in batches to avoid too many requests
    const take = names.slice(0, 10)
    const promises = take.map(n => api.getObservationRuns({ page: 1, limit: 200, target: n }))
    const results = await Promise.allSettled(promises)
    const merged = []
    const seen = new Set()
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const arr = Array.isArray(r.value?.results) ? r.value.results : (Array.isArray(r.value?.items) ? r.value.items : (Array.isArray(r.value) ? r.value : []))
        for (const x of arr) {
          const id = x?.pk || x?.id
          if (id && !seen.has(id)) { seen.add(id); merged.push(x) }
        }
      }
    }
    runs.value = merged
  } catch (e) {
    console.error(e)
    runs.value = []
  } finally {
    searchingRuns.value = false
  }
}

const formatDate = (value) => {
  if (!value) return 'N/A'
  return formatDateTime(value, { dateStyle: 'short' })
}

const formatRA = (ra) => {
  if (ra === undefined || ra === null) return '—'
  const hours = Math.floor(ra / 15)
  const minutes = Math.floor((ra % 15) * 4)
  const seconds = ((ra % 15) * 4 - minutes) * 60
  return `${hours.toString().padStart(2, '0')}h ${minutes.toString().padStart(2, '0')}m ${seconds.toFixed(1)}s`
}

const formatDec = (dec) => {
  if (dec === undefined || dec === null) return '—'
  const sign = dec >= 0 ? '+' : '-'
  const absDec = Math.abs(dec)
  const degrees = Math.floor(absDec)
  const minutes = Math.floor((absDec - degrees) * 60)
  const seconds = ((absDec - degrees) * 60 - minutes) * 60
  return `${sign}${degrees.toString().padStart(2, '0')}° ${minutes.toString().padStart(2, '0')}' ${seconds.toFixed(1)}"`
}

// Helpers copied to mirror other views
const getMainTargets = (item) => {
  // prefer item.main_targets (array of names or objects), or build from nested objects
  if (Array.isArray(item?.main_targets)) {
    return item.main_targets
      .map(t => typeof t === 'string' ? { name: t, id: undefined } : { name: t?.name || String(t), id: t?.pk || t?.id })
      .map(t => ({ ...t, href: t.id ? `/objects/${t.id}` : undefined }))
      .filter(t => !!t.name)
  }
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

const getCount = (item, keys) => {
  for (const k of keys) {
    const v = item?.[k]
    if (typeof v === 'number') return v
  }
  return null
}

function parseCoordinates(input) {
  if (!input) return null
  const s = String(input).trim()
  // Try to find two tokens with time-like structure and an optional radius
  const tokens = s.split(/\s+/)
  const timeLike = tokens.filter(t => /\d{1,2}:\d{1,2}:\d{1,2}(?:\.\d+)?/.test(t))
  if (timeLike.length >= 2) {
    const raStr = timeLike[0]
    const decStr = timeLike[1]
    const rest = tokens.filter(t => t !== raStr && t !== decStr).join(' ')
    const raDeg = hmsToDeg(raStr)
    const decDeg = dmsToDeg(decStr)
    if (raDeg == null || decDeg == null) return null
    const { value: radiusArcsec } = parseRadius(rest) || { value: 60 } // default 60 arcsec
    return { raDeg, decDeg, radiusArcsec }
  }
  return null
}

function hmsToDeg(hms) {
  const m = String(hms).match(/^(\d{1,2}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/)
  if (!m) return null
  const h = Number(m[1]); const mi = Number(m[2]); const s = Number(m[3])
  if (!Number.isFinite(h) || !Number.isFinite(mi) || !Number.isFinite(s)) return null
  if (mi >= 60 || s >= 60) return null
  return (h + mi / 60 + s / 3600) * 15
}

function dmsToDeg(dms) {
  const m = String(dms).match(/^([+\-]?)(\d{1,2}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/)
  if (!m) return null
  const sign = m[1] === '-' ? -1 : 1
  const d = Number(m[2]); const mi = Number(m[3]); const s = Number(m[4])
  if (!Number.isFinite(d) || !Number.isFinite(mi) || !Number.isFinite(s)) return null
  if (d > 90 || mi >= 60 || s >= 60) return null
  const val = d + mi / 60 + s / 3600
  return sign * val
}

function parseRadius(str) {
  if (!str) return null
  const m = String(str).match(/(\d+(?:\.\d+)?)\s*(arcsec|arcmin|deg|"|'|m)/i)
  if (!m) return null
  const v = Number(m[1])
  const u = m[2].toLowerCase()
  if (!Number.isFinite(v)) return null
  if (u === 'arcsec' || u === '"') return { value: v }
  if (u === 'arcmin' || u === 'm' || u === "'") return { value: v * 60 }
  if (u === 'deg') return { value: v * 3600 }
  return null
}
</script>

<style scoped>
.home {
  padding: 20px 0;
}
.home-search-field :deep(input) {
  font-size: 1.1rem;
}

/* Table links – same style as Objects.vue and ObservationRuns.vue */
.custom-table :deep(.table-link) {
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
.custom-table :deep(.table-link:hover) {
  color: var(--v-theme-primary-dark);
  background-color: rgba(var(--v-theme-primary-light), 0.9);
  transform: translateY(-1px);
}
.custom-table :deep(.table-link::after) {
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
.custom-table :deep(.table-link:hover::after) {
  transform: scaleX(1);
}

.cell-truncate {
  display: inline-block;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>