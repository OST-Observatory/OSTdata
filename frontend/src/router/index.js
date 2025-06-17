import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '@/views/Dashboard.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue')
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: Dashboard
  },
  {
    path: '/objects',
    name: 'objects',
    component: () => import('../views/Objects.vue')
  },
  {
    path: '/objects/:id',
    name: 'object-detail',
    component: () => import('../views/ObjectDetail.vue')
  },
  {
    path: '/observation-runs',
    name: 'observation-runs',
    component: () => import('../views/ObservationRuns.vue')
  },
  {
    path: '/observation-runs/:id',
    name: 'observation-run-detail',
    component: () => import('../views/ObservationRunDetail.vue')
  },
  {
    path: '/tags',
    name: 'tags',
    component: () => import('../views/Tags.vue')
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/change-password',
    name: 'change-password',
    component: () => import('../views/ChangePassword.vue')
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('../views/ResetPassword.vue')
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

export default router 