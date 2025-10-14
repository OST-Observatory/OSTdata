<template>
  <div class="empty-state d-flex align-center">
    <v-icon :size="24" class="mr-2" color="primary">{{ icon }}</v-icon>
    <div>
      <div class="text-body-2">{{ text }}</div>
      <div v-if="subtext" class="text-caption text-secondary">{{ subtext }}</div>
      <div v-if="$slots.actions" class="mt-2">
        <slot name="actions"></slot>
      </div>
    </div>
  </div>
  
</template>

<script setup>
const props = defineProps({
  text: { type: String, default: 'No results.' },
  subtext: { type: String, default: '' },
  icon: { type: String, default: 'mdi-database-off' },
})
</script>

<style scoped>
.empty-state {
  padding: 8px 0;
}
</style>


