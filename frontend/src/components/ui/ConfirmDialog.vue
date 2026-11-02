<template>
  <v-dialog
    :model-value="state.open"
    max-width="480"
    aria-labelledby="confirm-dialog-title"
    @update:model-value="(open) => { if (!open) answer(false) }"
  >
    <v-card>
      <v-card-title id="confirm-dialog-title" class="d-flex align-center" style="gap: 8px">
        <v-icon v-if="state.color === 'error' || state.color === 'warning'" icon="mdi-alert-outline" :color="state.color" />
        <span class="text-wrap">{{ state.title }}</span>
      </v-card-title>
      <v-card-text v-if="state.text" class="confirm-text">{{ state.text }}</v-card-text>
      <v-card-actions>
        <v-spacer />
        <!-- Cancel gets the focus: Enter right after opening must not trigger a destructive action -->
        <v-btn ref="cancelBtn" variant="text" @click="answer(false)">{{ state.cancelText }}</v-btn>
        <v-btn :color="state.color" variant="flat" @click="answer(true)">{{ state.confirmText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { useConfirm } from '@/composables/useConfirm'

const { state, answer } = useConfirm()
const cancelBtn = ref(null)

watch(() => state.open, async (open) => {
  if (!open) return
  await nextTick()
  // The dialog content is mounted after opening; wait one more frame for the transition
  requestAnimationFrame(() => cancelBtn.value?.$el?.focus())
})
</script>

<style scoped>
.confirm-text {
  white-space: pre-line;
}
</style>
