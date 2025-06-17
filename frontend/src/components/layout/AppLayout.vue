<template>
  <v-app>
    <v-app-bar
      app
      class="app-bar"
      color="secondary"
      elevation="2"
      fixed
      height="64"
    >
      <v-app-bar-title class="text-h6 font-weight-bold on-secondary">
        OST Data Archive
      </v-app-bar-title>
      <v-spacer></v-spacer>
      
      <!-- Debug Button -->
      <v-btn
        v-if="isDevelopment"
        @click="showThemeVariables"
        class="me-2"
        color="primary"
        variant="text"
      >
        Debug Theme
      </v-btn>
      
      <v-btn icon to="/" class="on-secondary nav-btn">
        <v-icon>speed</v-icon>
        <v-tooltip activator="parent" location="bottom">Dashboard</v-tooltip>
      </v-btn>

      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn">
            <v-icon>assignment</v-icon>
            <v-tooltip activator="parent" location="bottom">Observation runs</v-tooltip>
          </v-btn>
        </template>
        <v-list class="nav-menu">
          <v-list-item to="/observation-runs" class="nav-item">
            <v-list-item-title class="text-primary">Observation runs</v-list-item-title>
          </v-list-item>
          <v-list-item to="/tags" class="nav-item">
            <v-list-item-title class="text-primary">Tags</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <v-btn icon to="/objects" class="on-secondary nav-btn">
        <v-icon>star</v-icon>
        <v-tooltip activator="parent" location="bottom">Objects</v-tooltip>
      </v-btn>

      <v-menu v-if="isAuthenticated">
        <template v-slot:activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn">
            <v-icon>account_circle</v-icon>
            <v-tooltip activator="parent" location="bottom">{{ username }}</v-tooltip>
          </v-btn>
        </template>
        <v-list class="nav-menu">
          <v-list-item @click="logout" class="nav-item">
            <v-list-item-title class="text-primary">Log Out</v-list-item-title>
          </v-list-item>
          <v-list-item to="/change-password" class="nav-item">
            <v-list-item-title class="text-primary">Change password</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <v-menu v-else>
        <template v-slot:activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn">
            <v-icon>lock</v-icon>
            <v-tooltip activator="parent" location="bottom">Log In</v-tooltip>
          </v-btn>
        </template>
        <v-list class="nav-menu">
          <v-list-item to="/login" class="nav-item">
            <v-list-item-title class="text-primary">Log In</v-list-item-title>
          </v-list-item>
          <v-list-item to="/reset-password" class="nav-item">
            <v-list-item-title class="text-primary">Reset password</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-app-bar>

    <v-main class="main-content">
      <v-container>
        <v-alert
          v-for="message in messages"
          :key="message.id"
          :type="message.type"
          :text="message.text"
          class="mb-4"
          variant="tonal"
        ></v-alert>
        
        <slot></slot>
      </v-container>
    </v-main>

    <v-footer class="footer" :class="{ 'footer-visible': isFooterVisible }">
      <v-row justify="center" no-gutters>
        <v-col class="text-center" cols="12">
          <div class="text-caption footer-text">
            <span class="me-2">contact: ostdata (at) astro.physik.uni-potsdam.de</span>
            <span class="mx-2">•</span>
            <a href="https://github.com/OST-Observatory/ostdata" target="_blank" class="footer-link">
              source code
            </a>
          </div>
        </v-col>
      </v-row>
    </v-footer>
  </v-app>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/store/auth'

const authStore = useAuthStore()
const isAuthenticated = ref(authStore.isAuthenticated)
const username = ref(authStore.username)
const messages = ref([])
const isFooterVisible = ref(false)

// Debug mode is always true for now
const isDevelopment = computed(() => true)

const checkScroll = () => {
  const scrollPosition = window.scrollY + window.innerHeight
  const documentHeight = document.documentElement.scrollHeight
  isFooterVisible.value = scrollPosition >= documentHeight - 100
}

onMounted(() => {
  window.addEventListener('scroll', checkScroll)
  checkScroll() // Initial check
})

onUnmounted(() => {
  window.removeEventListener('scroll', checkScroll)
})

const showThemeVariables = () => {
  const root = document.documentElement
  const styles = getComputedStyle(root)
  
  console.log('Theme Variables:')
  // Check all available theme variables
  const themeVars = Array.from(styles)
    .filter(prop => prop.startsWith('--v-theme-'))
    .map(prop => `${prop}: ${styles.getPropertyValue(prop)}`)
  
  console.log('All theme variables:')
  themeVars.forEach(v => console.log(v))
  
  // Check specific variables we're interested in
  console.log('\nSpecific variables:')
  console.log('--v-theme-primary:', styles.getPropertyValue('--v-theme-primary'))
  console.log('--v-theme-primary-light:', styles.getPropertyValue('--v-theme-primary-light'))
  console.log('--v-theme-border-card', styles.getPropertyValue('--v-theme-border-card'))
  
  const appBar = document.querySelector('.app-bar')
  if (appBar) {
    const appBarStyles = getComputedStyle(appBar)
    console.log('\nApp Bar Styles:')
    console.log('background-color:', appBarStyles.backgroundColor)
    console.log('color:', appBarStyles.color)
    console.log('Computed background-color:', window.getComputedStyle(appBar).backgroundColor)
  }
}

const logout = () => {
  authStore.logout()
  isAuthenticated.value = false
  username.value = ''
}
</script>

<style scoped>
.app-bar {
  box-shadow: var(--v-theme-app-bar-shadow) !important;
  border-bottom: var(--v-theme-app-bar-border);
}

.main-content {
  background-color: rgb(var(--v-theme-background));
  min-height: calc(100vh - 64px);
  padding-top: 64px;
}

.footer {
  background-color: rgb(var(--v-theme-secondary));
  color: rgb(var(--v-theme-on-secondary));
  border-top: var(--v-theme-app-bar-border);
  padding: 16px 0;
  transition: opacity 0.3s;
  opacity: 0;
}

.footer-visible {
  opacity: 1;
}

.footer-text {
  color: rgb(var(--v-theme-on-secondary));
  font-size: 0.75rem !important;
  line-height: 1.2;
}

.footer-link {
  color: rgb(var(--v-theme-primary-light));
  text-decoration: none;
  transition: color 0.2s;
}

.footer-link:hover {
  color: rgb(var(--v-theme-primary));
}

.nav-menu {
  background-color: rgb(var(--v-theme-surface));
  border-radius: 8px;
  box-shadow: var(--v-theme-app-bar-shadow);
}

.nav-item {
  transition: background-color 0.2s;
}

.nav-item:hover {
  background-color: rgba(var(--v-theme-primary), var(--v-theme-hover-opacity));
}

.nav-btn {
  transition: background-color 0.2s;
}

.nav-btn:hover {
  background-color: rgba(var(--v-theme-primary), var(--v-theme-hover-opacity)) !important;
}

a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  transition: color 0.2s;
}

a:hover {
  color: rgb(var(--v-theme-primary-dark));
}
</style>
