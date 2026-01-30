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
    path: '/admin',
    name: 'admin',
    component: () => import('@/views/Admin.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: 'Admin', description: 'Administration panel.' }
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/admin/AdminUsers.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, requiresAnyPerms: ['users.acl_users_view','acl_users_view'], title: 'Admin – Users', description: 'Manage users and roles.' }
  },
  {
    path: '/admin/jobs',
    name: 'admin-jobs',
    component: () => import('@/views/admin/AdminJobs.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: 'Admin – Download Jobs', description: 'Monitor and control download jobs.' }
  },
  {
    path: '/admin/health',
    name: 'admin-health',
    component: () => import('@/views/admin/AdminHealth.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, requiresPerm: 'users.acl_system_health_view', title: 'Admin – Health', description: 'System health and diagnostics.' }
  },
  {
    path: '/admin/maintenance',
    name: 'admin-maintenance',
    component: () => import('@/views/admin/AdminMaintenance.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, requiresAnyPerms: ['users.acl_maintenance_cleanup','users.acl_maintenance_reconcile','users.acl_maintenance_orphans','users.acl_banner_manage','acl_maintenance_cleanup','acl_maintenance_reconcile','acl_maintenance_orphans','acl_banner_manage'], title: 'Admin – Maintenance', description: 'Data maintenance tools.' }
  },
  {
    path: '/admin/exposure-type-discrepancies',
    name: 'admin-exposure-type-discrepancies',
    component: () => import('@/views/admin/AdminExposureTypeDiscrepancies.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, title: 'Admin – Exposure Type Discrepancies', description: 'Review and resolve exposure type classification discrepancies.' }
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
  },
  {
    path: '/dark-finder',
    name: 'DarkFinder',
    component: () => import('../views/DarkFinder.vue'),
    meta: { requiresAuth: true, title: 'Dark Finder', description: 'Find matching dark frames from the archive.' }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// Global auth guard
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  // Ensure we know current auth/admin state (force-check for admin routes)
  if (!auth.isAuthenticated || (to.meta?.requiresAdmin === true)) {
    await auth.checkAuth()
  }

  if (to.meta?.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }

  if (to.meta?.requiresAdmin && !(auth.isAdmin)) {
    return { path: '/' }
  }

  // Optional ACL route gating: requiresPerm or requiresAnyPerms
  const requiresPerm = to.meta?.requiresPerm
  const requiresAny = to.meta?.requiresAnyPerms
  const has = (code) => {
    try {
      return auth.hasPerm(code)
    } catch { return false }
  }
  if (requiresPerm && !has(requiresPerm)) {
    return { path: '/' }
  }
  if (Array.isArray(requiresAny) && requiresAny.length) {
    const ok = requiresAny.some(code => has(code))
    if (!ok) return { path: '/' }
  }
})

export default router 