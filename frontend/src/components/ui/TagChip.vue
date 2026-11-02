<template>
  <v-chip v-bind="chipProps" :size="size" class="tag-chip">{{ name }}</v-chip>
</template>

<script setup>
import { computed } from 'vue'
import { readableTextColor } from '@/utils/color'

/**
 * Chip of a tag ({ name, color } or a plain name). Tag colors are chosen by users, so the chip is
 * filled with the tag color and gets black or white text, whichever contrasts more: readable for
 * any color on light and dark surfaces (as text or outline, dark colors vanish in the dark theme).
 */
const props = defineProps({
  tag: { type: [Object, String], required: true },
  size: { type: String, default: 'small' },
})

const name = computed(() => (typeof props.tag === 'string' ? props.tag : props.tag?.name || props.tag?.label || ''))
const color = computed(() => (typeof props.tag === 'string' ? '' : props.tag?.color || ''))

const chipProps = computed(() => {
  const text = readableTextColor(color.value)
  if (!text) return { variant: 'tonal', color: color.value || undefined }
  return { variant: 'flat', style: { backgroundColor: color.value, color: text } }
})
</script>

<style scoped>
/* Light tag colors stay distinguishable from a white card */
.tag-chip.v-chip--variant-flat {
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-on-surface), 0.16);
}
</style>
