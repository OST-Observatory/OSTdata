<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Auxiliary Objects (SIMBAD)</h1>
      <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="refresh">
        Refresh
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="!featureEnabled" type="warning" variant="tonal" class="mb-4">
      Auxiliary objects are disabled on the server (<code>AUX_OBJECTS_ENABLED=false</code>).
      Set <code>AUX_OBJECTS_ENABLED=True</code> in the backend environment and restart Django/Celery to enable triggers.
    </v-alert>
    <v-alert v-if="success" type="success" variant="tonal" class="mb-4">{{ success }}</v-alert>

    <v-card class="mb-4" v-if="stats">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">Photometry runs</div>
            <div class="text-h6">{{ stats.photometry_runs ?? 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">With plate-solved WCS</div>
            <div class="text-h6">{{ stats.with_wcs ?? 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">Ready</div>
            <div class="text-h6 text-success">{{ stats.ready ?? 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">Pending</div>
            <div class="text-h6 text-info">{{ stats.pending ?? 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">Error</div>
            <div class="text-h6 text-error">{{ stats.error ?? 0 }}</div>
          </v-col>
          <v-col cols="12" sm="6" md="4" lg="2">
            <div class="text-caption text-medium-emphasis">Missing</div>
            <div class="text-h6 text-warning">{{ stats.missing ?? 0 }}</div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="mb-4">
      <v-card-title>Automatic processing</v-card-title>
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">
          Background tasks query SIMBAD for auxiliary objects in the field of view.
          At least {{ simbadInterval }}s between SIMBAD requests (shared across workers).
          New plate solutions can trigger a refresh automatically when enabled in settings.
        </p>
        <v-switch
          v-model="taskEnabled"
          label="Celery beat queue enabled"
          color="primary"
          :loading="taskToggleLoading"
          hide-details
          class="mb-2"
          @update:model-value="toggleTaskEnabled"
        />
        <div v-if="taskSource" class="text-caption text-medium-emphasis mb-4">
          Source: {{ taskSource }}
        </div>
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-playlist-play"
          :loading="queueLoading"
          :disabled="!featureEnabled"
          @click="runQueueNow"
        >
          Process queue now
        </v-btn>
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title>Manual bulk trigger</v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="6">
            <v-switch
              v-model="requireWcs"
              label="Only runs with plate-solved WCS"
              color="primary"
              hide-details
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-switch
              v-model="forceRefresh"
              label="Refresh existing results (re-query SIMBAD)"
              color="primary"
              hide-details
            />
          </v-col>
        </v-row>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <v-btn
            color="primary"
            prepend-icon="mdi-magnify-scan"
            :loading="triggerMissingLoading"
            :disabled="!featureEnabled"
            @click="triggerMissing"
          >
            Compute missing
          </v-btn>
          <v-btn
            color="primary"
            variant="outlined"
            prepend-icon="mdi-refresh"
            :loading="triggerAllLoading"
            :disabled="!featureEnabled"
            @click="triggerAll"
          >
            {{ forceRefresh ? 'Refresh all eligible' : 'Compute all missing' }}
          </v-btn>
        </div>
        <p class="text-caption text-medium-emphasis mt-4 mb-0">
          Tasks are queued in Celery. Runs show as pending on the observation run detail page until complete.
        </p>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '@/services/api'

const loading = ref(false)
const error = ref('')
const success = ref('')
const stats = ref(null)
const featureEnabled = ref(true)
const taskEnabled = ref(false)
const taskSource = ref('')
const taskToggleLoading = ref(false)
const queueLoading = ref(false)
const triggerMissingLoading = ref(false)
const triggerAllLoading = ref(false)
const requireWcs = ref(true)
const forceRefresh = ref(false)
const simbadInterval = 10

const refresh = async () => {
  loading.value = true
  error.value = ''
  try {
    const [statsRes, taskRes] = await Promise.all([
      api.getAuxObjectsStats(),
      api.getAuxObjectsTaskEnabled(),
    ])
    stats.value = statsRes || null
    featureEnabled.value = statsRes?.enabled !== false
    taskEnabled.value = !!taskRes?.enabled
    taskSource.value = taskRes?.source || ''
  } catch (e) {
    error.value = 'Failed to load auxiliary objects admin data.'
    console.error(e)
  } finally {
    loading.value = false
  }
}

const toggleTaskEnabled = async (value) => {
  taskToggleLoading.value = true
  error.value = ''
  success.value = ''
  try {
    await api.setAuxObjectsTaskEnabled(!!value)
    taskSource.value = 'redis'
    success.value = value ? 'Background queue enabled.' : 'Background queue disabled.'
  } catch (e) {
    error.value = 'Failed to update task status.'
    taskEnabled.value = !value
    console.error(e)
  } finally {
    taskToggleLoading.value = false
  }
}

const runQueueNow = async () => {
  queueLoading.value = true
  error.value = ''
  success.value = ''
  try {
    await api.triggerAuxObjectsQueue()
    success.value = 'Queue processor enqueued.'
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to enqueue queue processor.')
    console.error(e)
  } finally {
    queueLoading.value = false
  }
}

const apiErrorMessage = (e, fallback) => e?.data?.detail || e?.message || fallback

const trigger = async (mode) => {
  if (!featureEnabled.value) {
    throw Object.assign(new Error('AUX_OBJECTS_ENABLED is false in settings'), {
      data: { detail: 'AUX_OBJECTS_ENABLED is false in settings' },
    })
  }
  const payload = {
    mode,
    force: forceRefresh.value,
    require_wcs: requireWcs.value,
  }
  return api.triggerAuxObjects(payload)
}

const triggerMissing = async () => {
  triggerMissingLoading.value = true
  error.value = ''
  success.value = ''
  try {
    const res = await trigger('missing')
    success.value = `Enqueued ${res?.enqueued ?? 0} run(s) (${res?.skipped ?? 0} skipped).`
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to trigger auxiliary object lookup.')
    console.error(e)
  } finally {
    triggerMissingLoading.value = false
  }
}

const triggerAll = async () => {
  triggerAllLoading.value = true
  error.value = ''
  success.value = ''
  try {
    const res = await trigger('all')
    success.value = `Enqueued ${res?.enqueued ?? 0} run(s) (${res?.skipped ?? 0} skipped).`
    await refresh()
  } catch (e) {
    error.value = apiErrorMessage(e, 'Failed to trigger auxiliary object lookup.')
    console.error(e)
  } finally {
    triggerAllLoading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.gap-2 {
  gap: 8px;
}
</style>
