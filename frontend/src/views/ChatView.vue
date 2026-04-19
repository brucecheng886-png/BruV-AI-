<template>
  <div class="chat-root">

    <!-- ── Sidebar ─────────────────────────────────────────── -->
    <aside class="chat-sidebar">
      <div class="sidebar-top">
        <el-button type="primary" class="new-conv-btn" @click="newConversation">+ 新對話</el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId === conv.id }"
          @click="selectConversation(conv)"
        >
          <el-input
            v-if="renamingId === conv.id"
            v-model="renameTitle"
            size="small"
            class="rename-input"
            @blur="commitRename(conv)"
            @keydown.enter.prevent="commitRename(conv)"
            @keydown.esc="cancelRename"
            @click.stop
          />
          <div v-else class="conv-item-body" @dblclick.stop="startRename(conv)" title="雙擊重命名">
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-date">{{ conv.created_at?.slice(0,10) }}</div>
          </div>
          <button class="conv-delete-btn" @click.stop="deleteConversation(conv.id)" title="刪除">✕</button>
        </div>
      </div>
    </aside>

    <!-- ── Main ──────────────────────────────────────────────── -->
    <div class="chat-main">

      <!-- Home state -->
      <div v-if="messages.length === 0" class="chat-home">
        <div class="home-greeting">
          <img src="/logo.svg" alt="logo" class="home-icon" onerror="this.style.display='none'" />
          <span class="home-title">有什麼需要幫忙的？</span>
        </div>

        <div class="home-input-wrap">
          <div class="input-box-card">
            <div v-if="attachedDocs.length" class="attached-docs">
              <el-tag v-for="doc in attachedDocs" :key="doc.id" closable size="small" type="info" @close="removeDoc(doc.id)">
                📄 {{ doc.filename }}
              </el-tag>
            </div>
            <div v-if="slashMenu.show" class="cmd-menu">
              <div v-for="cmd in slashMenu.filtered" :key="cmd.name" class="cmd-item" @mousedown.prevent="applySlash(cmd)">
                <span class="cmd-icon">{{ cmd.icon }}</span>
                <span class="cmd-name">{{ cmd.name }}</span>
                <span class="cmd-desc">{{ cmd.desc }}</span>
              </div>
            </div>
            <div v-if="mentionMenu.show" class="cmd-menu">
              <div v-for="doc in mentionMenu.docs" :key="doc.id" class="cmd-item" @mousedown.prevent="applyMention(doc)">
                <span class="cmd-icon">📄</span>
                <span class="cmd-name">{{ doc.filename }}</span>
              </div>
            </div>
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="輸入問題… （/ 命令，@ 引用文件）"
              class="home-textarea"
              @keydown.enter.exact.prevent="sendMessage"
              @input="onInput"
              :disabled="streaming"
            />
            <div class="input-footer">
              <div class="footer-left">
                <el-radio-group v-model="chatMode" size="small" :disabled="streaming">
                  <el-radio-button value="chat">💬 對話</el-radio-button>
                  <el-radio-button value="agent">🤖 Agent</el-radio-button>
                </el-radio-group>
                <span class="input-hint">Enter 送出 · Shift+Enter 換行</span>
              </div>
              <div class="footer-right">
                <el-select v-model="selectedModel" size="small" class="model-select" :disabled="streaming" placeholder="選擇模型" :title="selectedModel">
                  <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
                </el-select>
                <el-button v-if="streaming" type="danger" size="small" @click="stopStreaming">■ 停止</el-button>
                <el-button v-else type="primary" size="small" :disabled="!inputText.trim()" @click="sendMessage">發送</el-button>
              </div>
            </div>
          </div>
        </div>

        <div class="quick-prompts">
          <button v-for="p in quickPrompts" :key="p.label" class="prompt-chip" @click="usePrompt(p.text)">
            <span class="chip-icon">{{ p.icon }}</span>
            <span>{{ p.label }}</span>
          </button>
        </div>
      </div>

      <!-- Active state: messages -->
      <template v-else>
        <div class="messages-area" ref="messagesEl" @scroll="onScroll" @click="onMsgAreaClick">
          <div v-for="(msg, idx) in messages" :key="idx" class="message-wrap">

            <!-- User bubble -->
            <div v-if="msg.role === 'user'" class="message-row user-row">
              <div class="msg-actions user-actions">
                <button @click="copyText(msg.content)" title="複製">📋</button>
              </div>
              <div class="message-bubble user-bubble">{{ msg.content }}</div>
            </div>

            <!-- AI bubble -->
            <div v-else class="message-row ai-row">
              <div class="message-bubble ai-bubble">
                <div v-if="!msg.content && msg.streaming" class="thinking">
                  <span></span><span></span><span></span>
                </div>
                <div v-if="msg.steps && msg.steps.length && msg.streaming" class="agent-progress">
                  <div v-for="(step, si) in msg.steps" :key="si" class="agent-step">
                    <span class="step-icon">🔧</span>
                    <span class="step-tool">{{ step.tool }}</span>
                    <span v-if="step.input" class="step-input">{{ truncate(step.input) }}</span>
                  </div>
                </div>
                <div v-if="msg.content" class="markdown-body" v-html="renderMd(msg.content)"></div>
                <span v-if="msg.streaming && msg.content" class="cursor">▌</span>
              </div>
              <div v-if="!msg.streaming" class="msg-actions ai-actions">
                <button @click="copyText(msg.content)" title="複製">📋</button>
                <button @click="retryFrom(idx)" title="重試">🔄</button>
                <button
                  v-if="msg.id"
                  @click="saveToKb(msg)"
                  :title="savedMsgIds.has(msg.id) ? '已儲存至知識庫' : '存入知識庫'"
                  :style="{ color: savedMsgIds.has(msg.id) ? '#67c23a' : '' }"
                >💾</button>
              </div>
            </div>

            <!-- Sources -->
            <div v-if="msg.sources && msg.sources.length" class="sources-wrap">
              <div v-for="(src, si) in msg.sources" :key="si" class="source-card">
                <div class="source-title">📄 {{ src.title || src.doc_id || '文件' }}</div>
                <div class="source-snippet">{{ src.content_preview || src.content || '' }}</div>
                <div v-if="src.score" class="source-score">相關度: {{ (src.score * 100).toFixed(0) }}%</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Scroll to bottom FAB -->
        <button v-show="!atBottom" class="scroll-fab" @click="scrollToBottom" title="捲到底部">↓</button>
      </template>

      <!-- Input bar (active state) -->
      <div v-if="messages.length > 0" class="input-bar">
        <div class="input-bar-inner">
          <div v-if="attachedDocs.length" class="attached-docs" style="margin-bottom:8px;">
            <el-tag v-for="doc in attachedDocs" :key="doc.id" closable size="small" type="info" @close="removeDoc(doc.id)">
              📄 {{ doc.filename }}
            </el-tag>
          </div>
          <div v-if="slashMenu.show" class="cmd-menu cmd-menu--bar">
            <div v-for="cmd in slashMenu.filtered" :key="cmd.name" class="cmd-item" @mousedown.prevent="applySlash(cmd)">
              <span class="cmd-icon">{{ cmd.icon }}</span>
              <span class="cmd-name">{{ cmd.name }}</span>
              <span class="cmd-desc">{{ cmd.desc }}</span>
            </div>
          </div>
          <div v-if="mentionMenu.show" class="cmd-menu cmd-menu--bar">
            <div v-for="doc in mentionMenu.docs" :key="doc.id" class="cmd-item" @mousedown.prevent="applyMention(doc)">
              <span class="cmd-icon">📄</span>
              <span class="cmd-name">{{ doc.filename }}</span>
            </div>
          </div>
          <el-input
            v-model="inputText"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="輸入問題… （/ 命令，@ 引用文件）"
            @keydown.enter.exact.prevent="sendMessage"
            @input="onInput"
            :disabled="streaming"
          />
          <div class="input-footer">
            <div class="footer-left">
              <el-radio-group v-model="chatMode" size="small" :disabled="streaming">
                <el-radio-button value="chat">💬 對話</el-radio-button>
                <el-radio-button value="agent">🤖 Agent</el-radio-button>
              </el-radio-group>
              <span class="input-hint">Enter 送出 · Shift+Enter 換行</span>
            </div>
            <div class="footer-right">
              <el-select v-model="selectedModel" size="small" class="model-select" :disabled="streaming" placeholder="選擇模型" :title="selectedModel">
                <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
              </el-select>
              <el-button v-if="streaming" type="danger" size="small" @click="stopStreaming">■ 停止</el-button>
              <el-button v-else type="primary" size="small" :disabled="!inputText.trim()" @click="sendMessage">發送</el-button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
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
import { chatStream, conversationsApi, agentApi, systemSettingsApi, docsApi, chatApi } from '../api/index.js'

// ── highlight.js ──────────────────────────────────────────────
;[['javascript', javascript], ['python', python], ['typescript', typescript],
  ['sql', sql], ['bash', bash], ['shell', bash], ['json', json],
  ['xml', xml], ['html', xml], ['css', css]
].forEach(([name, mod]) => hljs.registerLanguage(name, mod))

// ── marked ────────────────────────────────────────────────────
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
  try { return marked.parse(text) } catch { return text }
}

function truncate(str, n = 80) {
  return str && str.length > n ? str.slice(0, n) + '…' : (str || '')
}

// ── State ─────────────────────────────────────────────────────
const conversations = ref([])
const currentConvId = ref(null)
const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const messagesEl = ref(null)
const atBottom = ref(true)
const chatMode = ref('chat')
const renamingId = ref(null)
const renameTitle = ref('')
const availableModels = ref([])
const selectedModel = ref('')
let modelPollTimer = null
let abortController = null
let agentPollActive = false

const SLASH_COMMANDS = [
  { name: '/search', icon: '🔍', desc: '搜尋知識庫模式' },
  { name: '/agent',  icon: '🤖', desc: '切換 Agent 模式' },
  { name: '/chat',   icon: '💬', desc: '切換對話模式' },
  { name: '/clear',  icon: '🗑️', desc: '清除當前對話' },
]
const slashMenu = reactive({ show: false, filtered: [] })
const mentionMenu = reactive({ show: false, docs: [] })
const attachedDocs = ref([])

const quickPrompts = [
  { icon: '💻', label: '程式碼', text: '幫我撰寫程式：' },
  { icon: '📖', label: '解釋概念', text: '請解釋：' },
  { icon: '✏️', label: '文字創作', text: '幫我寫：' },
  { icon: '🔍', label: '搜尋知識庫', text: '在知識庫中搜尋：' },
  { icon: '📊', label: '資料分析', text: '幫我分析：' },
]

// ── Scroll ────────────────────────────────────────────────────
function onScroll() {
  if (!messagesEl.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesEl.value
  atBottom.value = scrollHeight - scrollTop - clientHeight < 80
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
      atBottom.value = true
    }
  })
}

// ── Code copy (event delegation) ──────────────────────────────
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

// ── Message actions ───────────────────────────────────────────
function copyText(text) {
  navigator.clipboard.writeText(text || '').then(() => ElMessage.success('已複製'))
}

const savedMsgIds = ref(new Set())

async function saveToKb(msg) {
  if (!msg.id || savedMsgIds.value.has(msg.id)) return
  try {
    await chatApi.saveToKb(msg.id)
    savedMsgIds.value.add(msg.id)
    ElMessage.success('已加入知識庫，正在背景索引…')
  } catch (e) {
    ElMessage.error('存入失敗：' + e.message)
  }
}

async function retryFrom(idx) {
  let ui = idx - 1
  while (ui >= 0 && messages.value[ui].role !== 'user') ui--
  if (ui < 0) return
  const userContent = messages.value[ui].content
  messages.value.splice(ui)
  inputText.value = userContent
  await sendMessage()
}

// ── Conversations ─────────────────────────────────────────────
async function loadConversations() {
  try { conversations.value = await conversationsApi.list() } catch {}
}

async function selectConversation(conv) {
  currentConvId.value = conv.id
  try {
    const data = await conversationsApi.get(conv.id)
    messages.value = data || []
  } catch {}
  scrollToBottom()
}

function newConversation() {
  stopStreaming()
  streaming.value = false
  currentConvId.value = null
  messages.value = []
  attachedDocs.value = []
  inputText.value = ''
  slashMenu.show = false
  mentionMenu.show = false
}

async function deleteConversation(id) {
  try {
    await conversationsApi.delete(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConvId.value === id) newConversation()
  } catch (e) { ElMessage.error(e.message) }
}

function startRename(conv) {
  renamingId.value = conv.id
  renameTitle.value = conv.title
  nextTick(() => {
    const input = document.querySelector('.rename-input input')
    if (input) { input.focus(); input.select() }
  })
}

function cancelRename() { renamingId.value = null; renameTitle.value = '' }

async function commitRename(conv) {
  const title = renameTitle.value.trim()
  if (!title || title === conv.title) { cancelRename(); return }
  try {
    await conversationsApi.rename(conv.id, title)
    conv.title = title
  } catch (e) { ElMessage.error(e.message) }
  cancelRename()
}

// ── Models ────────────────────────────────────────────────────
async function loadModels() {
  try {
    const data = await systemSettingsApi.getModels()
    availableModels.value = data.models || []
    if (!selectedModel.value || !availableModels.value.includes(selectedModel.value)) {
      selectedModel.value = data.default || availableModels.value[0] || ''
    }
  } catch {}
}

function usePrompt(text) { inputText.value = text }

// ── Input: slash + @ ─────────────────────────────────────────
function onInput() {
  const text = inputText.value
  const slashMatch = text.match(/(^|\s)(\/\S*)$/)
  if (slashMatch) {
    const q = slashMatch[2].toLowerCase()
    slashMenu.filtered = SLASH_COMMANDS.filter(c => c.name.startsWith(q))
    slashMenu.show = slashMenu.filtered.length > 0
  } else {
    slashMenu.show = false
  }
  const atMatch = text.match(/@(\S*)$/)
  if (atMatch) searchMentionDocs(atMatch[1])
  else mentionMenu.show = false
}

function applySlash(cmd) {
  inputText.value = inputText.value.replace(/(^|\s)(\/\S*)$/, '$1')
  slashMenu.show = false
  if (cmd.name === '/agent') { chatMode.value = 'agent'; ElMessage.success('切換至 Agent 模式') }
  else if (cmd.name === '/chat') { chatMode.value = 'chat'; ElMessage.success('切換至對話模式') }
  else if (cmd.name === '/clear') newConversation()
}

async function searchMentionDocs(query) {
  try {
    const res = await docsApi.list({ q: query, limit: 8 })
    const items = res.items || res
    mentionMenu.docs = Array.isArray(items) ? items.slice(0, 8) : []
    mentionMenu.show = mentionMenu.docs.length > 0
  } catch { mentionMenu.show = false }
}

function applyMention(doc) {
  inputText.value = inputText.value.replace(/@\S*$/, '')
  mentionMenu.show = false
  if (!attachedDocs.value.find(d => d.id === doc.id)) attachedDocs.value.push(doc)
}

function removeDoc(docId) {
  attachedDocs.value = attachedDocs.value.filter(d => d.id !== docId)
}

// ── Stop ──────────────────────────────────────────────────────
function stopStreaming() {
  if (abortController) { abortController.abort(); abortController = null }
  agentPollActive = false
}

// ── Send ──────────────────────────────────────────────────────
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  scrollToBottom()
  if (chatMode.value === 'agent') await runAgent(text)
  else await runChat(text)
}

async function runChat(text) {
  const aiMsg = { role: 'assistant', content: '', sources: [], streaming: true }
  messages.value.push(aiMsg)
  streaming.value = true
  abortController = new AbortController()
  try {
    const docIds = attachedDocs.value.map(d => d.id)
    const resp = await chatStream(text, currentConvId.value, selectedModel.value || null, abortController.signal, docIds)
    if (!resp.ok) { aiMsg.content = '⚠️ 請求失敗，請重試'; return }
    // backend 把新建的 conv_id 放在 X-Conversation-Id header
    const headerConvId = resp.headers.get('X-Conversation-Id')
    if (headerConvId && !currentConvId.value) currentConvId.value = headerConvId
    const reader = resp.body.getReader()
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
        if (raw === '[DONE]') { aiMsg.streaming = false; await loadConversations(); break }
        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'token') { aiMsg.content += evt.text; if (atBottom.value) scrollToBottom() }
          else if (evt.type === 'sources') aiMsg.sources = evt.sources || []
          else if (evt.type === 'conv_id') currentConvId.value = evt.id
        } catch {}
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') aiMsg.content += '\n\n_[已停止]_'
    else aiMsg.content = '⚠️ 錯誤：' + e.message
  } finally {
    aiMsg.streaming = false
    streaming.value = false
    abortController = null
    scrollToBottom()
  }
}

async function runAgent(instruction) {
  const aiMsg = { role: 'assistant', content: '', steps: [], sources: [], streaming: true }
  messages.value.push(aiMsg)
  streaming.value = true
  agentPollActive = true
  try {
    const res = await agentApi.run(instruction, selectedModel.value || null)
    const taskId = res.task_id
    if (res.conv_id) currentConvId.value = res.conv_id
    let attempts = 0
    const poll = async () => {
      if (!agentPollActive) return   // 已被 newConversation/stopStreaming 取消
      if (attempts >= 60) {
        aiMsg.content = '⚠️ Agent 任務超時'
        aiMsg.streaming = false; streaming.value = false; return
      }
      attempts++
      try {
        const status = await agentApi.getTask(taskId)
        if (!agentPollActive) return  // await 期間被取消
        aiMsg.steps = status.steps || []
        if (atBottom.value) scrollToBottom()
        if (status.status === 'completed') {
          aiMsg.content = status.result || '✅ 任務完成'
          aiMsg.streaming = false; streaming.value = false
          await loadConversations()
        } else if (status.status === 'failed') {
          aiMsg.content = '⚠️ 任務失敗：' + (status.error || '未知錯誤')
          aiMsg.streaming = false; streaming.value = false
        } else {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (!agentPollActive) return
        aiMsg.content = '⚠️ 查詢失敗：' + e.message
        aiMsg.streaming = false; streaming.value = false
      }
    }
    setTimeout(poll, 1000)
  } catch (e) {
    aiMsg.content = '⚠️ 錯誤：' + e.message
    aiMsg.streaming = false; streaming.value = false
  }
}

// ── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await loadConversations()
  await loadModels()
  modelPollTimer = setInterval(loadModels, 30_000)
})

onUnmounted(() => {
  clearInterval(modelPollTimer)
  stopStreaming()
})
</script>

<style scoped>
.chat-root {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: #f8fafc;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

/* ── Sidebar ─────────────────────────────────────────────────── */
.chat-sidebar {
  width: 220px;
  min-width: 220px;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-top { padding: 12px; border-bottom: 1px solid #e2e8f0; }
.new-conv-btn { width: 100%; }
.conv-list { flex: 1; overflow-y: auto; padding: 6px; }
.conv-item {
  padding: 9px 10px;
  cursor: pointer;
  border-radius: 7px;
  font-size: 13px;
  margin-bottom: 2px;
  transition: background 0.12s;
  display: flex;
  align-items: center;
  gap: 4px;
}
.conv-item:hover { background: #e2e8f0; }
.conv-item.active { background: #dbeafe; }
.conv-item-body { flex: 1; min-width: 0; }
.conv-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #1e293b; font-weight: 500; }
.conv-item.active .conv-title { color: #1d4ed8; }
.conv-date { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.conv-delete-btn {
  flex-shrink: 0; display: none; width: 20px; height: 20px;
  border: none; background: transparent; color: #94a3b8;
  font-size: 11px; cursor: pointer; border-radius: 4px; padding: 0;
}
.conv-item:hover .conv-delete-btn { display: flex; align-items: center; justify-content: center; }
.conv-delete-btn:hover { background: #fecaca; color: #dc2626; }
.rename-input { flex: 1; }

/* ── Main ────────────────────────────────────────────────────── */
.chat-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #fff; position: relative; }

/* ── Home state ──────────────────────────────────────────────── */
.chat-home {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 40px 24px; gap: 28px; overflow-y: auto;
}
.home-greeting { display: flex; align-items: center; gap: 14px; }
.home-icon { width: 52px; height: 52px; }
.home-title { font-size: 30px; font-weight: 600; color: #1e293b; letter-spacing: -0.02em; }
.home-input-wrap { width: 100%; max-width: 700px; }
.input-box-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 14px 14px 10px;
  position: relative;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.input-box-card:focus-within { box-shadow: 0 0 0 3px rgba(37,99,235,0.1); border-color: #93c5fd; }
:deep(.home-textarea .el-textarea__inner) {
  border: none !important; background: transparent !important;
  box-shadow: none !important; padding: 0;
  font-size: 15px; resize: none; color: #1e293b;
}
.quick-prompts { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; max-width: 700px; }
.prompt-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 18px; background: #fff;
  border: 1px solid #e2e8f0; border-radius: 20px;
  font-size: 13px; color: #475569; cursor: pointer;
  transition: all 0.12s; font-family: inherit;
}
.prompt-chip:hover { background: #f1f5f9; border-color: #94a3b8; color: #1e293b; }
.chip-icon { font-size: 15px; }

/* ── Input footer (shared) ───────────────────────────────────── */
.input-footer {
  display: flex; align-items: center;
  justify-content: space-between;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid #e2e8f0;
  flex-wrap: wrap; gap: 8px;
}
.footer-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.footer-right { display: flex; align-items: center; gap: 8px; }
.input-hint { font-size: 11px; color: #94a3b8; }
.model-select { width: 150px; }
:deep(.model-select .el-input__wrapper) { border-radius: 6px; padding: 0 8px; }
:deep(.model-select .el-input__inner) { font-size: 12px; }
.attached-docs { display: flex; flex-wrap: wrap; gap: 6px; }

/* ── Slash / Mention menu ────────────────────────────────────── */
.cmd-menu {
  position: absolute; bottom: calc(100% + 6px); left: 0; right: 0;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12); z-index: 100;
  overflow: hidden; max-height: 220px; overflow-y: auto;
}
.cmd-menu--bar { bottom: calc(100% + 4px); }
.cmd-item { display: flex; align-items: center; gap: 10px; padding: 9px 14px; cursor: pointer; transition: background 0.1s; font-size: 13px; }
.cmd-item:hover { background: #f1f5f9; }
.cmd-icon { font-size: 15px; flex-shrink: 0; }
.cmd-name { font-weight: 500; color: #1e293b; flex-shrink: 0; }
.cmd-desc { color: #94a3b8; font-size: 12px; }

/* ── Messages area ───────────────────────────────────────────── */
.messages-area { flex: 1; overflow-y: auto; padding: 24px 20px; display: flex; flex-direction: column; gap: 12px; }
.message-wrap { max-width: 780px; width: 100%; margin: 0 auto; }
.message-row { display: flex; align-items: flex-start; gap: 6px; }
.user-row { justify-content: flex-end; }
.ai-row { justify-content: flex-start; }

/* ── Hover actions ───────────────────────────────────────────── */
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

/* ── Bubbles ─────────────────────────────────────────────────── */
.message-bubble {
  max-width: 78%; padding: 12px 16px; border-radius: 14px;
  font-size: 14px; line-height: 1.75; word-break: break-word;
}
.user-bubble { background: #4a90d9; color: #fff; border-bottom-right-radius: 3px; white-space: pre-wrap; }
.ai-bubble { background: #f8fafc; border: 1px solid #e8edf3; color: #1e293b; border-bottom-left-radius: 3px; min-width: 120px; }

/* ── Thinking dots ───────────────────────────────────────────── */
.thinking { display: flex; gap: 5px; padding: 4px 2px; align-items: center; }
.thinking span {
  width: 7px; height: 7px; background: #94a3b8; border-radius: 50%;
  animation: bounce 1.2s infinite ease-in-out;
}
.thinking span:nth-child(2) { animation-delay: 0.2s; }
.thinking span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

/* ── Cursor ──────────────────────────────────────────────────── */
.cursor { display: inline-block; opacity: 0.7; animation: blink 1s infinite; }
@keyframes blink { 0%,100%{opacity:0.7} 50%{opacity:0} }

/* ── Agent steps ─────────────────────────────────────────────── */
.agent-progress { margin-bottom: 8px; }
.agent-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #64748b; padding: 3px 0; }
.step-icon { flex-shrink: 0; }
.step-tool { font-weight: 600; color: #4a90d9; }
.step-input { color: #94a3b8; font-size: 11px; }

/* ── Sources ─────────────────────────────────────────────────── */
.sources-wrap { max-width: 780px; width: 100%; margin: 6px auto 0; display: flex; flex-wrap: wrap; gap: 8px; }
.source-card { background: #f0f7ff; border: 1px solid #c0d8f0; border-radius: 8px; padding: 8px 12px; font-size: 12px; max-width: 220px; }
.source-title { font-weight: 600; color: #1a6fa8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-snippet { color: #555; margin-top: 4px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.source-score { color: #888; margin-top: 4px; }

/* ── Scroll FAB ──────────────────────────────────────────────── */
.scroll-fab {
  position: absolute; bottom: 90px; right: 20px;
  width: 36px; height: 36px;
  background: #4a90d9; color: #fff;
  border: none; border-radius: 50%; font-size: 16px;
  cursor: pointer; box-shadow: 0 3px 10px rgba(0,0,0,0.2);
  transition: background 0.15s, transform 0.15s; z-index: 10;
}
.scroll-fab:hover { background: #2563eb; transform: scale(1.05); }

/* ── Input bar (active) ──────────────────────────────────────── */
.input-bar { padding: 10px 16px 14px; border-top: 1px solid #e2e8f0; background: #fff; }
.input-bar-inner { max-width: 780px; margin: 0 auto; position: relative; }
:deep(.input-bar-inner .el-textarea__inner) { border-radius: 10px; font-size: 14px; resize: none; }

/* ── Markdown body ───────────────────────────────────────────── */
:deep(.markdown-body) { font-size: 14px; line-height: 1.8; color: #1e293b; }
:deep(.markdown-body h1),:deep(.markdown-body h2),:deep(.markdown-body h3) { font-weight: 600; margin: 1em 0 0.4em; color: #0f172a; }
:deep(.markdown-body h1) { font-size: 1.4em; }
:deep(.markdown-body h2) { font-size: 1.2em; }
:deep(.markdown-body h3) { font-size: 1.05em; }
:deep(.markdown-body p) { margin: 0.5em 0; }
:deep(.markdown-body ul),:deep(.markdown-body ol) { padding-left: 1.6em; margin: 0.4em 0; }
:deep(.markdown-body li) { margin: 0.2em 0; }
:deep(.markdown-body blockquote) {
  border-left: 3px solid #94a3b8; padding: 4px 12px;
  color: #64748b; margin: 8px 0; background: #f8fafc;
  border-radius: 0 6px 6px 0;
}
:deep(.markdown-body strong) { font-weight: 600; }
:deep(.markdown-body em) { font-style: italic; }
:deep(.markdown-body a) { color: #4a90d9; text-decoration: none; }
:deep(.markdown-body a:hover) { text-decoration: underline; }
:deep(.markdown-body table) { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
:deep(.markdown-body th),:deep(.markdown-body td) { border: 1px solid #e2e8f0; padding: 6px 12px; }
:deep(.markdown-body th) { background: #f1f5f9; font-weight: 600; }
:deep(.markdown-body code:not(.hljs)) {
  background: #f1f5f9; padding: 1px 5px; border-radius: 4px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 0.9em; color: #e53e3e;
}
:deep(.markdown-body hr) { border: none; border-top: 1px solid #e2e8f0; margin: 12px 0; }

/* ── Code blocks ─────────────────────────────────────────────── */
:deep(.code-block) { margin: 8px 0; border-radius: 8px; overflow: hidden; border: 1px solid #2d3748; font-size: 13px; }
:deep(.code-header) { display: flex; align-items: center; justify-content: space-between; background: #2d3748; padding: 5px 12px; }
:deep(.code-lang) { font-size: 11px; color: #a0aec0; font-family: monospace; text-transform: uppercase; }
:deep(.code-copy-btn) {
  background: transparent; border: 1px solid #4a5568;
  color: #a0aec0; font-size: 11px; padding: 2px 8px;
  border-radius: 4px; cursor: pointer; transition: all 0.15s;
}
:deep(.code-copy-btn:hover) { background: #4a5568; color: #fff; }
:deep(.code-block pre) { margin: 0; padding: 14px 16px; overflow-x: auto; }
:deep(.code-block code) { font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6; }

/* ── highlight.js theme ──────────────────────────────────────── */
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
:deep(.hljs-symbol),:deep(.hljs-bullet) { color: #79c0ff; }
:deep(.hljs-meta) { color: #8b949e; }
:deep(.hljs-deletion) { color: #ffa198; background: #490202; }
:deep(.hljs-addition) { color: #7ee787; background: #04260f; }
:deep(.hljs-emphasis) { font-style: italic; }
:deep(.hljs-strong) { font-weight: bold; }
</style>

