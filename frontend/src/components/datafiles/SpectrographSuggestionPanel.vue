<template>
  <v-card class="mb-3">
    <v-card-title class="d-flex align-center flex-wrap" style="gap: 8px">
      <span class="text-subtitle-1">Spectrograph Suggestions: Evaluation</span>
      <v-spacer />
      <span v-if="evaluation?.computed_at" class="text-caption text-medium-emphasis">
        Computed {{ formatDate(evaluation.computed_at) }}
      </span>
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="load">Reload</v-btn>
      <v-btn size="small" color="primary" variant="outlined" prepend-icon="mdi-calculator" :loading="recomputing" @click="recompute">
        Recompute
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="error" type="error" variant="tonal" class="mb-2">{{ error }}</v-alert>
      <v-alert v-else-if="evaluation && !evaluation.data" type="info" variant="tonal">
        No suggestions computed yet. Use "Recompute" (runs in the background, nightly otherwise).
      </v-alert>
      <template v-else-if="evaluation?.data">
        <p class="text-body-2 text-medium-emphasis mb-3">
          Evaluated on {{ evaluation.data.reviewed_files }} files with a manually reviewed spectrograph, using their
          state before the review. A suggestion counts as correct (TP) if it equals the manual value and as wrong (FP)
          otherwise, also when the review only confirmed the old value ("Keep" in the table adds such confirmations).
          Path token purity is computed on current values and therefore slightly optimistic.
        </p>
        <v-table density="compact" class="mb-3">
          <thead>
            <tr>
              <th>Heuristic</th>
              <th class="text-right">Open now</th>
              <th class="text-right">TP</th>
              <th class="text-right">FP</th>
              <th class="text-right">FN</th>
              <th class="text-right">Precision</th>
              <th class="text-right">Recall</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.key">
              <tr>
                <td>{{ row.label }}</td>
                <td class="text-right">{{ row.open ?? '—' }}</td>
                <td class="text-right">{{ row.ev.tp }}</td>
                <td class="text-right">{{ row.ev.fp }}</td>
                <td class="text-right">{{ row.ev.fn }}</td>
                <td class="text-right">{{ percent(row.ev.precision) }}</td>
                <td class="text-right">{{ percent(row.ev.recall) }}</td>
                <td class="text-right">
                  <v-btn
                    v-if="Object.keys(row.ev.transitions || {}).length"
                    size="x-small"
                    variant="text"
                    :icon="expanded === row.key ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                    :aria-label="`Show transitions for ${row.label}`"
                    @click="expanded = expanded === row.key ? null : row.key"
                  />
                </td>
              </tr>
              <tr v-if="expanded === row.key">
                <td colspan="8" class="py-2">
                  <div class="d-flex flex-wrap" style="gap: 6px">
                    <v-chip v-for="(counts, transition) in row.ev.transitions" :key="transition" size="small" variant="tonal">
                      {{ formatTransition(transition) }}: {{ counts.tp || 0 }} TP / {{ counts.fp || 0 }} FP
                    </v-chip>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </v-table>
        <div v-if="tokens.length" class="text-body-2">
          <span class="text-medium-emphasis mr-2">Path tokens indicating a spectrograph:</span>
          <v-chip v-for="t in tokens" :key="t.token" size="x-small" :color="spectrographColor(t.label)" variant="tonal" class="mr-1 mb-1">
            {{ t.token }} → {{ spectrographLabel(t.label) }} ({{ percent(t.purity) }}, {{ t.support }} files)
          </v-chip>
        </div>
      </template>
      <v-skeleton-loader v-else-if="loading" type="table-row@3" />
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { spectrographColor, spectrographLabel } from '@/constants/classification'

const notify = useNotifyStore()
const evaluation = ref(null)
const loading = ref(false)
const recomputing = ref(false)
const error = ref(null)
const expanded = ref(null)

const LABELS = { run_majority: 'Run majority', path_token: 'Path token', both: 'Both agree' }

const rows = computed(() => {
  const ev = evaluation.value?.data?.evaluation || {}
  const open = evaluation.value?.open_now || {}
  return Object.keys(LABELS)
    .filter(key => ev[key])
    .map(key => ({ key, label: LABELS[key], ev: ev[key], open: open[key] }))
})

const tokens = computed(() => Object.entries(evaluation.value?.data?.indicative_tokens || {})
  .map(([token, info]) => ({ token, ...info })))

function percent(v) {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)} %`
}

function formatDate(v) {
  try { return new Date(v).toLocaleString() } catch { return v }
}

function formatTransition(t) {
  return String(t).split(' -> ').map(spectrographLabel).join(' → ')
}

async function load() {
  loading.value = true
  error.value = null
  try {
    evaluation.value = await api.getSpectrographSuggestionEvaluation()
  } catch (e) {
    error.value = 'Failed to load the evaluation'
  } finally {
    loading.value = false
  }
}

async function recompute() {
  recomputing.value = true
  try {
    await api.recomputeSpectrographSuggestions()
    notify.info('Recomputation queued. Reload in a minute to see the new results.')
  } catch (e) {
    notify.error('Failed to queue the recomputation')
  } finally {
    recomputing.value = false
  }
}

defineExpose({ load })
onMounted(load)
</script>
