<template>
  <v-app>
    <a href="#main-content" class="skip-link">Skip to content</a>
    <v-app-bar
      app
      class="app-bar"
      color="secondary"
      elevation="2"
      fixed
      height="64"
    >
      <v-app-bar-title class="text-h6 font-weight-bold on-secondary app-title-fixed">
        <router-link to="/" class="text-decoration-none on-secondary" style="color: inherit;">
          OST Data Archive
        </router-link>
      </v-app-bar-title>
      <v-breadcrumbs
        v-if="breadcrumbsDisplay.length && !isMobile"
        :items="breadcrumbsDisplay"
        class="breadcrumbs-appbar on-secondary ml-3"
        aria-label="Breadcrumbs"
      >
        <template #item="{ item }">
          <v-tooltip location="bottom" :text="(item as any).full">
            <template #activator="{ props }">
              <v-breadcrumbs-item v-bind="props" :to="item.to" :disabled="item.disabled" :aria-current="item.disabled ? 'page' : undefined">
                {{ item.title }}
              </v-breadcrumbs-item>
            </template>
          </v-tooltip>
        </template>
        <template #divider>
          <v-icon size="16">mdi-chevron-right</v-icon>
        </template>
      </v-breadcrumbs>
      <v-spacer></v-spacer>
      
      <nav v-if="!isMobile" class="primary-nav" aria-label="Primary">
      <v-btn icon to="/" aria-label="Home" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': route.path === '/' }" :aria-current="route.path === '/' ? 'page' : undefined" @mouseenter="prefetchRoute('/dashboard')">
        <v-icon>mdi-home</v-icon>
        <v-tooltip activator="parent" location="bottom">Home</v-tooltip>
      </v-btn>
      <v-btn icon to="/dashboard" aria-label="Open Dashboard" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': isActive('/dashboard')}" :aria-current="(isActive('/dashboard')) ? 'page' : undefined" @mouseenter="prefetchRoute('/dashboard')">
        <v-icon>mdi-speedometer</v-icon>
        <v-tooltip activator="parent" location="bottom">Dashboard</v-tooltip>
      </v-btn>

      <v-btn icon to="/observation-runs" aria-label="Open Observation runs" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': isActive('/observation-runs') }" :aria-current="isActive('/observation-runs') ? 'page' : undefined" @mouseenter="prefetchRoute('/observation-runs')">
        <v-icon>mdi-telescope</v-icon>
        <v-tooltip activator="parent" location="bottom">Observation runs</v-tooltip>
      </v-btn>

      <v-btn icon to="/objects" aria-label="Open Objects" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': isActive('/objects') }" :aria-current="isActive('/objects') ? 'page' : undefined" @mouseenter="prefetchRoute('/objects')">
        <v-icon>mdi-creation</v-icon>
        <v-tooltip activator="parent" location="bottom">Objects</v-tooltip>
      </v-btn>

      <v-btn icon to="/tags" aria-label="Open Tags" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': isActive('/tags') }" :aria-current="isActive('/tags') ? 'page' : undefined" @mouseenter="prefetchRoute('/tags')">
        <v-icon>mdi-tag-outline</v-icon>
        <v-tooltip activator="parent" location="bottom">Tags</v-tooltip>
      </v-btn>

      <v-btn v-if="isAdmin" icon to="/admin" aria-label="Open Admin" class="on-secondary nav-btn nav-gap" :class="{ 'nav-active': isActive('/admin') }" :aria-current="isActive('/admin') ? 'page' : undefined">
        <v-icon>mdi-shield-account</v-icon>
        <v-tooltip activator="parent" location="bottom">Admin</v-tooltip>
      </v-btn>

      <v-btn
        icon
        class="on-secondary nav-btn nav-gap"
        aria-label="Toggle theme"
        @click="toggleTheme"
      >
        <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
        <v-tooltip activator="parent" location="bottom">{{ isDark ? 'Dark' : 'Light' }} theme</v-tooltip>
      </v-btn>

      <v-menu v-if="isAuthenticated" v-model="accountMenuOpen">
        <template v-slot:activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn nav-gap" aria-label="Account menu" :aria-expanded="accountMenuOpen ? 'true' : 'false'">
            <v-icon>mdi-account-circle</v-icon>
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

      <v-menu v-else v-model="loginMenuOpen">
        <template v-slot:activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn nav-gap" aria-label="Open login menu" :aria-expanded="loginMenuOpen ? 'true' : 'false'">
            <v-icon>mdi-lock</v-icon>
            <v-tooltip activator="parent" location="bottom">Log In</v-tooltip>
          </v-btn>
        </template>
        <v-list class="nav-menu">
          <v-list-item :to="{ path: '/login', query: { next: route.fullPath } }" class="nav-item">
            <v-list-item-title class="text-primary">Log In</v-list-item-title>
          </v-list-item>
          <v-list-item to="/reset-password" class="nav-item">
            <v-list-item-title class="text-primary">Reset password</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
      </nav>

      <!-- Mobile overflow menu -->
      <v-menu v-if="isMobile">
        <template #activator="{ props }">
          <v-btn icon v-bind="props" class="on-secondary nav-btn nav-gap" aria-label="Open menu">
            <v-icon>mdi-menu</v-icon>
          </v-btn>
        </template>
        <v-list class="nav-menu">
          <v-list-item to="/dashboard" :aria-current="(isActive('/dashboard') || route.path === '/') ? 'page' : undefined"><v-list-item-title>Dashboard</v-list-item-title></v-list-item>
          <v-list-item to="/observation-runs" :aria-current="isActive('/observation-runs') ? 'page' : undefined"><v-list-item-title>Observation runs</v-list-item-title></v-list-item>
          <v-list-item to="/objects" :aria-current="isActive('/objects') ? 'page' : undefined"><v-list-item-title>Objects</v-list-item-title></v-list-item>
          <v-list-item to="/tags" :aria-current="isActive('/tags') ? 'page' : undefined"><v-list-item-title>Tags</v-list-item-title></v-list-item>
          <template v-if="isAdmin">
            <v-list-item to="/admin" :aria-current="isActive('/admin') ? 'page' : undefined"><v-list-item-title>Admin</v-list-item-title></v-list-item>
          </template>
          <v-divider></v-divider>
          <v-list-item @click="toggleTheme"><v-list-item-title>{{ isDark ? 'Light theme' : 'Dark theme' }}</v-list-item-title></v-list-item>
          <v-divider></v-divider>
          <template v-if="isAuthenticated">
            <v-list-item @click="logout"><v-list-item-title>Log Out</v-list-item-title></v-list-item>
            <v-list-item to="/change-password"><v-list-item-title>Change password</v-list-item-title></v-list-item>
          </template>
          <template v-else>
            <v-list-item :to="{ path: '/login', query: { next: route.fullPath } }"><v-list-item-title>Log In</v-list-item-title></v-list-item>
            <v-list-item to="/reset-password"><v-list-item-title>Reset password</v-list-item-title></v-list-item>
          </template>
        </v-list>
      </v-menu>
    </v-app-bar>

    <v-main class="main-content" id="main-content" tabindex="-1">
      <v-container>
        <v-alert
          v-if="banner.enabled && banner.message"
          :type="banner.level"
          class="mb-4"
          variant="tonal"
        >
          {{ banner.message }}
        </v-alert>
        <v-breadcrumbs :items="breadcrumbsDisplayMobile" class="mb-2" v-if="breadcrumbsDisplayMobile.length && isMobile" aria-label="Breadcrumbs">
          <template #item="{ item }">
            <v-tooltip location="bottom" :text="(item as any).full">
              <template #activator="{ props }">
                <v-breadcrumbs-item v-bind="props" :to="item.to" :disabled="item.disabled" :aria-current="item.disabled ? 'page' : undefined">
                  {{ item.title }}
                </v-breadcrumbs-item>
              </template>
            </v-tooltip>
          </template>
          <template #divider>
            <v-icon icon="mdi-chevron-right"></v-icon>
          </template>
        </v-breadcrumbs>
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
            <span class="me-2">contact: ost-observatory (at) astro.physik.uni-potsdam.de</span>
            <span class="mx-2">•</span>
            <a href="https://github.com/OST-Observatory/ostdata" target="_blank" rel="noopener noreferrer" class="footer-link">
              source code
            </a>
          </div>
        </v-col>
      </v-row>
    </v-footer>
    <!-- Global notifications -->
    <div class="notify-stack" aria-live="polite" aria-atomic="true">
      <v-snackbar
        v-for="n in notify.notifications"
        :key="n.id"
        v-model="n.visible"
        :timeout="n.timeout"
        :color="n.type"
        location="bottom right"
        class="mb-2"
      >
        {{ n.text }}
        <template #actions>
          <v-btn variant="text" @click="notify.dismiss(n.id)" aria-label="Dismiss">Close</v-btn>
        </template>
      </v-snackbar>
    </div>

    <!-- Route change live announcer -->
    <div class="sr-only" aria-live="polite" aria-atomic="true">{{ documentTitle }}</div>
  </v-app>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
// @ts-ignore - allow JS store import in TS SFC
import { useAuthStore } from '@/store/auth'
import { useTheme, useDisplay } from 'vuetify'
// @ts-ignore
import { useNotifyStore } from '@/store/notify'
// @ts-ignore - JS module in TS SFC
import { api } from '@/services/api'

const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated)
const username = computed(() => authStore.username)
const isAdmin = computed(() => authStore.isAdmin)
type UiMessage = { id: string | number; type: 'info' | 'success' | 'warning' | 'error'; text: string }
const messages = ref<UiMessage[]>([])
const isFooterVisible = ref(false)
const route = useRoute()
const router = useRouter()
const vuetifyTheme = useTheme()
const notify = useNotifyStore()
const isDark = computed(() => vuetifyTheme.global.current.value.dark)
const accountMenuOpen = ref(false)
const loginMenuOpen = ref(false)
const documentTitle = computed(() => document?.title || 'OST Data Archive')
const prefetchRoute = async (path: string) => {
  try {
    if (path === '/dashboard') {
      await import('../../views/Dashboard.vue')
    } else if (path === '/objects') {
      await import('../../views/Objects.vue')
    } else if (path === '/observation-runs') {
      await import('../../views/ObservationRuns.vue')
    } else if (path === '/tags') {
      await import('../../views/Tags.vue')
    } else if (path === '/admin') {
      await import('../../views/Admin.vue')
    }
  } catch {}
}
const toggleTheme = () => {
  const newName = isDark.value ? 'ostdata' : 'dark'
  vuetifyTheme.global.name.value = newName
  try { localStorage.setItem('theme', newName) } catch {}
}
const display = useDisplay()
const isMobile = computed(() => display.smAndDown.value)

// Site-wide banner (public)
type Banner = { enabled: boolean; message: string; level: 'info' | 'success' | 'warning' | 'error' }
const banner = ref<Banner>({ enabled: false, message: '', level: 'warning' })
let bannerInterval: any = null
const fetchBanner = async () => {
  try {
    const b = await api.getBanner()
    banner.value = {
      enabled: !!b?.enabled,
      message: String(b?.message || ''),
      level: (['info','success','warning','error'].includes(b?.level) ? b.level : 'warning') as Banner['level'],
    }
  } catch {}
}

// Dynamic titles for detail routes
const dynamicDetailTitle = ref<string>('')
const dynamicObjectTitle = ref<string>('')
let lastFetchedKey = ''

const deriveDateFromName = (name: string | undefined | null) => {
  if (!name) return ''
  const n = String(name)
  if (/^\d{8}/.test(n)) {
    return `${n.slice(0, 4)}-${n.slice(4, 6)}-${n.slice(6, 8)}`
  }
  return ''
}

const refreshDynamicTitle = async () => {
  // Only for observation run detail: /observation-runs/:id
  const segs = route.path.split('/').filter(Boolean)
  if (segs.length >= 2 && segs[0] === 'observation-runs') {
    const id = segs[1]
    const key = `run:${id}`
    if (key === lastFetchedKey) return
    lastFetchedKey = key
    try {
      const run = await api.getObservationRun(id)
      const dateFromName = deriveDateFromName(run?.name)
      dynamicDetailTitle.value = dateFromName || (run?.name || id)
    } catch {
      dynamicDetailTitle.value = id
    }
    dynamicObjectTitle.value = ''
  } else if (segs.length >= 2 && segs[0] === 'objects') {
    const id = segs[1]
    const key = `obj:${id}`
    if (key === lastFetchedKey) return
    lastFetchedKey = key
    try {
      const obj = await api.getObject(id)
      dynamicObjectTitle.value = obj?.name || id
    } catch {
      dynamicObjectTitle.value = id
    }
    dynamicDetailTitle.value = ''
  } else {
    dynamicDetailTitle.value = ''
    dynamicObjectTitle.value = ''
    lastFetchedKey = ''
  }
}

// Update on navigation
watch(() => route.path, () => {
  refreshDynamicTitle()
}, { immediate: true })

type Crumb = { title: string; full: string; to?: string; disabled?: boolean }

const buildCrumbs = (): Crumb[] => {
  const items: Crumb[] = []
  // Simple mapping of known routes
  const nameMap: Record<string, string> = {
    '/': 'Dashboard',
    '/dashboard': 'Dashboard',
    '/objects': 'Objects',
    '/observation-runs': 'Observation Runs',
    '/tags': 'Tags',
  }
  const segments = route.path.split('/').filter(Boolean)
  let acc = ''
  segments.forEach((seg, idx) => {
    acc += '/' + seg
    const last = idx === segments.length - 1
    let baseTitle = nameMap['/' + seg] || nameMap[acc] || seg.replace(/-/g, ' ')
    // Use dynamic titles for detail segments
    if (segments[0] === 'observation-runs' && idx === segments.length - 1) {
      if (dynamicDetailTitle.value) baseTitle = dynamicDetailTitle.value
    }
    if (segments[0] === 'objects' && idx === segments.length - 1) {
      if (dynamicObjectTitle.value) baseTitle = dynamicObjectTitle.value
    }
    // full should be the full readable title for tooltip, not the path
    items.push({ title: baseTitle, full: baseTitle, to: last ? undefined : acc, disabled: last })
  })
  return items
}

const truncateMiddle = (s: string, max = 22) => {
  if (!s) return s
  if (s.length <= max) return s
  const head = Math.ceil((max - 1) / 2)
  const tail = Math.floor((max - 1) / 2)
  return s.slice(0, head) + '…' + s.slice(-tail)
}

const breadcrumbsDisplay = computed<Crumb[]>(() => {
  const items = buildCrumbs()
  return items.map(it => ({ ...it, title: truncateMiddle(it.title, 28) }))
})

const breadcrumbsDisplayMobile = computed<Crumb[]>(() => {
  const items = buildCrumbs()
  return items.map(it => ({ ...it, title: truncateMiddle(it.title, 18) }))
})

// Debug mode is always true for now
const isDevelopment = computed(() => true)

const checkScroll = () => {
  const scrollPosition = window.scrollY + window.innerHeight
  const documentHeight = document.documentElement.scrollHeight
  isFooterVisible.value = scrollPosition >= documentHeight - 100
}

onMounted(async () => {
  // Apply persisted theme if available
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'ostdata' || saved === 'dark') {
      vuetifyTheme.global.name.value = saved
    } else {
      // Fallback to system preference
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      vuetifyTheme.global.name.value = prefersDark ? 'dark' : 'ostdata'
    }
  } catch {}
  window.addEventListener('scroll', checkScroll)
  checkScroll() // Initial check
  
  // Check authentication status on mount
  await authStore.checkAuth()
  // Fetch banner and schedule refresh
  fetchBanner()
  bannerInterval = setInterval(fetchBanner, 60000)
})

onUnmounted(() => {
  window.removeEventListener('scroll', checkScroll)
  if (bannerInterval) {
    clearInterval(bannerInterval)
    bannerInterval = null
  }
})

const logout = async () => {
  await authStore.logout()
  try { notify.info('Logged out') } catch {}
}

// Helpers
const isActive = (base: string) => {
  return route.path === base || route.path.startsWith(base + '/')
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

/* Ensure icons in the app bar are visible on secondary background */
.on-secondary :deep(.v-icon) {
  color: rgb(var(--v-theme-on-secondary)) !important;
}

/* Subtle background for nav buttons to make them visible even without hover */
.nav-btn {
  background-color: rgba(var(--v-theme-on-secondary), 0.08) !important;
  border: 1px solid rgba(var(--v-theme-on-secondary), 0.18) !important;
  border-radius: 50% !important;
  transition: background-color 0.2s ease, box-shadow 0.2s ease, transform 0.1s ease, border-color 0.2s ease !important;
}

/* Consistent spacing between buttons */
.nav-gap {
  margin-left: 8px !important;
}

/* Pronounced ring hover/focus effect to improve discoverability */
.nav-btn:hover,
.nav-btn:focus-visible {
  background-color: rgba(var(--v-theme-on-secondary), 0.16) !important;
  border-color: rgba(var(--v-theme-on-secondary), 0.36) !important;
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.6) inset, 0 2px 6px rgba(0, 0, 0, 0.25) !important;
}

/* Slight press feedback */
.nav-btn:active {
  transform: scale(0.96);
}

/* Active tab indicator */
.nav-active {
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.85) inset !important;
  background-color: rgba(var(--v-theme-primary), 0.22) !important;
  border-color: rgba(var(--v-theme-primary), 0.5) !important;
}

a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  transition: color 0.2s;
}

a:hover {
  color: rgb(var(--v-theme-primary-dark));
}

/* Keep title from expanding so breadcrumbs sit immediately next to it */
.app-title-fixed {
  flex: 0 0 auto !important;
}

/* Breadcrumbs next to title, truncated if too long */
.breadcrumbs-appbar {
  flex: 0 1 auto;
  max-width: 50%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.breadcrumbs-appbar :deep(.v-breadcrumbs-item) {
  color: rgb(var(--v-theme-on-secondary)) !important;
}

/* Desktop primary nav layout and responsive spacing */
.primary-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}
.primary-nav .nav-gap { margin-left: 0 !important; }

@media (max-width: 1440px) {
  .breadcrumbs-appbar { max-width: 45%; }
}
@media (max-width: 1280px) {
  .breadcrumbs-appbar { max-width: 40%; }
  .primary-nav { gap: 6px; }
}
@media (max-width: 1120px) {
  .breadcrumbs-appbar { max-width: 36%; }
  .primary-nav { gap: 4px; }
}

/* Screen-reader only utility */
.sr-only {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 1px, 1px) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
</style>
