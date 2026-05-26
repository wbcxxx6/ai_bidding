import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/knowledge', name: 'knowledge', component: () => import('./views/KnowledgeBase.vue') },
  { path: '/models', name: 'models', component: () => import('./views/ModelSettings.vue') },
  { path: '/audit', name: 'audit', component: () => import('./views/AuditLogs.vue') },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
