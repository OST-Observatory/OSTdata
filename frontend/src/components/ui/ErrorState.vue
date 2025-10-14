<template>
  <v-alert type="error" variant="tonal" class="mb-3">
    <div class="d-flex align-center">
      <v-icon class="mr-2">mdi-alert-circle</v-icon>
      <span>{{ message }}</span>
      <v-spacer />
      <v-btn v-if="retry" variant="text" color="primary" @click="retry" size="small">Retry</v-btn>
    </div>
  </v-alert>
</template>

<script setup>
const props = defineProps({
  message: { type: String, default: 'Something went wrong.' },
  retry: { type: Function, default: null },
})
</script>

<style scoped>
</style>


