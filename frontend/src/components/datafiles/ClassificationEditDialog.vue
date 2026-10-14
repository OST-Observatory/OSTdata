<template>
  <v-dialog :model-value="modelValue" max-width="560" @update:model-value="emit('update:modelValue', $event)">
    <v-card>
      <v-card-title>{{ bulk ? `Edit Classification (${items.length} files)` : 'Edit Classification' }}</v-card-title>
      <v-card-text>
        <div v-if="!bulk && single" class="text-body-2 mb-4">
          <div class="text-medium-emphasis mb-1">{{ single.file_name }}</div>
          <div class="d-flex flex-wrap align-center" style="gap: 6px">
            <span class="text-medium-emphasis">Header</span>
            <v-chip size="x-small" :color="exposureTypeColor(single.exposure_type)" variant="flat">{{ exposureTypeLabel(single.exposure_type) }}</v-chip>
            <span class="text-medium-emphasis ml-2">Classifier</span>
            <v-chip size="x-small" :color="exposureTypeColor(single.exposure_type_ml)" variant="flat">{{ exposureTypeLabel(single.exposure_type_ml) }}</v-chip>
            <span class="text-medium-emphasis ml-2">Effective</span>
            <v-chip size="x-small" :color="exposureTypeColor(single.effective_exposure_type)" variant="flat">{{ exposureTypeLabel(single.effective_exposure_type) }}</v-chip>
          </div>
        </div>

        <template v-if="canExposureType">
          <v-select
            v-model="form.exposureType"
            :items="exposureItems"
            item-title="label"
            item-value="value"
            label="Exposure Type (Manual)"
            hint="A manual type takes precedence over header and classifier. 'None' falls back to them."
            persistent-hint
            variant="outlined"
            class="mb-1"
          />
          <v-checkbox
            v-model="form.exposureOverride"
            :disabled="form.exposureType === UNCHANGED"
            label="Set override flag for the exposure type"
            density="compact"
            hide-details
            class="mb-3"
          />
        </template>

        <template v-if="canSpectrograph">
          <v-select
            v-model="form.spectrograph"
            :items="spectrographItems"
            item-title="label"
            item-value="value"
            label="Spectrograph"
            hint="Bias and dark frames never carry a spectrograph."
            persistent-hint
            variant="outlined"
            class="mb-1"
          />
          <v-checkbox
            v-model="form.spectrographOverride"
            :disabled="form.spectrograph === UNCHANGED"
            label="Set override flag (manual value, excluded from suggestions)"
            density="compact"
            hide-details
          />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!hasChanges" @click="save">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import {
  EXPOSURE_TYPE_ITEMS,
  SPECTROGRAPH_ITEMS,
  exposureTypeColor,
  exposureTypeLabel,
} from '@/constants/classification'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // Data file rows to edit (one row: single edit with current values; several: bulk edit)
  items: { type: Array, default: () => [] },
  canExposureType: { type: Boolean, default: false },
  canSpectrograph: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const notify = useNotifyStore()
const UNCHANGED = '__unchanged__'
const NONE = '__none__'

const bulk = computed(() => props.items.length > 1)
const single = computed(() => (props.items.length === 1 ? props.items[0] : null))
const exposureItems = computed(() => [
  ...(bulk.value ? [{ label: '(unchanged)', value: UNCHANGED }] : []),
  { label: 'None (use header/classifier)', value: NONE },
  ...EXPOSURE_TYPE_ITEMS,
])
const spectrographItems = computed(() => [
  ...(bulk.value ? [{ label: '(unchanged)', value: UNCHANGED }] : []),
  ...SPECTROGRAPH_ITEMS,
])

const initial = ref({})
const form = ref({})
const saving = ref(false)

function reset() {
  const row = single.value
  initial.value = {
    exposureType: row ? (row.exposure_type_user || NONE) : UNCHANGED,
    spectrograph: row ? (row.spectrograph || 'N') : UNCHANGED,
  }
  form.value = { ...initial.value, exposureOverride: true, spectrographOverride: true }
}

watch(() => props.modelValue, (open) => { if (open) reset() }, { immediate: true })

// Only fields that differ from the initial value are sent (a single edit of the exposure type must not
// mark the spectrograph as manually reviewed)
const payload = computed(() => {
  const data = {}
  if (props.canExposureType && form.value.exposureType !== initial.value.exposureType
      && form.value.exposureType !== UNCHANGED) {
    data.exposure_type_user = form.value.exposureType === NONE ? null : form.value.exposureType
    data.exposure_type_user_override = form.value.exposureOverride
  }
  if (props.canSpectrograph && form.value.spectrograph !== initial.value.spectrograph
      && form.value.spectrograph !== UNCHANGED) {
    data.spectrograph = form.value.spectrograph
    data.spectrograph_override = form.value.spectrographOverride
  }
  return data
})
const hasChanges = computed(() => Object.keys(payload.value).length > 0)

async function save() {
  saving.value = true
  try {
    const res = await api.updateClassification(props.items.map(i => i.pk), payload.value)
    notify.success(bulk.value ? `Updated ${res?.updated ?? props.items.length} file(s)` : 'Classification updated')
    emit('update:modelValue', false)
    emit('saved')
  } catch (e) {
    notify.error(e?.message || 'Failed to update classification')
  } finally {
    saving.value = false
  }
}
</script>
