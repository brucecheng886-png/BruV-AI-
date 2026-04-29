import { useAuthStore } from '../stores/auth.js'

// ── 全域並發限制器（防止頁面初始化時同時打爆 nginx burst） ──────────────────
const MAX_CONCURRENT = 6
let _activeCount = 0
const _queue = []

function _acquire() {
  return new Promise(resolve => {
    if (_activeCount < MAX_CONCURRENT) { _activeCount++; resolve() }
    else { _queue.push(resolve) }
  })
}

function _release() {
  if (_queue.length > 0) { _queue.shift()() }
  else { _activeCount-- }
}

async function apiFetch(input, init) {
  await _acquire()
  try { return await fetch(input, init) }
  finally { _release() }
}
// ──────────────────────────────────────────────────────────────────────────────

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
    return apiFetch(`/api/documents?${qs}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  count: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch(`/api/documents/count${qs ? '?' + qs : ''}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  upload: (file, kbId = null) => {
    const fd = new FormData()
    fd.append('file', file)
    if (kbId) fd.append('knowledge_base_id', kbId)
    const auth = useAuthStore()
    return apiFetch('/api/documents/upload', {
      method: 'POST',
      headers: auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {},
      body: fd,
    }).then(handleResponse)
  },
  delete: (id) => apiFetch(`/api/documents/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  getChunks: (id, params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch(`/api/documents/${id}/chunks?${qs}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  getChunk: (chunkId) =>
    apiFetch(`/api/documents/chunks/${chunkId}`, { headers: getHeaders(false) }).then(handleResponse),
  moveToKb: (docId, kbId) =>
    apiFetch(`/api/documents/${docId}/kb`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify({ knowledge_base_id: kbId }),
    }).then(handleResponse),
  aiSearch: (query, kbId = null, topK = 10) =>
    apiFetch('/api/documents/search', {
      method: 'POST', headers: getHeaders(),
      body: JSON.stringify({ query, kb_id: kbId, top_k: topK }),
    }).then(handleResponse),
  updateMeta: (docId, body) =>
    apiFetch(`/api/documents/${docId}/meta`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify(body),
    }).then(handleResponse),
  reanalyze: (docId) =>
    apiFetch(`/api/documents/${docId}/reanalyze`, {
      method: 'POST', headers: getHeaders(false),
    }).then(handleResponse),
  confirmKbSuggestion: (docId, action) =>
    apiFetch(`/api/documents/${docId}/knowledge-base`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify({ action }),
    }).then(handleResponse),
  confirmKbs: (docId, action, kbIds = []) =>
    apiFetch(`/api/documents/${docId}/knowledge-bases`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify({ action, kb_ids: kbIds }),
    }).then(handleResponse),
  confirmTagSuggestions: (docId, action, tagIds = []) =>
    apiFetch(`/api/documents/${docId}/tags/suggestions`, {
      method: 'PATCH', headers: getHeaders(),
      body: JSON.stringify({ action, tag_ids: tagIds }),
    }).then(handleResponse),
  importExcel: (file, kbId = null) => {
    const fd = new FormData()
    fd.append('file', file)
    if (kbId) fd.append('knowledge_base_id', kbId)
    const auth = useAuthStore()
    return apiFetch('/api/documents/import-excel', {
      method: 'POST',
      headers: auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {},
      body: fd,
    }).then(handleResponse)
  },
  smartImport: (urls, kbId = null) =>
    apiFetch('/api/documents/smart-import', {
      method: 'POST', headers: getHeaders(),
      body: JSON.stringify({ urls, knowledge_base_id: kbId }),
    }).then(handleResponse),
  smartImportConfirm: (items) =>
    apiFetch('/api/documents/smart-import/confirm', {
      method: 'POST', headers: getHeaders(),
      body: JSON.stringify({ items }),
    }).then(handleResponse),
  trash: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch(`/api/documents/trash${qs ? '?' + qs : ''}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  restore: (id) =>
    apiFetch(`/api/documents/${id}/restore`, { method: 'POST', headers: getHeaders(false) }).then(handleResponse),
  permanentDelete: (id) =>
    apiFetch(`/api/documents/${id}/permanent`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  download: async (docId) => {
    const resp = await apiFetch(`/api/documents/${docId}/download`, { headers: getHeaders(false) })
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
  list: () => apiFetch('/api/knowledge-bases', { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    apiFetch('/api/knowledge-bases', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  update: (id, body) =>
    apiFetch(`/api/knowledge-bases/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  delete: (id) =>
    apiFetch(`/api/knowledge-bases/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}

// Ontology
export const ontologyApi = {
  reviewQueue: (status = 'pending') =>
    apiFetch(`/api/ontology/review-queue?status=${status}`, { headers: getHeaders(false) }).then(handleResponse),
  approve: (id) =>
    apiFetch(`/api/ontology/review-queue/${id}/approve`, { method: 'POST', headers: getHeaders() }).then(handleResponse),
  reject: (id) =>
    apiFetch(`/api/ontology/review-queue/${id}/reject`, { method: 'POST', headers: getHeaders() }).then(handleResponse),
  blocklist: () =>
    apiFetch('/api/ontology/blocklist', { headers: getHeaders(false) }).then(handleResponse),
  deleteBlocklist: (id) =>
    apiFetch(`/api/ontology/blocklist/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  graph: () =>
    apiFetch('/api/ontology/graph', { headers: getHeaders(false) }).then(handleResponse),
  batchApprove: (body) =>
    apiFetch('/api/ontology/review-queue/batch-approve', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  batchReject: (body) =>
    apiFetch('/api/ontology/review-queue/batch-reject', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
}

// Wiki / LLM Models
export const wikiApi = {
  list: (q = '') =>
    apiFetch(`/api/wiki/models${q ? '?q=' + encodeURIComponent(q) : ''}`, { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    apiFetch('/api/wiki/models', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  get: (id) =>
    apiFetch(`/api/wiki/models/${id}`, { headers: getHeaders(false) }).then(handleResponse),
  update: (id, body) =>
    apiFetch(`/api/wiki/models/${id}`, { method: 'PUT', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  delete: (id) =>
    apiFetch(`/api/wiki/models/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  updateGovernance: (id, body) =>
    apiFetch(`/api/wiki/models/${id}/governance`, { method: 'PATCH', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  compare: (idA, idB) =>
    apiFetch(`/api/wiki/models/compare/two?id_a=${idA}&id_b=${idB}`, { headers: getHeaders(false) }).then(handleResponse),
  verifyModel: (body) =>
    apiFetch('/api/wiki/models/verify', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
}

// Monitoring (Phase B6)
export const monitoringApi = {
  getUsageSummary: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.start) qs.set('start', params.start)
    if (params.end)   qs.set('end',   params.end)
    if (params.user_id) qs.set('user_id', params.user_id)
    const q = qs.toString()
    return apiFetch(`/api/monitoring/usage${q ? '?' + q : ''}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  getUsageDaily: (days = 30, user_id = null) => {
    const qs = new URLSearchParams({ days: String(days) })
    if (user_id) qs.set('user_id', user_id)
    return apiFetch(`/api/monitoring/usage/daily?${qs.toString()}`, { headers: getHeaders(false) }).then(handleResponse)
  },
}

// Plugins
export const pluginsApi = {
  list: () =>
    apiFetch('/api/plugins', { headers: getHeaders(false) }).then(handleResponse),
  catalog: () =>
    apiFetch('/api/plugins/catalog/list', { headers: getHeaders(false) }).then(handleResponse),
  create: (body) =>
    apiFetch('/api/plugins', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  update: (id, body) =>
    apiFetch(`/api/plugins/${id}`, { method: 'PATCH', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  toggle: (id, enabled) =>
    apiFetch(`/api/plugins/${id}/toggle`, { method: 'POST', headers: getHeaders() }).then(handleResponse),
  invoke: (id, payload) =>
    apiFetch(`/api/plugins/${id}/invoke`, { method: 'POST', headers: getHeaders(), body: JSON.stringify(payload) }).then(handleResponse),
  delete: (id) =>
    apiFetch(`/api/plugins/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}

// System Settings (LLM Provider)
export const systemSettingsApi = {
  getLlm: () =>
    apiFetch('/api/settings/llm', { headers: getHeaders(false) }).then(handleResponse),
  saveLlm: (body) =>
    apiFetch('/api/settings/llm', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  testLlm: (provider, apiKey) =>
    apiFetch('/api/settings/llm/test', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ provider, api_key: apiKey }) }).then(handleResponse),
  // RAG 參數
  getRag: () =>
    apiFetch('/api/settings/rag', { headers: getHeaders(false) }).then(handleResponse),
  saveRag: (body) =>
    apiFetch('/api/settings/rag', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  // 備份
  triggerBackup: () =>
    apiFetch('/api/settings/backup/trigger', { method: 'POST', headers: getHeaders() }).then(handleResponse),
  listBackups: () =>
    apiFetch('/api/settings/backup/list', { headers: getHeaders(false) }).then(handleResponse),
  // 密碼修改
  changePassword: (current_password, new_password) =>
    apiFetch('/api/settings/user/change-password', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ current_password, new_password }) }).then(handleResponse),
  getModels: () =>
    apiFetch('/api/settings/models', { headers: getHeaders(false) }).then(handleResponse),
  // 知識庫 Schema
  getSchema: () =>
    apiFetch('/api/settings/schema', { headers: getHeaders(false) }).then(handleResponse),
  saveSchema: (schema_text) =>
    apiFetch('/api/settings/schema', { method: 'PUT', headers: getHeaders(), body: JSON.stringify({ schema_text }) }).then(handleResponse),
  // 對話行為設定
  getChatBehavior: () =>
    apiFetch('/api/settings/chat', { headers: getHeaders(false) }).then(handleResponse),
  saveChatBehavior: (body) =>
    apiFetch('/api/settings/chat', { method: 'POST', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
}

// Chat stream returns raw response for ReadableStream processing
export async function chatStream(query, conversationId, model, signal = null, docIds = [], kbScopeId = null, docScopeIds = [], tagScopeIds = [], agentType = 'chat', mode = 'agent') {
  const auth = useAuthStore()
  const body = { query, conversation_id: conversationId, model, agent_type: agentType, mode }
  if (docIds && docIds.length) body.doc_ids = docIds
  if (kbScopeId) body.kb_scope_id = kbScopeId
  if (docScopeIds && docScopeIds.length) body.doc_scope_ids = docScopeIds
  if (tagScopeIds && tagScopeIds.length) body.tag_scope_ids = tagScopeIds
  return fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {}),
    },
    body: JSON.stringify(body),
    ...(signal ? { signal } : {}),
  })
}

export async function chatStreamWithFile(query, conversationId, model, file, signal = null, docIds = [], kbScopeId = null, docScopeIds = [], tagScopeIds = [], agentType = 'chat', mode = 'agent') {
  const auth = useAuthStore()
  const fd = new FormData()
  fd.append('query', query)
  if (conversationId) fd.append('conversation_id', conversationId)
  if (model) fd.append('model', model)
  fd.append('agent_type', agentType || 'chat')
  fd.append('mode', mode || 'agent')
  if (docIds && docIds.length) fd.append('doc_ids', JSON.stringify(docIds))
  if (kbScopeId) fd.append('kb_scope_id', kbScopeId)
  if (docScopeIds && docScopeIds.length) fd.append('doc_scope_ids', JSON.stringify(docScopeIds))
  if (tagScopeIds && tagScopeIds.length) fd.append('tag_scope_ids', JSON.stringify(tagScopeIds))
  if (file) fd.append('file', file)
  return fetch('/api/chat/stream-with-file', {
    method: 'POST',
    headers: {
      ...(auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {}),
    },
    body: fd,
    ...(signal ? { signal } : {}),
  })
}

export const chatApi = {
  saveToKb: (msgId) =>
    apiFetch(`/api/chat/messages/${msgId}/save_to_kb`, { method: 'POST', headers: getHeaders(false) }).then(handleResponse),
}

export const conversationsApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return apiFetch(`/api/chat/conversations${qs ? '?' + qs : ''}`, { headers: getHeaders(false) }).then(handleResponse)
  },
  get: (id) => apiFetch(`/api/chat/conversations/${id}`, { headers: getHeaders(false) }).then(handleResponse),
  create: (kbScopeId = null, docScopeIds = [], tagScopeIds = [], agentType = 'chat', agentMeta = {}) => apiFetch('/api/chat/conversations', {
    method: 'POST', headers: getHeaders(),
    body: JSON.stringify({ kb_scope_id: kbScopeId, doc_scope_ids: docScopeIds, tag_scope_ids: tagScopeIds, agent_type: agentType, agent_meta: agentMeta }),
  }).then(handleResponse),
  delete: (id) => apiFetch(`/api/chat/conversations/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  rename: (id, title) => apiFetch(`/api/chat/conversations/${id}`, {
    method: 'PATCH', headers: getHeaders(),
    body: JSON.stringify({ title }),
  }).then(handleResponse),
}

export const agentApi = {
  run: (instruction, model) => apiFetch('/api/agent/run', {
    method: 'POST', headers: getHeaders(),
    body: JSON.stringify({ instruction, model }),
  }).then(handleResponse),
  getTask: (taskId) => apiFetch(`/api/agent/tasks/${taskId}`, { headers: getHeaders(false) }).then(handleResponse),
}

export const proteinApi = {
  import: (files) => {
    const auth = useAuthStore()
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    return apiFetch('/api/protein/import', {
      method: 'POST',
      headers: auth.token ? { 'Authorization': `Bearer ${auth.token}` } : {},
      body: fd,
    }).then(handleResponse)
  },
  networks: () => apiFetch('/api/protein/networks', { headers: getHeaders(false) }).then(handleResponse),
  graph: (network = 'USP7', minScore = 0.5) =>
    apiFetch(`/api/protein/graph?network=${encodeURIComponent(network)}&min_score=${minScore}`, {
      headers: getHeaders(false),
    }).then(handleResponse),
  top: (network = 'USP7', limit = 20) =>
    apiFetch(`/api/protein/top?network=${encodeURIComponent(network)}&limit=${limit}`, {
      headers: getHeaders(false),
    }).then(handleResponse),
  stats: (network = 'USP7', threshold = 0) =>
    apiFetch(`/api/protein/stats?network=${encodeURIComponent(network)}&threshold=${threshold}`, {
      headers: getHeaders(false),
    }).then(handleResponse),
}

// Tags
export const tagsApi = {
  list: () =>
    apiFetch('/api/tags/', { headers: getHeaders(false) }).then(handleResponse),
  create: (name, color = '#409eff', description = null) =>
    apiFetch('/api/tags/', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ name, color, description }) }).then(handleResponse),
  update: (id, body) =>
    apiFetch(`/api/tags/${id}`, { method: 'PATCH', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  delete: (id) =>
    apiFetch(`/api/tags/${id}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  removeFromAll: (id) =>
    apiFetch(`/api/tags/${id}/documents/all`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
  addToDoc: (tagId, docId) =>
    apiFetch(`/api/tags/${tagId}/documents/${docId}`, { method: 'POST', headers: getHeaders(false) }).then(handleResponse),
  removeFromDoc: (tagId, docId) =>
    apiFetch(`/api/tags/${tagId}/documents/${docId}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}

// Agent Skills
export const agentSkillsApi = {
  list: () =>
    apiFetch('/api/agent-skills/', { headers: getHeaders(false) }).then(handleResponse),
  update: (pageKey, body) =>
    apiFetch(`/api/agent-skills/${pageKey}`, { method: 'PATCH', headers: getHeaders(), body: JSON.stringify(body) }).then(handleResponse),
  available: () =>
    apiFetch('/api/agent-skills/store/available', { headers: getHeaders(false) }).then(handleResponse),
  install: (pageKey) =>
    apiFetch('/api/agent-skills/store/install', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ page_key: pageKey }) }).then(handleResponse),
  uninstall: (pageKey) =>
    apiFetch(`/api/agent-skills/store/${pageKey}`, { method: 'DELETE', headers: getHeaders(false) }).then(handleResponse),
}
