<template>
  <v-container fluid class="dark-finder">
    <h1 class="text-h4 mb-4">Dark Finder</h1>

    <v-tabs v-model="tab" class="mb-4">
      <v-tab value="manual">Manuelle Eingabe</v-tab>
      <v-tab value="upload">FITS Upload</v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <!-- Manual Input Tab -->
      <v-window-item value="manual">
        <v-card>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="params.exptime"
                  type="number"
                  label="Exposure Time (s) *"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v != null && v !== '' && v > 0) || 'Must be positive']"
                  required
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="params.exptime_tolerance"
                  type="number"
                  label="Exposure Tolerance (s)"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v == null || v === '' || v >= 0) || 'Must be non-negative']"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="params.ccd_temp"
                  type="number"
                  label="CCD Temperature (°C) *"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v != null && v !== '') || 'Required']"
                  required
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="params.temp_tolerance"
                  type="number"
                  label="Temperature Tolerance (°C)"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v == null || v === '' || v >= 0) || 'Must be non-negative']"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-autocomplete
                  v-model="params.instrument"
                  :items="instruments"
                  label="Instrument *"
                  variant="outlined"
                  density="comfortable"
                  :loading="loadingInstruments"
                  :rules="[v => (v && v.trim() !== '') || 'Required']"
                  required
                  clearable
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.naxis1"
                  type="number"
                  label="Width (px) *"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v != null && v !== '' && v > 0) || 'Must be positive']"
                  required
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.naxis2"
                  type="number"
                  label="Height (px) *"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v != null && v !== '' && v > 0) || 'Must be positive']"
                  required
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.gain"
                  type="number"
                  label="Gain (optional)"
                  variant="outlined"
                  density="comfortable"
                  placeholder="-1"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.egain"
                  type="number"
                  label="EGAIN (optional)"
                  variant="outlined"
                  density="comfortable"
                  placeholder="-1"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.pedestal"
                  type="number"
                  label="Pedestal (optional)"
                  variant="outlined"
                  density="comfortable"
                  placeholder="-1"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.offset"
                  type="number"
                  label="Offset (optional)"
                  variant="outlined"
                  density="comfortable"
                  placeholder="-1"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.binning_x"
                  type="number"
                  label="Binning X"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v > 0) || 'Must be positive']"
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model.number="params.binning_y"
                  type="number"
                  label="Binning Y"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v > 0) || 'Must be positive']"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model.number="params.limit"
                  type="number"
                  label="Results Limit"
                  variant="outlined"
                  density="comfortable"
                  :rules="[v => (v > 0 && v <= 100) || 'Must be between 1 and 100']"
                />
              </v-col>
            </v-row>
            <v-btn
              color="primary"
              prepend-icon="mdi-magnify"
              :loading="searching"
              @click="searchDarks"
              class="mt-4"
            >
              Search Darks
            </v-btn>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- FITS Upload Tab -->
      <v-window-item value="upload">
        <v-card>
          <v-card-text>
            <v-file-input
              v-model="fitsFile"
              label="Select FITS file"
              accept=".fits,.fit,.fts"
              prepend-icon="mdi-file-upload"
              variant="outlined"
              density="comfortable"
              :loading="parsing"
              @change="onFileSelected"
            />
            <v-alert
              v-if="parseError"
              type="error"
              class="mt-4"
            >
              {{ parseError }}
            </v-alert>
            <v-alert
              v-if="parseSuccess"
              type="success"
              class="mt-4"
            >
              Header parsed successfully. Parameters loaded below.
            </v-alert>
            <div v-if="parsedParams" class="mt-4">
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="parsedParams.exptime"
                    type="number"
                    label="Exposure Time (s)"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="params.exptime_tolerance"
                    type="number"
                    label="Exposure Tolerance (s)"
                    variant="outlined"
                    density="comfortable"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="parsedParams.ccd_temp"
                    type="number"
                    label="CCD Temperature (°C)"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="params.temp_tolerance"
                    type="number"
                    label="Temperature Tolerance (°C)"
                    variant="outlined"
                    density="comfortable"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-autocomplete
                    v-model="parsedParams.instrument"
                    :items="instruments"
                    label="Instrument *"
                    variant="outlined"
                    density="comfortable"
                    :loading="loadingInstruments"
                    :rules="[v => (v && v.trim() !== '') || 'Required']"
                    required
                    clearable
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.naxis1"
                    type="number"
                    label="Width (px)"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.naxis2"
                    type="number"
                    label="Height (px)"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.gain"
                    type="number"
                    label="Gain"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.egain"
                    type="number"
                    label="EGAIN"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.pedestal"
                    type="number"
                    label="Pedestal"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.offset"
                    type="number"
                    label="Offset"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.binning_x"
                    type="number"
                    label="Binning X"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-text-field
                    v-model.number="parsedParams.binning_y"
                    type="number"
                    label="Binning Y"
                    variant="outlined"
                    density="comfortable"
                    readonly
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="params.limit"
                    type="number"
                    label="Results Limit"
                    variant="outlined"
                    density="comfortable"
                  />
                </v-col>
              </v-row>
              <v-btn
                color="primary"
                prepend-icon="mdi-magnify"
                :loading="searching"
                @click="searchDarksFromParsed"
                class="mt-4"
              >
                Search Darks
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Results -->
    <v-card v-if="results.length > 0" class="mt-4">
      <v-card-title class="d-flex justify-space-between align-center">
        <span>Results ({{ results.length }} matching darks)</span>
        <div>
          <v-btn
            color="primary"
            variant="outlined"
            prepend-icon="mdi-download"
            :loading="downloading"
            :disabled="selectedIds.length === 0"
            @click="downloadSelected"
            class="mr-2"
          >
            Download Selected ({{ selectedIds.length }})
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-download"
            :loading="downloading"
            @click="downloadAll"
          >
            Download All
          </v-btn>
        </div>
      </v-card-title>
      <v-card-text>
        <v-data-table
          v-model="selected"
          :headers="headers"
          :items="results"
          item-value="id"
          show-select
          class="elevation-0"
        >
          <template v-slot:item.obs_date="{ item }">
            {{ formatDate(item.obs_date) }}
          </template>
          <template v-slot:item.exptime="{ item }">
            {{ item.exptime }}s
          </template>
          <template v-slot:item.ccd_temp="{ item }">
            {{ item.ccd_temp }}°C
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <v-alert
      v-if="searchError"
      type="error"
      class="mt-4"
    >
      {{ searchError }}
    </v-alert>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'

const notify = useNotifyStore()

const tab = ref('manual')
const searching = ref(false)
const parsing = ref(false)
const downloading = ref(false)
const loadingInstruments = ref(false)
const searchError = ref('')
const parseError = ref('')
const parseSuccess = ref(false)
const fitsFile = ref(null)
const instruments = ref([])
const results = ref([])
const selected = ref([])
const parsedParams = ref(null)

const params = ref({
  exptime: null,
  exptime_tolerance: 0,
  ccd_temp: null,
  temp_tolerance: 2,
  instrument: '',
  naxis1: null,
  naxis2: null,
  gain: -1,
  egain: -1,
  pedestal: -1,
  offset: -1,
  binning_x: 1,
  binning_y: 1,
  limit: 20,
})

const headers = [
  { title: 'Filename', key: 'filename' },
  { title: 'Observation Run', key: 'observation_run' },
  { title: 'Date', key: 'obs_date' },
  { title: 'Exposure', key: 'exptime' },
  { title: 'Temperature', key: 'ccd_temp' },
  { title: 'Instrument', key: 'instrument' },
]

const selectedIds = computed(() => selected.value.map(item => item.id))

const loadInstruments = async () => {
  loadingInstruments.value = true
  try {
    const data = await api.getInstruments()
    instruments.value = data.instruments || []
  } catch (e) {
    notify.error('Failed to load instruments')
  } finally {
    loadingInstruments.value = false
  }
}

const onFileSelected = async () => {
  if (!fitsFile.value) return
  
  parsing.value = true
  parseError.value = ''
  parseSuccess.value = false
  
  try {
    const data = await api.parseFitsHeader(fitsFile.value)
    parsedParams.value = {
      exptime: data.exptime || null,
      ccd_temp: data.ccd_temp !== -999 ? data.ccd_temp : null,
      instrument: data.instrument || '',
      naxis1: data.naxis1 || null,
      naxis2: data.naxis2 || null,
      gain: data.gain !== -1 ? data.gain : -1,
      egain: data.egain !== -1 ? data.egain : -1,
      pedestal: data.pedestal !== -1 ? data.pedestal : -1,
      offset: data.offset !== -1 ? data.offset : -1,
      binning_x: data.binning_x || 1,
      binning_y: data.binning_y || 1,
    }
    parseSuccess.value = true
  } catch (e) {
    const errorMsg = e?.data?.error || e?.message || 'Failed to parse FITS header'
    parseError.value = errorMsg
    notify.error(`FITS parse error: ${errorMsg}`)
    console.error('FITS parse error:', e)
  } finally {
    parsing.value = false
  }
}

const searchDarks = async () => {
  // Validate required fields - check for null, undefined, empty string, or NaN
  const exptime = params.value.exptime
  const ccd_temp = params.value.ccd_temp
  const instrument = params.value.instrument
  const naxis1 = params.value.naxis1
  const naxis2 = params.value.naxis2
  
  const isInvalid = (val) => {
    return val == null || val === '' || (typeof val === 'number' && isNaN(val))
  }
  
  // Build list of missing fields for better error message
  const missing = []
  if (isInvalid(exptime)) missing.push('Exposure Time')
  if (isInvalid(ccd_temp)) missing.push('CCD Temperature')
  if (!instrument || instrument.trim() === '') missing.push('Instrument')
  if (isInvalid(naxis1)) missing.push('Width')
  if (isInvalid(naxis2)) missing.push('Height')
  
  if (missing.length > 0) {
    notify.error(`Please fill in: ${missing.join(', ')}`)
    return
  }
  
  // Validate numeric values are positive where required
  const exptimeNum = Number(exptime)
  const naxis1Num = Number(naxis1)
  const naxis2Num = Number(naxis2)
  
  if (exptimeNum <= 0 || naxis1Num <= 0 || naxis2Num <= 0) {
    notify.error('Exposure time and image dimensions must be positive')
    return
  }
  
  searching.value = true
  searchError.value = ''
  results.value = []
  selected.value = []
  
  try {
    // Prepare params, converting values properly
    const searchParams = {
      exptime: exptimeNum,
      exptime_tolerance: params.value.exptime_tolerance != null && params.value.exptime_tolerance !== '' 
        ? Number(params.value.exptime_tolerance) : 0,
      ccd_temp: Number(ccd_temp),
      temp_tolerance: params.value.temp_tolerance != null && params.value.temp_tolerance !== ''
        ? Number(params.value.temp_tolerance) : 2,
      instrument: String(instrument).trim(),
      naxis1: naxis1Num,
      naxis2: naxis2Num,
      gain: params.value.gain != null && params.value.gain !== '' && !isNaN(params.value.gain) 
        ? Number(params.value.gain) : -1,
      egain: params.value.egain != null && params.value.egain !== '' && !isNaN(params.value.egain)
        ? Number(params.value.egain) : -1,
      pedestal: params.value.pedestal != null && params.value.pedestal !== '' && !isNaN(params.value.pedestal)
        ? Number(params.value.pedestal) : -1,
      offset: params.value.offset != null && params.value.offset !== '' && !isNaN(params.value.offset)
        ? Number(params.value.offset) : -1,
      binning_x: params.value.binning_x != null && !isNaN(params.value.binning_x)
        ? Number(params.value.binning_x) : 1,
      binning_y: params.value.binning_y != null && !isNaN(params.value.binning_y)
        ? Number(params.value.binning_y) : 1,
      limit: params.value.limit != null && !isNaN(params.value.limit)
        ? Math.min(Number(params.value.limit), 100) : 20,
    }
    
    const data = await api.darkFinderSearch(searchParams)
    results.value = data.results || []
    if (results.value.length === 0) {
      notify.info('No matching dark frames found')
    }
  } catch (e) {
    searchError.value = e?.data?.error || 'Failed to search dark frames'
    notify.error('Search failed')
  } finally {
    searching.value = false
  }
}

const searchDarksFromParsed = async () => {
  if (!parsedParams.value) return
  
  // Validate required fields
  const exptime = parsedParams.value.exptime
  const ccd_temp = parsedParams.value.ccd_temp
  const instrument = parsedParams.value.instrument
  const naxis1 = parsedParams.value.naxis1
  const naxis2 = parsedParams.value.naxis2
  
  const isInvalid = (val) => {
    return val == null || val === '' || (typeof val === 'number' && isNaN(val))
  }
  
  // Build list of missing fields for better error message
  const missing = []
  if (isInvalid(exptime)) missing.push('Exposure Time')
  if (isInvalid(ccd_temp)) missing.push('CCD Temperature')
  if (!instrument || instrument.trim() === '') missing.push('Instrument')
  if (isInvalid(naxis1)) missing.push('Width')
  if (isInvalid(naxis2)) missing.push('Height')
  
  if (missing.length > 0) {
    notify.error(`Please fill in: ${missing.join(', ')}`)
    return
  }
  
  // Validate numeric values are positive where required
  const exptimeNum = Number(exptime)
  const naxis1Num = Number(naxis1)
  const naxis2Num = Number(naxis2)
  
  if (exptimeNum <= 0 || naxis1Num <= 0 || naxis2Num <= 0) {
    notify.error('Exposure time and image dimensions must be positive')
    return
  }
  
  searching.value = true
  searchError.value = ''
  results.value = []
  selected.value = []
  
  try {
    // Prepare params, converting values properly
    const searchParams = {
      exptime: exptimeNum,
      exptime_tolerance: params.value.exptime_tolerance != null && params.value.exptime_tolerance !== '' 
        ? Number(params.value.exptime_tolerance) : 0,
      ccd_temp: Number(ccd_temp),
      temp_tolerance: params.value.temp_tolerance != null && params.value.temp_tolerance !== ''
        ? Number(params.value.temp_tolerance) : 2,
      instrument: String(instrument).trim(),
      naxis1: naxis1Num,
      naxis2: naxis2Num,
      gain: parsedParams.value.gain != null && parsedParams.value.gain !== '' && !isNaN(parsedParams.value.gain) 
        ? Number(parsedParams.value.gain) : -1,
      egain: parsedParams.value.egain != null && parsedParams.value.egain !== '' && !isNaN(parsedParams.value.egain)
        ? Number(parsedParams.value.egain) : -1,
      pedestal: parsedParams.value.pedestal != null && parsedParams.value.pedestal !== '' && !isNaN(parsedParams.value.pedestal)
        ? Number(parsedParams.value.pedestal) : -1,
      offset: parsedParams.value.offset != null && parsedParams.value.offset !== '' && !isNaN(parsedParams.value.offset)
        ? Number(parsedParams.value.offset) : -1,
      binning_x: parsedParams.value.binning_x != null && !isNaN(parsedParams.value.binning_x)
        ? Number(parsedParams.value.binning_x) : 1,
      binning_y: parsedParams.value.binning_y != null && !isNaN(parsedParams.value.binning_y)
        ? Number(parsedParams.value.binning_y) : 1,
      limit: params.value.limit != null && !isNaN(params.value.limit)
        ? Math.min(Number(params.value.limit), 100) : 20,
    }
    
    const data = await api.darkFinderSearch(searchParams)
    results.value = data.results || []
    if (results.value.length === 0) {
      notify.info('No matching dark frames found')
    }
  } catch (e) {
    searchError.value = e?.data?.error || 'Failed to search dark frames'
    notify.error('Search failed')
  } finally {
    searching.value = false
  }
}

const downloadSelected = async () => {
  if (selectedIds.value.length === 0) return
  await downloadFiles(selectedIds.value)
}

const downloadAll = async () => {
  const allIds = results.value.map(r => r.id)
  await downloadFiles(allIds)
}

const downloadFiles = async (ids) => {
  downloading.value = true
  try {
    const job = await api.createBulkDownloadJob(ids, {})
    notify.success(`Download job created (ID: ${job.job_id})`)
    
    // Poll for job completion
    let attempts = 0
    const maxAttempts = 60
    const pollInterval = 2000 // 2 seconds
    
    const pollJob = async () => {
      try {
        const status = await api.getDownloadJobStatus(job.job_id)
        
        if (status.status === 'done') {
          // Download the file
          await api.downloadJobFile(job.job_id)
          notify.success('Download started')
          downloading.value = false
          return
        } else if (status.status === 'failed' || status.status === 'cancelled') {
          notify.error(`Download job ${status.status}`)
          downloading.value = false
          return
        }
        
        attempts++
        if (attempts < maxAttempts) {
          setTimeout(pollJob, pollInterval)
        } else {
          notify.error('Download job timeout')
          downloading.value = false
        }
      } catch (e) {
        notify.error('Failed to check download status')
        downloading.value = false
      }
    }
    
    setTimeout(pollJob, pollInterval)
  } catch (e) {
    notify.error('Failed to create download job')
    downloading.value = false
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  try {
    // Handle various date formats
    const date = new Date(dateStr.replace(' ', 'T'))
    return date.toLocaleString()
  } catch {
    return dateStr
  }
}

onMounted(() => {
  loadInstruments()
})
</script>

<style scoped>
.dark-finder {
  max-width: 1400px;
  margin: 0 auto;
}
</style>

