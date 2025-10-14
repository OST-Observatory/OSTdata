import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Vuetify
import vuetify from './plugins/vuetify'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(vuetify)
app.use(router)
app.mount('#app') 

// Global: focus-visible ring and route-based title + scroll
const applyFocusRingStyle = () => {
  const style = document.createElement('style')
  style.innerHTML = `
  :focus-visible {
    outline: 2px solid rgba(59, 130, 246, 0.9); /* blue ring */
    outline-offset: 2px;
  }
  .nav-btn:focus-visible {
    box-shadow: 0 0 0 3px rgba(255,255,255,0.85) inset, 0 0 0 2px rgba(0,0,0,0.3);
  }

  /* Global table header styling */
  .custom-table thead th,
  .custom-table thead td {
    color: rgb(var(--v-theme-primary));
    font-weight: 700;
    border-bottom: 1px solid rgba(var(--v-theme-primary), 0.25);
  }
  .custom-table thead tr:first-child th:first-child {
    border-top-left-radius: var(--v-theme-radius-md);
  }
  .custom-table thead tr:first-child th:last-child {
    border-top-right-radius: var(--v-theme-radius-md);
  }
  `
  document.head.appendChild(style)
}

applyFocusRingStyle()

router.afterEach((to) => {
  try {
    const base = 'OST Data Archive'
    const titleFromMeta = to.meta && to.meta.title ? String(to.meta.title) : ''
    document.title = titleFromMeta ? `${titleFromMeta} – ${base}` : base
    // Update or create meta description
    const desc = to.meta && to.meta.description ? String(to.meta.description) : 'Explore observation runs, objects, files, and statistics in the OST Data Archive.'
    let tag = document.querySelector('meta[name="description"]')
    if (!tag) {
      tag = document.createElement('meta')
      tag.setAttribute('name', 'description')
      document.head.appendChild(tag)
    }
    tag.setAttribute('content', desc)
  } catch {}
  try {
    const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: prefersReduced ? 'auto' : 'smooth' })
  } catch {}
})