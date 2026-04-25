<script setup>
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { chatStream, agentApi, kbApi, docsApi, conversationsApi, ontologyApi, pluginsApi, wikiApi } from '../api/index.js'
import { useChatStore } from '../stores/chat.js'
import { Monitor, Globe, BookOpen, X, ArrowUp, Square, Plus, Paperclip, FileSpreadsheet, Bot, MessageCircle, ListChecks, Clock, ChevronDown, Check, Copy } from 'lucide-vue-next'
import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import sql from 'highlight.js/lib/languages/sql'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import { ElMessage } from 'element-plus'

const chatStore = useChatStore()

// ── highlight.js ─────────────────────────────────────
;[['javascript', javascript], ['python', python], ['typescript', typescript],
  ['sql', sql], ['bash', bash], ['shell', bash], ['json', json],
  ['xml', xml], ['html', xml], ['css', css]
].forEach(([name, mod]) => hljs.registerLanguage(name, mod))

// ── marked ──────────────────────────────────────────
marked.use({
  breaks: true,
  gfm: true,
  renderer: {
    code({ text, lang }) {
      const language = lang && hljs.getLanguage(lang) ? lang : ''
      const highlighted = language
        ? hljs.highlight(text, { language }).value
        : hljs.highlightAuto(text).value
      const encoded = encodeURIComponent(text)
      return `<div class="code-block" data-code="${encoded}"><div class="code-header"><span class="code-lang">${language || 'text'}</span><button class="code-copy-btn" type="button">複製</button></div><pre><code class="hljs">${highlighted}</code></pre></div>`
    }
  }
})

function renderMd(text) {
  if (!text) return ''
  try { return marked.parse(text.replace(/__action__:\{[^\n]+\}/g, '').trimEnd()) } catch { return text }
}

function onMsgAreaClick(e) {
  const btn = e.target.closest('.code-copy-btn')
  if (!btn) return
  const block = btn.closest('.code-block')
  if (!block) return
  const code = decodeURIComponent(block.dataset.code || '')
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = '已複製 ✓'
    setTimeout(() => { btn.textContent = '複製' }, 2000)
  }).catch(() => ElMessage.error('複製失敗'))
}

function copyText(text) {
  navigator.clipboard.writeText(text || '').then(() => ElMessage.success('已複製'))
}

// ── Props / Emits ─────────────────────────────────────────
const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// ── Router ────────────────────────────────────────────────
const route = useRoute()

// 在 /chat 與 / 頁面隱藏面板與 FAB（但元件仍挨載以保留串流狀態）
const isHiddenPage = computed(() => route.path === '/chat' || route.path === '/')

// [DEBUG] 追蹤 FAB 顯示條件
watchEffect(() => {
  console.log('[FAB]', 'route.path:', route.path, 'isHiddenPage:', isHiddenPage.value, 'modelValue:', props.modelValue)
})

// ── Page info ─────────────────────────────────────────────
const PAGE_INFO = {
  '/docs':     { name: '文件管理',  agentType: 'page_agent:docs' },
  '/ontology': { name: '知識圖譜',  agentType: 'page_agent:ontology' },
  '/plugins':  { name: '插件管理',  agentType: 'page_agent:plugins' },
  '/protein':  { name: '蛋白質圖譜', agentType: 'page_agent:protein' },
  '/settings': { name: '系統設定',  agentType: 'page_agent:settings' },
  '/chat':     { name: '對話',      agentType: 'page_agent:chat' },
}

const currentPageInfo = computed(() =>
  PAGE_INFO[route.path] || { name: '目前頁面', agentType: 'page_agent:unknown' }
)

// ── KB list（給 scope segment 的 popover 使用） ──────────
const knowledgeBases = ref([])

// ── Scope system ──────────────────────────────────────────
// Scope key 規則：
//   'global'           → 全域 Agent
//   'page:/docs'       → 頁面 Agent（依路徑）
//   'kb:{kb_id}'       → 知識庫 Agent（依 KB id）
const scopeStates = reactive({})
const activeScope = ref('global')

function getScopeState(key) {
  if (!scopeStates[key]) scopeStates[key] = { messages: [], convId: null, streaming: false }
  return scopeStates[key]
}

const currentScopeState = computed(() => getScopeState(activeScope.value))

const activeScopeLabel = computed(() => {
  const s = activeScope.value
  if (s === 'global') return '全域'
  if (s.startsWith('page:')) {
    const path = s.slice(5)
    return (PAGE_INFO[path] && PAGE_INFO[path].name) || '頁面'
  }
  if (s.startsWith('kb:')) {
    const id = s.slice(3)
    const kb = knowledgeBases.value.find(k => String(k.id) === String(id))
    return kb ? kb.name : '知識庫'
  }
  return s
})

const activeScopeAgentType = computed(() => {
  const s = activeScope.value
  if (s === 'global') return 'global_agent'
  if (s.startsWith('page:')) {
    const path = s.slice(5)
    return (PAGE_INFO[path] && PAGE_INFO[path].agentType) || 'page_agent:unknown'
  }
  if (s.startsWith('kb:')) return 'kb_agent'
  return 'global_agent'
})

const activeScopeKbId = computed(() => {
  const s = activeScope.value
  return s.startsWith('kb:') ? s.slice(3) : null
})

// (legacy tab aliases removed in Step 3)


// ── Agent mode & model ────────────────────────────────────
const agentMode      = ref('agent')  // 'agent' | 'ask' | 'plan'
const selectedModel  = ref('')
const localModels    = ref([])
const cloudModels    = ref([])
const modelPopoverVisible = ref(false)
const availableModels = computed(() => [
  ...localModels.value,
  ...cloudModels.value.map(m => m.name),
])
const MODE_LABELS = { agent: 'Agent', ask: 'Ask', plan: 'Plan' }
const MODE_ICONS  = { agent: Bot, ask: MessageCircle, plan: ListChecks }

// ── Scope popover state ──────────────────────────────────
const pagePopoverOpen = ref(false)
const kbPopoverOpen   = ref(false)
const pageOptions = computed(() =>
  Object.entries(PAGE_INFO).map(([path, info]) => ({ path, name: info.name }))
)

function selectPageScope(path) {
  activeScope.value = 'page:' + path
  pagePopoverOpen.value = false
}
function selectKbScope(kbId) {
  activeScope.value = 'kb:' + kbId
  kbPopoverOpen.value = false
}
function selectGlobalScope() {
  activeScope.value = 'global'
}

// ── History ──────────────────────────────────────────────
const historyOpen    = ref(false)
const historyLoading = ref(false)
const historyCache   = ref({})   // { [scopeKey]: ConversationOut[] }

watch(activeScope, () => { historyOpen.value = false })

async function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value && !historyCache.value[activeScope.value]) {
    await loadHistory(activeScope.value)
  }
}

async function loadHistory(scopeKey) {
  historyLoading.value = true
  let agentType
  if (scopeKey === 'global') agentType = 'global_agent'
  else if (scopeKey.startsWith('kb:')) agentType = 'kb_agent'
  else if (scopeKey.startsWith('page:')) {
    const path = scopeKey.slice(5)
    agentType = (PAGE_INFO[path] && PAGE_INFO[path].agentType) || 'page_agent:unknown'
  } else {
    agentType = 'global_agent'
  }
  try {
    const items = await conversationsApi.list({ agent_type: agentType, limit: 30 })
    historyCache.value = { ...historyCache.value, [scopeKey]: Array.isArray(items) ? items : [] }
  } catch {}
  historyLoading.value = false
}

async function loadConversation(conv) {
  const tab = currentScopeState.value
  chatStore.agentTabConvIds[activeScope.value] = conv.id
  tab.convId = conv.id
  tab.messages = []
  historyOpen.value = false
  try {
    const msgs = await conversationsApi.get(conv.id)
    tab.messages = (Array.isArray(msgs) ? msgs : [])
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({
        role: m.role,
        content: m.role === 'user'
          ? m.content.replace(/^\[頁面狀態\][\s\S]*?\n\n使用者問題：/, '')
          : m.content
      }))
    scrollToBottom()
  } catch {}
}

function formatHistoryDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ── Input / scroll ────────────────────────────────────────
const inputText  = ref('')
const messagesEl = ref(null)

let abortController = null
let agentPollActive = false

function _tabConvId() { return chatStore.agentTabConvIds[activeScope.value] }
function _setTabConvId(id) { chatStore.agentTabConvIds[activeScope.value] = id }

// ── Panel helpers ─────────────────────────────────────────
function toggle() {
  const willOpen = !props.modelValue
  emit('update:modelValue', willOpen)
  if (willOpen) chatStore.clearNewMessage()
}
function close()  { emit('update:modelValue', false) }

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

// ── Page Context ─────────────────────────────────────────
async function buildPageContext() {
  const page = route.path.replace(/^\//, '') || 'chat'
  try {
    switch (page) {
      case 'docs': {
        const [countRes, kbs, processingDocs, errorDocs] = await Promise.all([
          docsApi.count(),
          kbApi.list(),
          docsApi.list({ status: 'processing', limit: 10 }),
          docsApi.list({ status: 'error', limit: 10 }),
        ])
        const total = countRes?.total ?? 0
        const kbList = Array.isArray(kbs) ? kbs : []
        const kbSummary = kbList.map(k => `${k.name}(${k.doc_count ?? k.document_count ?? 0}篇)`).join('、') || '無'
        const pDocs = Array.isArray(processingDocs) ? processingDocs : (processingDocs?.items || processingDocs?.documents || [])
        const eDocs = Array.isArray(errorDocs) ? errorDocs : (errorDocs?.items || errorDocs?.documents || [])

        let context = `[頁面狀態] 文件總數：${total}\n知識庫：${kbSummary}\n`
        if (pDocs.length > 0) {
          context += `處理中文件（${pDocs.length} 篇）：\n`
          pDocs.forEach(d => { context += `  - ${d.title || d.filename || '未命名'}（已處理 ${d.chunk_count ?? 0} chunks）\n` })
        }
        if (eDocs.length > 0) {
          context += `處理失敗文件（${eDocs.length} 篇）：\n`
          eDocs.forEach(d => { context += `  - ${d.title || d.filename || '未命名'}（錯誤：${d.error_message || '未知錯誤'}）\n` })
        }
        return context.trimEnd()
      }
      case 'ontology': {
        const q = await ontologyApi.reviewQueue('pending')
        const total = Array.isArray(q) ? q.length : (q?.total ?? q?.items?.length ?? 0)
        return `[頁面狀態] 待審核實體：${total} 筆`
      }
      case 'chat':
        return `[頁面狀態] 目前在對話管理頁`
      default:
        return ''
    }
  } catch {
    return ''
  }
}

// ── Send ──────────────────────────────────────────────────
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || currentScopeState.value.streaming) return
  if (activeScope.value.startsWith('kb:') && !activeScopeKbId.value) return

  inputText.value = ''
  const tab = currentScopeState.value
  tab.messages.push({ role: 'user', content: text })
  scrollToBottom()

  if (activeScope.value === 'global') {
    await runGlobalAgent(text, tab)
  } else {
    const pageCtx = await buildPageContext()
    const finalQuery = pageCtx ? `${pageCtx}\n\n使用者問題：${text}` : text
    await runChat(finalQuery, tab)
  }
}

async function runChat(text, tab) {
  const aiMsg = { role: 'assistant', content: '', streaming: true }
  tab.messages.push(aiMsg)
  tab.streaming = true
  abortController = new AbortController()
  chatStore.abortController = abortController
  chatStore.streaming = true

  const agentType = activeScopeAgentType.value
  const kbScopeId = activeScopeKbId.value

  try {
    const resp = await chatStream(
      text, _tabConvId(), selectedModel.value || null, abortController.signal,
      [], kbScopeId, [], [], agentType, agentMode.value
    )
    if (!resp.ok) { aiMsg.content = '⚠️ 請求失敗'; aiMsg.streaming = false; return }

    const headerConvId = resp.headers.get('X-Conversation-Id')
    if (headerConvId && !_tabConvId()) {
      _setTabConvId(headerConvId)
      // 同步 ChatView sidebar
      chatStore.loadConversations()
      // 新對話建立後，令本 tab 的歷史快取失效
      const updated = { ...historyCache.value }
      delete updated[activeScope.value]
      historyCache.value = updated
    }

    const reader  = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const raw = part.slice(6).trim()
        if (raw === '[DONE]') { aiMsg.streaming = false; break }
        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'token') { aiMsg.content += evt.text; scrollToBottom() }
          else if (evt.type === 'error') aiMsg.content = '⚠️ ' + evt.text
        } catch {}
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') aiMsg.content += '\n\n_[已停止]_'
    else aiMsg.content = '⚠️ 錯誤：' + e.message
  } finally {
    aiMsg.streaming = false
    tab.streaming = false
    abortController = null
    chatStore.abortController = null
    chatStore.streaming = false
    // 元件不可見時發出通知
    if (!props.modelValue) {
      chatStore.markNewMessage()
      try {
        if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
          new Notification('AI 助理完成', {
            body: (aiMsg.content || '').slice(0, 60) + ((aiMsg.content || '').length > 60 ? '...' : '') || '已完成處理'
          })
        }
      } catch {}
    }
    await handlePageAction(aiMsg)
  }
}

// ── Page Action Handler ────────────────────────────────────
const ACTION_RE = /__action__:(\{[^\n]+\})/g

async function handlePageAction(aiMsg) {
  const matches = [...(aiMsg.content || '').matchAll(ACTION_RE)]
  if (!matches.length) return
  aiMsg.content = aiMsg.content.replace(ACTION_RE, '').trimEnd()
  if (!aiMsg.actionResults) aiMsg.actionResults = []
  for (const m of matches) {
    let action
    try { action = JSON.parse(m[1]) } catch { continue }
    const { type, ...params } = action
    let result = ''
    try {
      switch (type) {
        case 'create_kb': {
          const kb = await kbApi.create({ name: params.name, description: params.description || '' })
          result = `✅ 已建立知識庫「${kb.name}」`; break
        }
        case 'delete_doc': {
          await docsApi.delete(params.doc_id); result = `✅ 已刪除文件`; break
        }
        case 'search_docs': {
          try {
            const docs = await docsApi.aiSearch(params.query, null, params.top_k || 20)
            const header = `🔍 搜尋「${params.query}」：找到 ${docs.length} 篇文件`
            const body = docs.length
              ? docs.map(d => `- ID:${d.doc_id} 《${d.title || '未命名'}》 狀態:${d.status || '?'} 相關度:${d.score?.toFixed(3) ?? '?'}`).join('\n')
              : '（無符合文件）'
            result = `${header}\n${body}`
            const followUp = `以下是文件搜尋結果，請根據結果進行分析回覆（doc_id 可直接用於後續操作）：\n${header}\n${body}`
            const _tab = currentScopeState.value
            setTimeout(() => runChat(followUp, _tab), 200)
          } catch (e) {
            result = `❌ 搜尋失敗：${e.message}`
          }
          break
        }
        case 'list_all_docs': {
          try {
            const docs = await docsApi.list({ limit: 100 })
            const list = Array.isArray(docs) ? docs : []
            const kbApi_res = await kbApi.list()
            const kbs = Array.isArray(kbApi_res) ? kbApi_res : []
            const kbMap = Object.fromEntries(kbs.map(k => [k.id, k.name]))
            const header = `📋 共 ${list.length} 篇文件`
            const body = list.length
              ? list.map(d => `- ID:${d.doc_id} 《${d.title || '未命名'}》 狀態:${d.status} KB:${kbMap[d.knowledge_base_id] || d.knowledge_base_id || '未分類'}`).join('\n')
              : '（無文件）'
            result = `${header}\n${body}`
            const followUp = `以下是所有文件清單（doc_id 和 KB 資訊可直接用於後續操作）：\n${header}\n${body}`
            const _tab = currentScopeState.value
            setTimeout(() => runChat(followUp, _tab), 200)
          } catch (e) {
            result = `❌ 取得文件列表失敗：${e.message}`
          }
          break
        }
        case 'move_to_kb': {
          await docsApi.moveToKb(params.doc_id, params.kb_id); result = `✅ 已移入知識庫`; break
        }
        case 'batch_move_to_kb': {
          const docIds = Array.isArray(params.doc_ids) ? params.doc_ids : []
          let ok = 0, fail = 0
          for (const docId of docIds) {
            try {
              await docsApi.moveToKb(docId, params.kb_id)
              ok++
            } catch {
              fail++
            }
          }
          let kbName = params.kb_id
          try {
            const kbs = await kbApi.list()
            const found = (Array.isArray(kbs) ? kbs : []).find(k => k.id === params.kb_id)
            if (found) kbName = found.name
          } catch {}
          result = `✅ 已將 ${docIds.length} 篇文件移入《${kbName}》，成功 ${ok} 篇${fail > 0 ? `，失敗 ${fail} 篇` : ''}`
          window.dispatchEvent(new CustomEvent('ai-action', { detail: { type: 'reload_docs' } }))
          break
        }
        case 'list_kbs': {
          try {
            const kbs = await kbApi.list()
            const list = Array.isArray(kbs) ? kbs : []
            const header = `📂 現有知識庫：共 ${list.length} 個`
            const body = list.length
              ? list.map(k => `- ID:${k.id} 《${k.name}》${k.description ? ' — ' + k.description : ''}`).join('\n')
              : '（尚未建立任何知識庫）'
            result = `${header}\n${body}`
            const followUp = `以下是現有知識庫清單（kb_id 可直接用於 move_to_kb / batch_move_to_kb）：\n${header}\n${body}`
            const _tab = currentScopeState.value
            setTimeout(() => runChat(followUp, _tab), 200)
          } catch (e) {
            result = `❌ 取得知識庫失敗：${e.message}`
          }
          break
        }
        case 'edit_doc': {
          const updateBody = {}
          if (params.title) updateBody.title = params.title
          if (params.description !== undefined) updateBody.description = params.description
          await docsApi.updateMeta(params.doc_id, updateBody)
          result = `✅ 已更新文件 metadata`
          window.dispatchEvent(new CustomEvent('ai-action', { detail: { type: 'reload_docs' } }))
          break
        }
        case 'delete_conv': {
          await conversationsApi.delete(params.conv_id); result = `✅ 已刪除對話`; break
        }
        case 'search_convs': { result = `🔍 正在搜尋對話「${params.query}」`; break }
        case 'batch_approve_all': {
          const res = await ontologyApi.batchApprove({ all: true })
          result = `✅ 已批次核准 ${res.approved} 筆實體`; break
        }
        case 'batch_reject_all': {
          const res = await ontologyApi.batchReject({ all: true })
          result = `✅ 已批次拒絕 ${res.rejected} 筆實體`; break
        }
        case 'toggle_plugin': {
          await pluginsApi.toggle(params.plugin_id); result = `✅ 已切換插件狀態`; break
        }
        case 'add_model': {
          result = `ℹ️ 請至設定頁面手動新增模型「${params.name}」`; break
        }
        default: result = `⚠️ 未知操作：${type}`
      }
    } catch (e) {
      result = `❌ 操作失敗：${e.message || type}`
    }
    aiMsg.actionResults.push(result)
    window.dispatchEvent(new CustomEvent('ai-action', { detail: action }))
  }
}

async function runGlobalAgent(text, tab) {
  const aiMsg = { role: 'assistant', content: '', steps: [], streaming: true }
  tab.messages.push(aiMsg)
  tab.streaming = true
  agentPollActive = true
  try {
    const res = await agentApi.run(text, null)
    const taskId = res.task_id
    let attempts = 0
    const poll = async () => {
      if (!agentPollActive) return
      if (attempts >= 60) {
        aiMsg.content = '⚠️ Agent 任務超時'
        aiMsg.streaming = false; tab.streaming = false; return
      }
      attempts++
      try {
        const status = await agentApi.getTask(taskId)
        if (!agentPollActive) return
        aiMsg.steps = status.steps || []
        scrollToBottom()
        if (status.status === 'completed') {
          aiMsg.content = status.result || '✅ 任務完成'
          aiMsg.streaming = false; tab.streaming = false
        } else if (status.status === 'failed') {
          aiMsg.content = '⚠️ 任務失敗：' + (status.error || '未知錯誤')
          aiMsg.streaming = false; tab.streaming = false
        } else {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (!agentPollActive) return
        aiMsg.content = '⚠️ 查詢失敗：' + e.message
        aiMsg.streaming = false; tab.streaming = false
      }
    }
    setTimeout(poll, 1000)
  } catch (e) {
    aiMsg.content = '⚠️ 錯誤：' + e.message
    aiMsg.streaming = false; tab.streaming = false
  }
}

function stopStreaming() {
  if (abortController) { abortController.abort(); abortController = null }
  chatStore.stopStreaming()
  agentPollActive = false
  currentScopeState.value.streaming = false
}

// ── Plus menu handler ─────────────────────────────────────
function handlePlusCommand(cmd) {
  if (cmd === 'upload') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf,.docx,.txt,.md,.xlsx,.xls,.csv'
    input.onchange = (e) => {
      const file = e.target.files[0]
      if (file) window.dispatchEvent(new CustomEvent('agent-upload-file', { detail: { file } }))
    }
    input.click()
  } else if (cmd === 'import_excel') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e) => {
      const file = e.target.files[0]
      if (file) window.dispatchEvent(new CustomEvent('agent-import-excel', { detail: { file } }))
    }
    input.click()
  }
}

// ── Lifecycle ─────────────────────────────────────────────
async function _refreshKbList() {
  try {
    knowledgeBases.value = await kbApi.list()
    // 若當前 scope 是已被刪除的 KB，fallback 到 global
    if (activeScope.value.startsWith('kb:')) {
      const id = activeScope.value.slice(3)
      const exists = knowledgeBases.value.some(k => String(k.id) === String(id))
      if (!exists) activeScope.value = 'global'
    }
  } catch {}
}

function _onAgentAction(e) {
  const t = e?.detail?.type
  if (t === 'create_kb' || t === 'delete_kb' || t === 'reload_kbs') {
    _refreshKbList()
  }
}

onMounted(async () => {
  await _refreshKbList()
  window.addEventListener('ai-action', _onAgentAction)
  try {
    const resp = await fetch('/api/chat/models', {
      headers: { 'Authorization': `Bearer ${(await import('../stores/auth.js')).useAuthStore().token}` }
    })
    if (resp.ok) {
      const data = await resp.json()
      localModels.value = data.models || []
    }
  } catch {}
  try {
    const wiki = await wikiApi.list()
    cloudModels.value = (wiki || []).filter(
      m => (m.model_type || 'chat') === 'chat' && m.provider && m.provider !== 'ollama'
    )
  } catch {}
  if (!selectedModel.value && availableModels.value.length) {
    selectedModel.value = availableModels.value[0]
  }
  _loadFabPos()
  window.addEventListener('resize', _onResize)
})

onUnmounted(() => {
  // 不中斷串流（串流狀態在 chatStore，不跟元件生命週期綁定）
  window.removeEventListener('resize', _onResize)
  window.removeEventListener('ai-action', _onAgentAction)
})

// ── FAB 拖曳 ─────────────────────────────────────────────
const FAB_SIZE          = 44
const FAB_MARGIN        = 12   // 距視窗邊緣最小距離（左/上/右）
const FAB_BOTTOM_MARGIN = 72   // 底部額外留空（避免蓋住底部工具列）
const FAB_KEY           = 'agent-fab-position'

const fabPos = ref({ x: 0, y: 0 })  // left / top (px)
let _drag = null  // { startX, startY, origX, origY, moved }

function _clamp(val, min, max) { return Math.max(min, Math.min(max, val)) }

function _fabFixedX() { return window.innerWidth - FAB_SIZE - FAB_MARGIN }

function _loadFabPos() {
  console.log('[FAB] _loadFabPos called, innerWidth:', window.innerWidth, 'innerHeight:', window.innerHeight)
  try {
    const saved = JSON.parse(localStorage.getItem(FAB_KEY))
    if (saved && typeof saved.y === 'number') {
      fabPos.value = {
        x: _fabFixedX(),
        y: _clamp(saved.y, FAB_MARGIN, window.innerHeight - FAB_SIZE - FAB_BOTTOM_MARGIN),
      }
      console.log('[FAB] fabPos set (from localStorage) to:', fabPos.value)
      return
    }
  } catch {}
  // 預設右下角
  fabPos.value = {
    x: _fabFixedX(),
    y: window.innerHeight - FAB_SIZE - FAB_BOTTOM_MARGIN,
  }
  console.log('[FAB] fabPos set (default) to:', fabPos.value)
}

function _onResize() {
  fabPos.value = {
    x: _fabFixedX(),
    y: _clamp(fabPos.value.y, FAB_MARGIN, window.innerHeight - FAB_SIZE - FAB_BOTTOM_MARGIN),
  }
}

function onFabMousedown(e) {
  if (e.button !== 0) return
  e.preventDefault()
  _drag = { startX: e.clientX, startY: e.clientY, origX: fabPos.value.x, origY: fabPos.value.y, moved: false }
  document.addEventListener('mousemove', onFabMousemove)
  document.addEventListener('mouseup',   onFabMouseup)
}

function onFabMousemove(e) {
  if (!_drag) return
  const dy = e.clientY - _drag.startY
  if (!_drag.moved && Math.abs(dy) < 5) return
  _drag.moved = true
  fabPos.value = {
    x: _fabFixedX(),
    y: _clamp(_drag.origY + dy, FAB_MARGIN, window.innerHeight - FAB_SIZE - FAB_BOTTOM_MARGIN),
  }
}

function onFabMouseup() {
  document.removeEventListener('mousemove', onFabMousemove)
  document.removeEventListener('mouseup',   onFabMouseup)
  if (!_drag) return
  if (_drag.moved) {
    // 儲存位置
    try { localStorage.setItem(FAB_KEY, JSON.stringify(fabPos.value)) } catch {}
  } else {
    toggle()  // 點擊 → 開啟面板
  }
  _drag = null
}
</script>

<template>
  <!-- FAB 按鈕（面板關閉時顯示） -->
  <button
    v-show="!modelValue && !isHiddenPage"
    class="agent-fab"
    title="AI Agent"
    :style="{ left: fabPos.x + 'px', top: fabPos.y + 'px' }"
    @mousedown="onFabMousedown"
  >
    <img src="/logo.svg" alt="AI" class="fab-logo" onerror="this.style.display='none'" />
    <span v-if="chatStore.hasNewMessage" class="fab-badge"></span>
  </button>

  <!-- 面板 -->
  <Transition name="panel-slide">
    <div v-if="modelValue && !isHiddenPage" class="agent-panel">

      <!-- Title bar（配合 TitleBar 38px）-->
      <div class="panel-title-bar">
        <span class="panel-title-text">AI 助理</span>
        <button class="panel-title-close" title="關閉" @click="$emit('update:modelValue', false)"><X :size="16" :stroke-width="1.5" /></button>
      </div>

      <!-- Scope segment + 關閉按鈕 -->
      <div class="panel-tab-bar">
        <div class="scope-segment">
          <button
            class="scope-seg-btn"
            :class="{ active: activeScope === 'global' }"
            @click="selectGlobalScope"
          ><Globe :size="13" :stroke-width="1.5" />全域</button>

          <el-popover
            v-model:visible="pagePopoverOpen"
            placement="bottom"
            :width="180"
            trigger="click"
            popper-class="scope-popover"
          >
            <template #reference>
              <button
                class="scope-seg-btn"
                :class="{ active: activeScope.startsWith('page:') }"
              ><Monitor :size="13" :stroke-width="1.5" />頁面<ChevronDown :size="11" :stroke-width="2" /></button>
            </template>
            <div class="scope-popover-list">
              <div
                v-for="opt in pageOptions"
                :key="opt.path"
                class="scope-popover-item"
                :class="{ active: activeScope === 'page:' + opt.path }"
                @click="selectPageScope(opt.path)"
              >{{ opt.name }}</div>
            </div>
          </el-popover>

          <el-popover
            v-model:visible="kbPopoverOpen"
            placement="bottom"
            :width="200"
            trigger="click"
            popper-class="scope-popover"
          >
            <template #reference>
              <button
                class="scope-seg-btn"
                :class="{ active: activeScope.startsWith('kb:') }"
              ><BookOpen :size="13" :stroke-width="1.5" />知識庫<ChevronDown :size="11" :stroke-width="2" /></button>
            </template>
            <div class="scope-popover-list">
              <div v-if="!knowledgeBases.length" class="scope-popover-empty">尚未建立知識庫</div>
              <div
                v-for="kb in knowledgeBases"
                :key="kb.id"
                class="scope-popover-item"
                :class="{ active: activeScope === 'kb:' + kb.id }"
                @click="selectKbScope(kb.id)"
              >{{ kb.name }}</div>
            </div>
          </el-popover>
        </div>
      </div>

      <!-- Subtitle -->
      <div class="panel-subtitle">
        <div class="panel-subtitle-content">
          <span>當前：{{ activeScopeLabel }}</span>
        </div>
        <button
          class="history-toggle-btn"
          :class="{ active: historyOpen }"
          title="歷史對話"
          @click="toggleHistory"
        >
          <Clock :size="13" :stroke-width="1.5" />
          <ChevronDown :size="10" :stroke-width="2" class="hist-chevron" :class="{ open: historyOpen }" />
        </button>
      </div>

      <!-- History panel -->
      <div v-if="historyOpen" class="panel-history">
        <div v-if="historyLoading" class="history-loading">載入中…</div>
        <template v-else-if="historyCache[activeScope] && historyCache[activeScope].length">
          <div
            v-for="conv in historyCache[activeScope]"
            :key="conv.id"
            class="history-item"
            :class="{ active: currentScopeState.convId === conv.id }"
            @click="loadConversation(conv)"
          >
            <MessageCircle :size="11" :stroke-width="1.5" class="history-icon" />
            <span class="history-title">{{ conv.title || '未命名對話' }}</span>
            <span class="history-date">{{ formatHistoryDate(conv.updated_at || conv.created_at) }}</span>
          </div>
        </template>
        <div v-else class="history-empty">無歷史對話</div>
      </div>

      <!-- Messages -->
      <div class="panel-messages" ref="messagesEl" @click="onMsgAreaClick">
        <div v-if="currentScopeState.messages.length === 0" class="panel-empty">
          <div class="empty-icon">
            <Monitor v-if="activeScope.startsWith('page:')" :size="52" :stroke-width="1" />
            <Globe v-else-if="activeScope === 'global'" :size="52" :stroke-width="1" />
            <BookOpen v-else :size="52" :stroke-width="1" />
          </div>
          <div class="empty-title">
            <template v-if="activeScope.startsWith('page:')">{{ activeScopeLabel }} 助理</template>
            <template v-else-if="activeScope === 'global'">全域 Agent</template>
            <template v-else>{{ activeScopeLabel }} 知識庫問答</template>
          </div>
          <div class="empty-hint">
            <template v-if="activeScope.startsWith('page:')">詢問關於「{{ activeScopeLabel }}」的問題，或直接下達操作指令</template>
            <template v-else-if="activeScope === 'global'">下達指令，Agent 自動執行操作</template>
            <template v-else>詢問《{{ activeScopeLabel }}》相關問題</template>
          </div>
        </div>

        <div v-for="(msg, idx) in currentScopeState.messages" :key="idx" class="message-wrap">
          <!-- User bubble -->
          <div v-if="msg.role === 'user'" class="message-row user-row">
            <div class="msg-actions user-actions">
              <button @click="copyText(msg.content)" title="複製"><Copy :size="14" :stroke-width="1.5" /></button>
            </div>
            <div class="message-bubble user-bubble">{{ msg.content }}</div>
          </div>

          <!-- AI bubble -->
          <div v-else class="message-row ai-row">
            <div class="message-bubble ai-bubble">
              <div v-if="!msg.content && msg.streaming" class="thinking">
                <span></span><span></span><span></span>
              </div>
              <div v-if="msg.steps && msg.steps.length && msg.streaming" class="panel-steps">
                <div v-for="(step, si) in msg.steps" :key="si" class="panel-step">
                  <span>🔧</span>
                  <span class="step-tool">{{ step.tool }}</span>
                  <span v-if="step.input" class="step-input">{{ String(step.input).slice(0, 40) }}</span>
                </div>
              </div>
              <div v-if="msg.content" class="markdown-body" v-html="renderMd(msg.content)"></div>
              <span v-if="msg.streaming && msg.content" class="cursor">▌</span>
              <template v-if="msg.actionResults && msg.actionResults.length">
                <div v-for="(r, ri) in msg.actionResults" :key="ri" class="panel-action-result">{{ r }}</div>
              </template>
            </div>
            <div v-if="!msg.streaming && msg.content" class="msg-actions ai-actions">
              <button @click="copyText(msg.content)" title="複製"><Copy :size="14" :stroke-width="1.5" /></button>
            </div>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="panel-input-area">
        <div class="panel-input-card">
          <el-input
            v-model="inputText"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="輸入問題… Enter 送出"
            class="panel-textarea"
            :disabled="currentScopeState.streaming"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <div class="panel-input-footer">
            <div class="panel-footer-left">
              <!-- [+] 選單 -->
              <el-dropdown trigger="click" @command="handlePlusCommand" :disabled="currentScopeState.streaming">
                <button class="panel-plus-btn" :disabled="currentScopeState.streaming" title="附加">
                  <Plus :size="15" :stroke-width="1.8" />
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="upload">
                      <Paperclip :size="14" :stroke-width="1.5" style="margin-right:6px;vertical-align:middle" />
                      上傳文件
                    </el-dropdown-item>
                    <el-dropdown-item command="import_excel">
                      <FileSpreadsheet :size="14" :stroke-width="1.5" style="margin-right:6px;vertical-align:middle" />
                      匯入連結（Excel）
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <!-- [Agent▾] 模式選擇 -->
              <el-dropdown trigger="click" @command="(cmd) => agentMode = cmd" :disabled="currentScopeState.streaming">
                <button class="panel-mode-btn">
                  <component :is="MODE_ICONS[agentMode]" :size="14" :stroke-width="1.5" style="margin-right:4px;vertical-align:middle" />
                  {{ MODE_LABELS[agentMode] }} ▾
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="agent">
                      <Bot :size="14" :stroke-width="1.5" style="margin-right:6px;vertical-align:middle" />
                      Agent — 執行操作模式
                    </el-dropdown-item>
                    <el-dropdown-item command="ask">
                      <MessageCircle :size="14" :stroke-width="1.5" style="margin-right:6px;vertical-align:middle" />
                      Ask — 純問答模式
                    </el-dropdown-item>
                    <el-dropdown-item command="plan">
                      <ListChecks :size="14" :stroke-width="1.5" style="margin-right:6px;vertical-align:middle" />
                      Plan — 規劃後確認模式
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div class="panel-footer-right">
              <!-- [模型▾] 選擇 -->
              <el-popover v-model:visible="modelPopoverVisible" placement="top-end" :width="300" :disabled="currentScopeState.streaming">
                <template #reference>
                  <button class="model-trigger-btn" :disabled="currentScopeState.streaming" @click="modelPopoverVisible = !modelPopoverVisible">
                    <span class="model-trigger-name">{{ selectedModel || '選擇模型' }}</span>
                    <span class="model-trigger-arrow">▾</span>
                  </button>
                </template>
                <div class="model-popover-content">
                  <div class="model-section" v-if="localModels.length">
                    <div class="model-section-title">本地模型</div>
                    <div v-for="m in localModels" :key="m" class="model-option" @click="selectedModel = m; modelPopoverVisible = false">
                      <span class="model-option-name">{{ m }}</span>
                      <Check v-if="selectedModel === m" :size="14" :stroke-width="2" class="model-check" />
                    </div>
                  </div>
                  <div class="model-section" v-if="cloudModels.length">
                    <div class="model-section-title">雲端模型</div>
                    <div v-for="m in cloudModels" :key="m.name" class="model-option" @click="selectedModel = m.name; modelPopoverVisible = false">
                      <div>
                        <div class="model-option-name">{{ m.name }}</div>
                        <div class="model-option-desc">{{ m.developer || m.provider }}</div>
                      </div>
                      <Check v-if="selectedModel === m.name" :size="14" :stroke-width="2" class="model-check" />
                    </div>
                  </div>
                  <div v-if="!localModels.length && !cloudModels.length" style="padding:12px;font-size:13px;color:#909399;text-align:center">
                    請先在設定頁新增模型
                  </div>
                </div>
              </el-popover>
              <!-- 停止 / 發送 -->
              <button
                v-if="currentScopeState.streaming"
                class="panel-stop-btn"
                @click="stopStreaming"
              ><Square :size="12" :stroke-width="1.5" /></button>
              <button
                v-else
                class="panel-send-btn"
                :disabled="!inputText.trim() || (activeScope.startsWith('kb:') && !activeScopeKbId)"
                @click="sendMessage"
              ><ArrowUp :size="14" :stroke-width="2" /></button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </Transition>
</template>

<style scoped>
/* ── FAB ──────────────────────────────────────────────────── */
.agent-fab {
  position: fixed;
  /* left / top 由 JS fabPos 控制，不設預設值 */
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: #fff;
  cursor: grab;
  z-index: 1001;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
  transition: box-shadow 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  user-select: none;
  -webkit-user-select: none;
}
.agent-fab:active { cursor: grabbing; }
.agent-fab:hover { box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25); transform: scale(1.06); }
.fab-logo { width: 28px; height: 28px; object-fit: contain; border-radius: 50%; pointer-events: none; }
.fab-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  border: 2px solid #fff;
  pointer-events: none;
}

/* ── Panel ────────────────────────────────────────────────── */
.agent-panel {
  position: fixed;
  top: var(--titlebar-h, 0px);
  right: 0;
  width: 380px;
  height: calc(100vh - var(--titlebar-h, 0px));
  background: #fff;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.12);
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

/* ── Slide transition ─────────────────────────────────────── */
.panel-slide-enter-active,
.panel-slide-leave-active { transition: transform 0.25s ease; }
.panel-slide-enter-from,
.panel-slide-leave-to  { transform: translateX(100%); }

/* ── Title bar ─────────────────────────────────────────────── */
.panel-title-bar {
  height: 38px;
  padding: 0 14px;
  border-bottom: 1px solid #e8edf2;
  flex-shrink: 0;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.panel-title-text {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}
.panel-title-close {
  border: none;
  background: none;
  font-size: 18px;
  line-height: 1;
  color: #94a3b8;
  cursor: pointer;
  padding: 0 2px;
  transition: color 0.15s;
}
.panel-title-close:hover { color: #ef4444; }

/* ── Tab bar ────────────────────────────────────────────────── */
.panel-tab-bar {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
  gap: 6px;
}
.scope-segment {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: stretch;
  background: #f0f2f5;
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
}
.scope-seg-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: none;
  background: transparent;
  border-radius: 6px;
  padding: 6px 4px;
  font-size: 12px;
  color: #555;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.scope-seg-btn:hover { color: #333; }
.scope-seg-btn.active {
  background: #fff;
  color: #409eff;
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.scope-popover-list {
  display: flex;
  flex-direction: column;
  max-height: 280px;
  overflow-y: auto;
}
.scope-popover-item {
  padding: 8px 12px;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}
.scope-popover-item:hover { background: #f5f7fa; }
.scope-popover-item.active { background: #ecf5ff; color: #409eff; font-weight: 600; }
.scope-popover-empty {
  padding: 12px;
  color: #999;
  font-size: 12px;
  text-align: center;
}

/* ── Subtitle ─────────────────────────────────────────────── */
.panel-subtitle {
  padding: 8px 12px;
  font-size: 12px;
  color: #888;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: space-between;
}
.panel-subtitle-content { flex: 1; min-width: 0; display: flex; align-items: center; }
.history-toggle-btn {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 2px;
  border: none; background: none; cursor: pointer;
  color: #64748b; padding: 3px 5px; border-radius: 5px;
  transition: background 0.15s, color 0.15s;
}
.history-toggle-btn:hover { background: #f1f5f9; color: #334155; }
.history-toggle-btn.active { color: #2563eb; background: #eff6ff; }
.hist-chevron { transition: transform 0.2s; }
.hist-chevron.open { transform: rotate(0deg); }
/* ── History panel ─────────────────────────────────────────── */
.panel-history {
  max-height: 190px;
  overflow-y: auto;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
  background: #f8fafc;
}
.history-loading, .history-empty {
  padding: 10px 14px; font-size: 12px; color: #94a3b8; text-align: center;
}
.history-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  cursor: pointer; font-size: 12px; color: #475569;
  transition: background 0.15s;
}
.history-item:hover { background: #eff6ff; color: #1d4ed8; }
.history-item.active { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
.history-icon { flex-shrink: 0; color: #94a3b8; }
.history-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-date { flex-shrink: 0; font-size: 11px; color: #94a3b8; }

/* ── Messages ─────────────────────────────────────────────── */
.panel-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.panel-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #94a3b8;
  padding: 32px 20px;
  gap: 10px;
}
.empty-icon { color: #cbd5e1; display: flex; align-items: center; justify-content: center; }
.empty-title { font-size: 17px; font-weight: 600; color: #475569; letter-spacing: -0.01em; }
.empty-hint { font-size: 12px; line-height: 1.7; color: #94a3b8; max-width: 200px; }

/* ── Message bubbles (ChatView style) ─────────────────────── */
.message-wrap { display: flex; flex-direction: column; gap: 4px; }
.message-row { display: flex; align-items: flex-start; gap: 6px; }
.user-row { justify-content: flex-end; }
.ai-row { justify-content: flex-start; }
.msg-actions {
  display: flex; flex-direction: column; gap: 4px;
  opacity: 0; transition: opacity 0.15s; flex-shrink: 0; margin-top: 4px;
}
.message-wrap:hover .msg-actions { opacity: 1; }
.msg-actions button {
  border: none; background: transparent; font-size: 14px;
  cursor: pointer; padding: 3px 5px; border-radius: 5px;
  transition: background 0.1s; color: #64748b;
}
.msg-actions button:hover { background: #f1f5f9; color: #1e293b; }
.user-actions { align-self: center; }
.ai-actions { align-self: flex-start; margin-top: 2px; }
.message-bubble {
  max-width: 88%; padding: 10px 14px; border-radius: 12px;
  font-size: 13px; line-height: 1.7; word-break: break-word;
}
.user-bubble { background: #4a90d9; color: #fff; border-bottom-right-radius: 3px; white-space: pre-wrap; }
.ai-bubble { background: #f8fafc; border: 1px solid #e8edf3; color: #1e293b; border-bottom-left-radius: 3px; min-width: 100px; }

/* ── Agent steps ──────────────────────────────────────────── */
.panel-steps { margin-bottom: 6px; font-size: 12px; color: #666; }
.panel-step  { display: flex; align-items: center; gap: 4px; padding: 2px 0; }
.step-tool   { font-weight: 600; }
.step-input  { color: #999; font-size: 11px; }

/* ── Thinking dots ────────────────────────────────────────── */
.thinking { display: flex; gap: 5px; padding: 4px 0; align-items: center; }
.thinking span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  animation: ap-bounce 1.2s infinite ease-in-out;
}
.thinking span:nth-child(2) { animation-delay: 0.2s; }
.thinking span:nth-child(3) { animation-delay: 0.4s; }
@keyframes ap-bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

.cursor { display: inline-block; opacity: 0.7; animation: ap-cur-blink 1s infinite; }
@keyframes ap-cur-blink { 0%,100%{opacity:0.7} 50%{opacity:0} }

.panel-action-result { margin-top: 6px; padding: 5px 10px; background: #f0faf0; border: 1px solid #b7ddb7; border-radius: 6px; font-size: 12px; color: #2d6a2d; }

/* ── Markdown body ────────────────────────────────────────── */
:deep(.markdown-body) { font-size: 13px; line-height: 1.75; color: #1e293b; }
:deep(.markdown-body h1),:deep(.markdown-body h2),:deep(.markdown-body h3) { font-weight: 600; margin: 0.8em 0 0.3em; color: #0f172a; }
:deep(.markdown-body h1) { font-size: 1.3em; }
:deep(.markdown-body h2) { font-size: 1.15em; }
:deep(.markdown-body h3) { font-size: 1.02em; }
:deep(.markdown-body p) { margin: 0.4em 0; }
:deep(.markdown-body ul),:deep(.markdown-body ol) { padding-left: 1.4em; margin: 0.3em 0; }
:deep(.markdown-body li) { margin: 0.15em 0; }
:deep(.markdown-body blockquote) {
  border-left: 3px solid #94a3b8; padding: 4px 10px;
  color: #64748b; margin: 6px 0; background: #f1f5f9;
  border-radius: 0 6px 6px 0;
}
:deep(.markdown-body strong) { font-weight: 600; }
:deep(.markdown-body em) { font-style: italic; }
:deep(.markdown-body a) { color: #4a90d9; text-decoration: none; }
:deep(.markdown-body a:hover) { text-decoration: underline; }
:deep(.markdown-body table) { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px; }
:deep(.markdown-body th),:deep(.markdown-body td) { border: 1px solid #e2e8f0; padding: 5px 10px; }
:deep(.markdown-body th) { background: #f1f5f9; font-weight: 600; }
:deep(.markdown-body code:not(.hljs)) {
  background: #f1f5f9; padding: 1px 5px; border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.9em; color: #e53e3e;
}
:deep(.markdown-body hr) { border: none; border-top: 1px solid #e2e8f0; margin: 10px 0; }

/* ── Code blocks ──────────────────────────────────────────── */
:deep(.code-block) { margin: 6px 0; border-radius: 8px; overflow: hidden; border: 1px solid #2d3748; font-size: 12px; }
:deep(.code-header) { display: flex; align-items: center; justify-content: space-between; background: #2d3748; padding: 4px 10px; }
:deep(.code-lang) { font-size: 10px; color: #a0aec0; font-family: monospace; text-transform: uppercase; }
:deep(.code-copy-btn) {
  background: transparent; border: 1px solid #4a5568;
  color: #a0aec0; font-size: 10px; padding: 2px 7px;
  border-radius: 4px; cursor: pointer; transition: all 0.15s;
}
:deep(.code-copy-btn:hover) { background: #4a5568; color: #fff; }
:deep(.code-block pre) { margin: 0; padding: 12px 14px; overflow-x: auto; }
:deep(.code-block code) { font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 12px; line-height: 1.55; }

/* ── highlight.js theme ───────────────────────────────────── */
:deep(.hljs) { background: #1c2433; color: #e6edf3; }
:deep(.hljs-comment),:deep(.hljs-quote) { color: #8b949e; font-style: italic; }
:deep(.hljs-keyword),:deep(.hljs-selector-tag),:deep(.hljs-literal) { color: #ff7b72; }
:deep(.hljs-string),:deep(.hljs-doctag) { color: #a5d6ff; }
:deep(.hljs-number) { color: #79c0ff; }
:deep(.hljs-function),:deep(.hljs-title) { color: #d2a8ff; }
:deep(.hljs-built_in),:deep(.hljs-type) { color: #ffa657; }
:deep(.hljs-attr),:deep(.hljs-attribute) { color: #79c0ff; }
:deep(.hljs-tag) { color: #7ee787; }
:deep(.hljs-variable),:deep(.hljs-template-variable) { color: #ffa657; }
:deep(.hljs-regexp),:deep(.hljs-link) { color: #a5d6ff; }

/* ── Input ────────────────────────────────────────────────── */
.panel-input-area {
  padding: 8px 12px 14px;
  flex-shrink: 0;
}
.panel-input-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 12px 14px 10px;
  position: relative;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.panel-input-card:focus-within { box-shadow: 0 0 0 3px rgba(37,99,235,0.1); border-color: #93c5fd; }
:deep(.panel-textarea .el-textarea__inner) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0;
  font-size: 13px;
  resize: none;
  color: #1e293b;
  min-height: unset;
}
.panel-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e2e8f0;
}
.panel-footer-left { display: flex; align-items: center; gap: 4px; }
.panel-footer-right { display: flex; align-items: center; gap: 4px; }
.panel-input-hint { font-size: 11px; color: #94a3b8; }
.panel-plus-btn {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #64748b;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, border-color 0.15s;
}
.panel-plus-btn:hover:not(:disabled) { background: #f1f5f9; border-color: #94a3b8; }
.panel-plus-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.panel-mode-btn {
  height: 26px; padding: 0 10px;
  border-radius: 13px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
  display: flex; align-items: center; gap: 2px;
  white-space: nowrap;
  transition: background 0.15s;
}
.panel-mode-btn:hover { background: #f1f5f9; }
.model-trigger-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 0 10px; height: 32px;
  background: #f5f7fa; border: 1px solid #dcdfe6; border-radius: 6px;
  font-size: 12px; color: #606266; max-width: 160px; cursor: pointer;
}
.model-trigger-btn:hover:not(:disabled) { border-color: #409eff; color: #409eff; }
.model-trigger-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.model-trigger-arrow { flex-shrink: 0; font-size: 10px; }
.model-popover-content { padding: 4px 0; }
.model-section { margin-bottom: 4px; }
.model-section:last-child { margin-bottom: 0; }
.model-section-title {
  font-size: 11px; font-weight: 600; color: #909399;
  padding: 6px 12px 4px; text-transform: uppercase; letter-spacing: 0.05em;
}
.model-option {
  display: flex; align-items: center; justify-content: space-between;
  padding: 7px 12px; cursor: pointer; border-radius: 4px; transition: background 0.1s;
}
.model-option:hover { background: #f5f7fa; }
.model-option-name { font-weight: 600; font-size: 13px; color: #303133; }
.model-option-desc { font-size: 11px; color: #909399; margin-top: 1px; }
.model-check { color: #409eff; flex-shrink: 0; margin-left: 8px; }
.panel-send-btn,
.panel-stop-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.panel-send-btn { background: #c0522a; color: #fff; }
.panel-send-btn:hover:not(:disabled) { background: #a0441f; }
.panel-send-btn:disabled { background: #d8b4a0; cursor: not-allowed; }
.panel-stop-btn { background: #fef2f2; border: 1px solid #fca5a5; color: #dc2626; }
.panel-stop-btn:hover { background: #fee2e2; }
</style>
