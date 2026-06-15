import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('./layouts/UserLayout.vue'),
    children: [
      { path: '', name: 'projects', component: () => import('./user/views/ProjectList.vue') },
      { path: 'project/:id', name: 'project', component: () => import('./user/views/ProjectDetail.vue') },
      { path: 'project/:id/generate', name: 'generate', component: () => import('./user/views/Generation.vue') },
      { path: 'project/:id/research', name: 'research', component: () => import('./user/views/Research.vue') },
      { path: 'project/:id/editor', name: 'editor', component: () => import('./user/views/Editor.vue') },
      { path: 'project/:id/workbench', name: 'workbench', component: () => import('./user/views/TiptapWorkbench.vue') },
    ],
  },
  {
    path: '/admin',
    component: () => import('./layouts/AdminLayout.vue'),
    children: [
      { path: '', name: 'dashboard', component: () => import('./admin/views/Dashboard.vue') },
      { path: 'knowledge', name: 'knowledge', component: () => import('./admin/views/KnowledgeBase.vue') },
      { path: 'models', name: 'models', component: () => import('./admin/views/ModelSettings.vue') },
      { path: 'audit', name: 'audit', component: () => import('./admin/views/AuditLogs.vue') },
    ],
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
