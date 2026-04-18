import { useAuthStore } from '../stores/auth.js'

function getHeaders(json = true) {
  const auth = useAuthStore()
  const h = {}
  if (auth.token) h['Authorization'] = `Bearer ${auth.token}`
  if (json) h['Content-Type'] = 'application/json'
  return h
}

async function handleResponse(resp) {
  if (!resp.ok) {
    // 401 → token 過期或無效，清除並導向登入頁
    if (resp.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      window.location.href = '/login'
      throw new Error('登入已過期，請重新登入')
    }
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      if (typeof data.detail === 'string') {
        detail = data.detail
      } else if (Array.isArray(data.detail)) {
        detail = data.detail.map(e => e.msg || JSON.stringify(e)).join('; ')
      } else if (data.detail) {
        detail = JSON.stringify(data.detail)
      }
    } catch {}
    throw new Error(detail)
  }
  if (resp.status === 204 || resp.status === 205) return null
  return resp.json()
}

// Documents
export const docsApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return fetch(`/api/documents?${qs}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  upload: (file, kbId = null) => {
    const fd = new FormData()
    fd.append('file', file)
    if (kbId) fd.append('knowledge_base_id', kbId)
    const auth = useAuthStore()
    return fetch('/api/documents/upload', {
      method: 'POST',
      headers: auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {},
      body: fd,
    }).then(handleResponse)
  },
  delete: (id) => fetch(`/api/documents/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  getChunks: (id, params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return fetch(`/api/documents/${id}/chunks?${qs}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  moveToKb: (docId, kbId) =>
    fetch(`/api/documents/${docId}/kb`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify({ knowledge_base_id: kbId }),
    }).then(handleResponse),
  aiSearch: (query, kbId = null, topK = 10) =>
    fetch('/api/documents/search', {
      method: 'POST', headers: getHeaders(),
      body: JSON.stringify({ query, kb_id: kbId, top_k: topK }),
    }).then(handleResponse),
  updateMeta: (docId, body) =>
    fetch(`/api/documents/${docId}/meta`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify(body),
    }).then(handleResponse),
  reanalyze: (docId) =>
    fetch(`/api/documents/${docId}/reanalyze`, {
      method: 'POST', headers: getHeaders(false),
    }).then(handleResponse),
  download: async (docId) => {
    const resp = await fetch(`/api/documents/${docId}/download`, { headers: getHeaders(false) })
    if (!resp.ok) {
      if (resp.status === 401) {
        const auth = useAuthStore()
        auth.logout()
        window.location.href = '/login'
        throw new Error('登入已過期，請重新登入')
      }
      let detail = `HTTP ${resp.status}`
      try {
        const data = await resp.json()
        detail = typeof data.detail === 'string' ? data.detail : `HTTP ${resp.status}`
      } catch {}
      throw new Error(detail)
    }
    return resp.arrayBuffer()
  },
}

// Knowledge Bases
export const kbApi = {
  list: () => fetch('/api/knowledge-bases', { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    fetch('/api/knowledge-bases', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  update: (id, body) =>
    fetch(`/api/knowledge-bases/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  delete: (id) =>
    fetch(`/api/knowledge-bases/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}

// Ontology
export const ontologyApi = {
  reviewQueue: (status = 'pending') =>
    fetch(`/api/ontology/review-queue?status=${status}`, { headers: getHeaders(false) }).then(handleResponse),
  approve: (id) =>
    fetch(`/api/ontology/review-queue/${id}/approve`, { method: 'POST', headers: getHeaders() }).then(handleResponse),
  reject: (id) =>
    fetch(`/api/ontology/review-queue/${id}/reject`, { method: 'POST', headers: getHeaders() }).then(handleResponse),
  blocklist: () =>
    fetch('/api/ontology/blocklist', { headers: getHeaders(false) }).then(handleResponse),
  deleteBlocklist: (id) =>
    fetch(`/api/ontology/blocklist/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  graph: () =>
    fetch('/api/ontology/graph', { headers: getHeaders(false) }).then(handleResponse),
}

// Wiki / LLM Models
export const wikiApi = {
  list: (q = '') =>
    fetch(`/api/wiki/models${q ? '?q=' + encodeURIComponent(q) : ''}`, { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    fetch('/api/wiki/models', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  get: (id) =>
    fetch(`/api/wiki/models/${id}`, { headers: getHeaders(false) }).then(handleResponse),
  update: (id, body) =>
    fetch(`/api/wiki/models/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  delete: (id) =>
    fetch(`/api/wiki/models/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  compare: (idA, idB) =>
    fetch(`/api/wiki/models/compare/two?id_a=${idA}&id_b=${idB}`, { headers: getHeaders(false) }).then(handleResponse),
  verifyModel: (body) =>
    fetch('/api/wiki/models/verify', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
}

// Plugins
export const pluginsApi = {
  list: () =>
    fetch('/api/plugins', { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    fetch('/api/plugins', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  toggle: (id, enabled) =>
    fetch(`/api/plugins/${id}`, { method: 'PATCH', headers: getHeaders(), body: JSON.stringify({ enabled }) }).then(handleResponse),
  delete: (id) =>
    fetch(`/api/plugins/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}

// System Settings (LLM Provider)
export const systemSettingsApi = {
  getLlm: () =>
    fetch('/api/settings/llm', { headers: getHeaders(false) }).then(handleResponse),
  saveLlm: (body) =>
    fetch('/api/settings/llm', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  testLlm: (provider, apiKey) =>
    fetch('/api/settings/llm/test', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ provider, api_key: apiKey }) }).then(handleResponse),
  // RAG 參數
  getRag: () =>
    fetch('/api/settings/rag', { headers: getHeaders(false) }).then(handleResponse),
  saveRag: (body) =>
    fetch('/api/settings/rag', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  // 備份
  triggerBackup: () =>
    fetch('/api/settings/backup/trigger', { method: 'POST', headers: getHeaders() }).then(handleResponse),
  listBackups: () =>
    fetch('/api/settings/backup/list', { headers: getHeaders(false) }).then(handleResponse),
  // 密碼修改
  changePassword: (current_password, new_password) =>
    fetch('/api/settings/user/change-password', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ current_password, new_password }) }).then(handleResponse),
  getModels: () =>
    fetch('/api/settings/models', { headers: getHeaders(false) }).then(handleResponse),
}

// Chat stream returns raw response for ReadableStream processing
export async function chatStream(query, conversationId, model) {
  const auth = useAuthStore()
  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {}),
    },
    body: JSON.stringify({ query, conversation_id: conversationId, model }),
  })
}

export const conversationsApi = {
  list: () => fetch('/api/chat/conversations', { headers: getHeaders(false) }).then(handleResponse),
  get: (id) => fetch(`/api/chat/conversations/${id}`, { headers: getHeaders(false) }).then(handleResponse),
  delete: (id) => fetch(`/api/chat/conversations/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}
