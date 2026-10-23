<template>
  <!-- Quick actions of a data file row (preview, FITS header, download), shared by all data file
       tables so icons, sizes and spacing stay the same. Extra actions (e.g. a menu) go into the slot. -->
  <div class="d-flex align-center flex-nowrap quick-actions">
    <v-tooltip text="Preview thumbnail" location="top">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          icon="mdi-eye"
          size="small"
          density="comfortable"
          variant="text"
          :aria-label="`Preview ${fileName}`"
          @click="emit('preview', item)"
        />
      </template>
    </v-tooltip>
    <v-tooltip :text="isFits ? 'FITS header' : 'FITS header (FITS files only)'" location="top">
      <template #activator="{ props }">
        <!-- Wrapper keeps the tooltip working while the button is disabled -->
        <span v-bind="props">
          <v-btn
            icon="mdi-code-tags"
            size="small"
            density="comfortable"
            variant="text"
            :disabled="!isFits"
            :aria-label="`View FITS header for ${fileName}`"
            @click="emit('header', item)"
          />
        </span>
      </template>
    </v-tooltip>
    <v-tooltip v-if="download" text="Download" location="top">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          icon="mdi-download"
          size="small"
          density="comfortable"
          variant="text"
          :href="api.getDataFileDownloadUrl(item.pk ?? item.id)"
          :aria-label="`Download ${fileName}`"
        />
      </template>
    </v-tooltip>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { api } from '@/services/api'

const props = defineProps({
  item: { type: Object, required: true },
  download: { type: Boolean, default: true },
})
const emit = defineEmits(['preview', 'header'])

const fileName = computed(() => props.item.file_name || '')
const isFits = computed(() => {
  const type = String(props.item.file_type || '').toUpperCase()
  return type === 'FITS' || /\.(fits?|fts)$/i.test(fileName.value)
})
</script>

<style scoped>
.quick-actions {
  gap: 4px;
}

/* Clearer hover than Vuetify's default text-button overlay (4 %) */
.quick-actions :deep(.v-btn:not(.v-btn--disabled):hover) {
  color: rgb(var(--v-theme-primary));
}

.quick-actions :deep(.v-btn:not(.v-btn--disabled):hover > .v-btn__overlay) {
  opacity: 0.16;
}
</style>
