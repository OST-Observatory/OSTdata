<template>
  <div class="loading-state">
    <v-skeleton-loader :type="type" />
  </div>
</template>

<script setup>
const props = defineProps({
  type: { type: String, default: 'table' },
})
</script>

<style scoped>
.loading-state {
  padding: 8px 0;
}
</style>


