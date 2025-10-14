import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue')
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { requiresAuth: false, title: 'Dashboard', description: 'Overview of recent activity, key statistics, and quick links in the OST Data Archive.' }
  },
  {
    path: '/objects',
    name: 'objects',
    component: () => import('../views/Objects.vue'),
    meta: { requiresAuth: false, title: 'Objects', description: 'Browse and filter astronomical objects with server-side pagination and advanced search.' }
  },
  {
    path: '/objects/:id',
    name: 'object-detail',
    component: () => import('../views/ObjectDetail.vue'),
    meta: { requiresAuth: false, title: 'Object', description: 'Object details including coordinates, observation runs, files, and tags.' }
  },
  {
    path: '/observation-runs',
    name: 'observation-runs',
    component: () => import('../views/ObservationRuns.vue'),
    meta: { requiresAuth: false, title: 'Observation Runs', description: 'Browse and filter observation runs with server-side pagination and sorting.' }
  },
  {
    path: '/observation-runs/:id',
    name: 'observation-run-detail',
    component: () => import('../views/ObservationRunDetail.vue'),
    meta: { requiresAuth: false, title: 'Observation Run', description: 'Observation run details including time range, status, associated objects, and plots.' }
  },
  {
    path: '/tags',
    name: 'tags',
    component: () => import('../views/Tags.vue'),
    meta: { requiresAuth: false, title: 'Tags', description: 'View and manage tags used to organize objects and files.' }
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: 'Login', description: 'Sign in to the OST Data Archive.' }
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('../views/ChangePassword.vue'),
    meta: { title: 'Change Password', description: 'Change your account password.' }
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('../views/ResetPassword.vue'),
    meta: { title: 'Reset Password', description: 'Request a password reset link by email.' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// Global auth guard
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // Ensure we know current auth state
  if (!auth.isAuthenticated) {
    await auth.checkAuth()
  }

  if (to.meta?.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }
})

export default router 