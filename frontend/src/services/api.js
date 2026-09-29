import axios from 'axios'

const TOKEN_KEY = 'cm_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const t = tokenStore.get()
  if (t) config.headers.Authorization = `Bearer ${t}`
  return config
})

// An expired or revoked session sends the user back to the login page instead of showing cryptic errors.
api.interceptors.response.use((r) => r, (e) => {
  const onAuthPage = ['/login', '/register', '/'].includes(window.location.pathname)
  if (e.response?.status === 401 && tokenStore.get() && !onAuthPage && !e.config.url.includes('/auth/')) {
    tokenStore.clear()
    window.location.assign('/login?expired=1')
  }
  return Promise.reject(e)
})

/** A short, human-readable message for any API error. */
export const errorMessage = (e) => {
  const d = e.response?.data?.detail
  if (Array.isArray(d)) return d[0]?.msg ?? 'Please check the form and try again.'
  if (typeof d === 'string') return d
  if (d?.message) return d.message
  if (e.code === 'ERR_NETWORK') return 'Cannot reach the server. Is the backend running?'
  return e.message
}

const data = (r) => r.data

export const authApi = {
  register: (body) => api.post('/auth/register', body).then(data),
  login: (body) => api.post('/auth/login', body).then(data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me').then(data),
}

export const coursesApi = {
  list: () => api.get('/courses').then(data),
  get: (id) => api.get(`/courses/${id}`).then(data),
  retry: (id) => api.post(`/courses/${id}/retry`).then(data),
  remove: (id) => api.delete(`/courses/${id}`),
  overview: (id) => api.get(`/courses/${id}/overview`).then(data),
}

export const inputApi = {
  upload: (file, onProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/upload', fd, { onUploadProgress: (e) => e.total && onProgress?.(Math.round((100 * e.loaded) / e.total)) }).then(data)
  },
  getUpload: (id) => api.get(`/upload/${id}`).then(data),
  submitGoal: (body) => api.post('/goal', body).then(data),
}

export const curriculumApi = {
  get: (id) => api.get(`/curriculum/${id}`).then(data),
  revise: (id, feedback, curriculum) => api.post('/curriculum/revise', { curriculum_id: id, feedback, curriculum }).then(data),
  verify: (id, curriculum) => api.post('/curriculum/verify', { curriculum_id: id, curriculum }).then(data),
}

export const graphApi = {
  get: (id) => api.get(`/graph/${id}`).then(data),
  knowledge: (id) => api.get(`/graph/${id}/knowledge`).then(data),
  validate: (id, graph) => api.post('/graph/validate', { curriculum_id: id, graph }).then(data),
  verify: (id, graph) => api.post('/graph/verify', { curriculum_id: id, graph }).then(data),
  reject: (id, feedback, graph) => api.post('/graph/reject', { curriculum_id: id, feedback, graph }).then(data),
  revise: (id, feedback, graph) => api.post('/graph/revise', { curriculum_id: id, feedback, graph }).then(data),
}

export const sequencingApi = {
  get: (id) => api.get(`/sequencing/${id}`).then(data),
  generate: (id, params, feedback) => api.post('/sequencing/generate', { curriculum_id: id, params, feedback }).then(data),
  validate: (id, plan) => api.post('/sequencing/validate', { curriculum_id: id, plan }).then(data),
  verify: (id, plan) => api.post('/sequencing/verify', { curriculum_id: id, plan }).then(data),
  reject: (id, feedback) => api.post('/sequencing/reject', { curriculum_id: id, feedback }).then(data),
}

export const resourcesApi = {
  get: (id) => api.get(`/resources/${id}`).then(data),
  search: (id) => api.post('/resources/search', { curriculum_id: id }).then(data),
  analyze: (id) => api.post('/resources/analyze', { curriculum_id: id }).then(data),
}

export const pathApi = {
  get: (userId, curriculumId) => api.get(`/learning-path/${userId}`, { params: curriculumId ? { curriculum_id: curriculumId } : {} }).then(data),
  enroll: (id) => api.post('/learning-path/enroll', { curriculum_id: id }).then(data),
}

export const quizApi = {
  generate: (curriculumId, conceptIds) => api.post('/quiz/generate', { curriculum_id: curriculumId, concept_ids: conceptIds }).then(data),
  status: (curriculumId, conceptIds) => api.get('/quiz/status', { params: { curriculum_id: curriculumId, concept_ids: conceptIds }, paramsSerializer: { indexes: null } }).then(data),
  get: (quizId) => api.get(`/quiz/${quizId}`).then(data),
  submit: (quizId, answers) => api.post('/quiz/submit', { quiz_id: quizId, answers }).then(data),
  history: (curriculumId) => api.get('/quiz/history', { params: { curriculum_id: curriculumId } }).then(data),
}

export const adaptiveApi = {
  generate: (curriculumId, hoursPerWeek) => api.post('/adaptive-path/generate', { curriculum_id: curriculumId, hours_per_week: hoursPerWeek }).then(data),
}

export const dashboardApi = {
  learner: (userId, curriculumId) => api.get(`/dashboard/learner/${userId}`, { params: curriculumId ? { curriculum_id: curriculumId } : {} }).then(data),
}

export default api
