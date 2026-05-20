import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    name: 'Scan',
    component: () => import('@/views/ScanView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('@/views/HistoryView.vue'),
    meta: { requiresAuth: true },
  },
  // Catch-all: redirect unknown routes to home
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Navigation guard: redirect to login if not authenticated
router.beforeEach((to, _from, next) => {
  const requiresAuth = to.meta.requiresAuth !== false
  const sessionId = localStorage.getItem('session_id')

  if (requiresAuth && !sessionId) {
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router
