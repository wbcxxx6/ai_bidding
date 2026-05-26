import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 600000,
  headers: { 'Content-Type': 'application/json' }
})

export function getUserId() {
  let id = localStorage.getItem('userId')
  if (!id) {
    id = '1'
    localStorage.setItem('userId', id)
  }
  return id
}

export const projectApi = {
  list: () => http.get('/bidding/projects'),
  get: (id) => http.get(`/bidding/projects/${id}`),
  getBidding: (biddingId) => http.get(`/bidding/${biddingId}`),
  getFacts: (id) => http.get(`/bidding/projects/${id}/facts`),
  confirmFacts: (id, facts) => http.put(`/bidding/projects/${id}/facts`, { facts, userId: getUserId() }),
  getGates: (id) => http.get(`/bidding/projects/${id}/confirmation-gates`),
  confirmGate: (projectId, gateId) => http.post(`/bidding/projects/${projectId}/confirmation-gates/${gateId}/confirm`, { userId: getUserId() }),
  getEditorConfig: (projectId) => http.get(`/bidding/projects/${projectId}/editor-config`),
}

export const biddingApi = {
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    form.append('userId', getUserId())
    return http.post('/bidding/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  preAnalysis: (biddingId) => http.post('/bidding/pre-analysis_bid', { biddingId }),
  chapterDesign: (biddingId, formatReqs) => http.post('/bidding/chapter-design', { biddingId, formatRequirements: formatReqs }),
  generate: (biddingId, chapterDesign) => http.post('/bidding/generate-bid-document', { biddingId, chapterDesign, userId: getUserId() }),
  generateSSE: (biddingId, chapterDesign) => {
    const base = window.location.port === '5173' ? 'http://127.0.0.1:3012' : ''
    return fetch(`${base}/api/bidding/generate-bid-document`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ biddingId, chapterDesign, userId: getUserId() })
    })
  },
  getTask: (taskId) => http.get(`/bidding/generation-tasks/${taskId}`),
}

export const researchApi = {
  create: (projectId, data) => http.post(`/projects/${projectId}/research-tasks`, { ...data, userId: getUserId() }),
  get: (taskId) => http.get(`/research-tasks/${taskId}`),
  listReports: (projectId) => http.get(`/projects/${projectId}/research-reports`),
}

export const generationApi = {
  generateChapter: (chapterId, instruction) => http.post(`/chapters/${chapterId}/generate`, { instruction, userId: getUserId() }),
  listVersions: (chapterId) => http.get(`/chapters/${chapterId}/versions`),
  createRewrite: (chapterId, data) => http.post(`/chapters/${chapterId}/rewrite-tasks`, { ...data, userId: getUserId() }),
  applyRewrite: (taskId) => http.post(`/rewrite-tasks/${taskId}/apply`, { userId: getUserId() }),
  rejectRewrite: (taskId) => http.post(`/rewrite-tasks/${taskId}/reject`),
  reviewReport: (projectId) => http.get(`/projects/${projectId}/review-report`),
}

export const knowledgeApi = {
  list: () => http.get('/knowledge-bases'),
  create: (data) => http.post('/knowledge-bases', data),
  uploadDoc: (kbId, file, docType) => {
    const form = new FormData()
    form.append('file', file)
    form.append('docType', docType)
    form.append('userId', getUserId())
    return http.post(`/knowledge-bases/${kbId}/documents`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

export const settingsApi = {
  get: () => http.get('/settings/model-config'),
  update: (data) => http.post('/settings/model-config', { activeProvider: data.provider, model: data.model, apiKey: data.apiKey, baseUrl: data.baseUrl }),
  test: () => http.post('/settings/test-model'),
  getProviders: () => http.get('/settings/model-providers'),
}
