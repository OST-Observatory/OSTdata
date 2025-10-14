<template>
  <AppLayout>
    <router-view></router-view>
  </AppLayout>
</template>

<script setup>
import AppLayout from './components/layout/AppLayout.vue'
</script>

<style>
/* Global styles */
html {
  scrollbar-width: var(--v-theme-scrollbar-width);
}

::-webkit-scrollbar {
  width: var(--v-theme-scrollbar-width);
  height: var(--v-theme-scrollbar-height);
}

::-webkit-scrollbar-track {
  background: var(--v-theme-surface);
}

::-webkit-scrollbar-thumb {
  background: var(--v-theme-primary);
  border-radius: var(--v-theme-radius-sm);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--v-theme-primary-dark);
}

body {
  margin: 0;
  padding: 0;
  font-family: 'Roboto', sans-serif;
  background-color: var(--v-theme-background);
  color: var(--v-theme-on-background);
}

/* Form elements */
input, textarea, select {
  padding: var(--v-theme-spacing-sm);
  border-radius: var(--v-theme-radius-sm);
  border: var(--v-theme-border-card);
  background-color: var(--v-theme-surface);
  color: var(--v-theme-on-surface);
}

/* Links */
a {
  color: var(--v-theme-primary);
  text-decoration: none;
  transition: color var(--v-theme-transition-fast);
}

a:hover {
  color: var(--v-theme-primary-dark);
}

/* Container */
.container {
  max-width: var(--v-theme-container-max-width);
  margin: 0 auto;
  padding: var(--v-theme-spacing-md);
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