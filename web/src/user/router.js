import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'projects', component: () => import('./views/ProjectList.vue') },
  { path: '/project/:id', name: 'project', component: () => import('./views/ProjectDetail.vue') },
  { path: '/project/:id/generate', name: 'generate', component: () => import('./views/Generation.vue') },
  { path: '/project/:id/research', name: 'research', component: () => import('./views/Research.vue') },
  { path: '/project/:id/editor', name: 'editor', component: () => import('./views/Editor.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
