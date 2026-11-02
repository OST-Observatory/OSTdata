<template>
  <AppLayout>
    <router-view></router-view>
  </AppLayout>
</template>

<script setup>
import AppLayout from './components/layout/AppLayout.vue'
</script>

<style>
/* Global styles (theme-dependent base styles: styles/base.css) */
body {
  margin: 0;
  padding: 0;
  font-family: 'Roboto', sans-serif;
}

/* Tables */
.v-table .v-table__wrapper > table {
  border-collapse: separate;
  border-spacing: 0;
}

/* Respect user preference for reduced motion */
@media (prefers-reduced-motion: reduce) {
  *:not(.v-overlay__scrim) {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
</style> 