<template>
  <div class="chat-root">
    <!-- Sidebar -->
    <aside class="chat-sidebar">
      <div class="sidebar-top">
        <el-button type="primary" class="new-conv-btn" @click="newConversation">
          + 新對話
        </el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="conv-item"
          :class="{ active: currentConvId === conv.id }"
          @click="selectConversation(conv)"
        >
          <div class="conv-item-body">
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-date">{{ conv.created_at?.slice(0,10) }}</div>
          </div>
          <button class="conv-delete-btn" @click.stop="deleteConversation(conv.id)" title="刪除對話">
            ✕
          </button>
        </div>
      </div>
    </aside>

    <!-- Main -->
    <div class="chat-main">

      <!-- Home state: centered Claude-style -->
      <div v-if="messages.length === 0" class="chat-home">
        <div class="home-greeting">
          <img src="/logo.svg" alt="logo" class="home-icon" />
          <span class="home-title">有什麼需要幫忙的？</span>
        </div>

        <div class="home-input-wrap">
          <div class="home-input-card">
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="輸入問題..."
              class="home-textarea"
              @keydown.enter.exact.prevent="sendMessage"
              :disabled="streaming"
            />
            <div class="input-card-footer">
              <span class="input-hint">Enter 送出 · Shift+Enter 換行</span>
              <el-button
                type="primary"
                size="small"
                :disabled="!inputText.trim() || streaming"
                :loading="streaming"
                @click="sendMessage"
              >發送</el-button>
            </div>
          </div>
        </div>

        <div class="quick-prompts">
          <button
            v-for="p in quickPrompts"
            :key="p.label"
            class="prompt-chip"
            @click="usePrompt(p.text)"
          >
            <span class="chip-icon">{{ p.icon }}</span>
            <span>{{ p.label }}</span>
          </button>
        </div>
      </div>

      <!-- Active state: messages + bottom input -->
      <template v-else>
        <div ref="messagesEl" class="messages-area">
          <div v-for="(msg, idx) in messages" :key="idx" class="message-wrap">
            <div class="message-row" :class="msg.role === 'user' ? 'user-row' : 'ai-row'">
              <div class="message-bubble" :class="msg.role === 'user' ? 'user-bubble' : 'ai-bubble'">
                {{ msg.content }}<span v-if="msg.streaming" class="cursor">&#9614;</span>
              </div>
            </div>

            <!-- Source cards -->
            <div v-if="msg.sources && msg.sources.length" class="sources-wrap">
              <div
                v-for="(src, si) in msg.sources"
                :key="si"
                class="source-card"
              >
                <div class="source-title">&#x1F4C4; {{ src.title || src.doc_id || '文件' }}</div>
                <div class="source-snippet">{{ src.content_preview || src.content || '' }}</div>
                <div v-if="src.score" class="source-score">相關度: {{ (src.score * 100).toFixed(0) }}%</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Input bar -->
        <div class="input-bar">
          <div class="input-bar-inner">
            <el-input
              v-model="inputText"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="輸入問題..."
              @keydown.enter.exact.prevent="sendMessage"
              :disabled="streaming"
            />
            <el-button
              type="primary"
              :disabled="!inputText.trim() || streaming"
              :loading="streaming"
              @click="sendMessage"
              class="send-btn"
            >發送</el-button>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { chatStream, conversationsApi } from '../api/index.js'

const conversations = ref([])
const currentConvId = ref(null)
const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const messagesEl = ref(null)

const quickPrompts = [
  { icon: '💻', label: '程式碼', text: '幫我撰寫程式：' },
  { icon: '📖', label: '解釋概念', text: '請解釋：' },
  { icon: '✏️', label: '文字創作', text: '幫我寫：' },
  { icon: '🔍', label: '搜尋知識庫', text: '在知識庫中搜尋：' },
  { icon: '📊', label: '資料分析', text: '幫我分析：' },
]

function usePrompt(text) {
  inputText.value = text
}

onMounted(async () => {
  try {
    conversations.value = await conversationsApi.list()
  } catch {}
})

async function selectConversation(conv) {
  currentConvId.value = conv.id
  try {
    const data = await conversationsApi.get(conv.id)
    messages.value = data.messages || []
  } catch {}
  scrollToBottom()
}

function newConversation() {
  currentConvId.value = null
  messages.value = []
}

async function deleteConversation(id) {
  try {
    await conversationsApi.delete(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConvId.value === id) {
      currentConvId.value = null
      messages.value = []
    }
  } catch {}
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  scrollToBottom()

  const aiMsg = { role: 'assistant', content: '', sources: [], streaming: true }
  messages.value.push(aiMsg)
  streaming.value = true

  try {
    const resp = await chatStream(text, currentConvId.value)
    if (!resp.ok) {
      aiMsg.content = '&#9888; 請求失敗，請重試'
      aiMsg.streaming = false
      streaming.value = false
      return
    }

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
        if (raw === '[DONE]') {
          aiMsg.streaming = false
          try { conversations.value = await conversationsApi.list() } catch {}
          break
        }
        try {
          const evt = JSON.parse(raw)
          if (evt.type === 'token') {
            aiMsg.content += evt.text
            scrollToBottom()
          } else if (evt.type === 'sources') {
            aiMsg.sources = evt.sources || []
          } else if (evt.type === 'conv_id') {
            currentConvId.value = evt.id
          }
        } catch {}
      }
    }
  } catch (e) {
    aiMsg.content = '&#9888; 錯誤：' + e.message
  } finally {
    aiMsg.streaming = false
    streaming.value = false
    scrollToBottom()
  }
}
</script>

<style scoped>
.chat-root {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: #f8fafc;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

/* Sidebar */
.chat-sidebar {
  width: 220px;
  min-width: 220px;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-top {
  padding: 12px;
  border-bottom: 1px solid #e2e8f0;
}
.new-conv-btn { width: 100%; }
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}
.conv-item {
  padding: 9px 12px;
  cursor: pointer;
  border-radius: 7px;
  font-size: 13px;
  margin-bottom: 2px;
  transition: background 0.12s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.conv-item:hover { background: #e2e8f0; }
.conv-item.active { background: #dbeafe; }
.conv-item-body {
  flex: 1;
  min-width: 0;
}
.conv-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1e293b;
  font-weight: 500;
}
.conv-item.active .conv-title { color: #1d4ed8; }
.conv-date { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.conv-delete-btn {
  flex-shrink: 0;
  display: none;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  border-radius: 4px;
  line-height: 1;
  padding: 0;
  transition: background 0.1s, color 0.1s;
}
.conv-item:hover .conv-delete-btn { display: flex; align-items: center; justify-content: center; }
.conv-delete-btn:hover { background: #fecaca; color: #dc2626; }

/* Main */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

/* ── Home state ── */
.chat-home {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  gap: 28px;
}
.home-greeting {
  display: flex;
  align-items: center;
  gap: 14px;
}
.home-icon { width: 52px; height: 52px; }
.home-title {
  font-size: 30px;
  font-weight: 600;
  color: #1e293b;
  letter-spacing: -0.02em;
}
.home-input-wrap {
  width: 100%;
  max-width: 680px;
}
.home-input-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 16px 16px 10px;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.home-input-card:focus-within {
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
  border-color: #93c5fd;
}
:deep(.home-textarea .el-textarea__inner) {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0;
  font-size: 15px;
  resize: none;
  color: #1e293b;
}
.input-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
}
.input-hint {
  font-size: 11px;
  color: #94a3b8;
}
.quick-prompts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  max-width: 680px;
}
.prompt-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.12s;
  font-family: inherit;
}
.prompt-chip:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #1e293b;
}
.chip-icon { font-size: 15px; }

/* ── Active state ── */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.message-wrap {
  max-width: 760px;
  width: 100%;
  margin: 0 auto;
}
.message-row { display: flex; }
.user-row { justify-content: flex-end; }
.ai-row { justify-content: flex-start; }
.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.7;
}
.user-bubble {
  background: #4a90d9;
  color: #fff;
  border-bottom-right-radius: 2px;
}
.ai-bubble {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #1e293b;
  border-bottom-left-radius: 2px;
}
.cursor {
  display: inline-block;
  opacity: 0.6;
  animation: blink 1s infinite;
}
@keyframes blink { 0%,100%{opacity:0.6} 50%{opacity:0} }

.sources-wrap {
  max-width: 760px;
  width: 100%;
  margin: 8px auto 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.source-card {
  background: #f0f7ff;
  border: 1px solid #c0d8f0;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12px;
  max-width: 220px;
}
.source-title {
  font-weight: 600;
  color: #1a6fa8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-snippet {
  color: #555;
  margin-top: 4px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.source-score { color: #888; margin-top: 4px; }

/* Input bar */
.input-bar {
  padding: 12px 20px 16px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}
.input-bar-inner {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.send-btn { height: 60px; width: 80px; flex-shrink: 0; }
</style>
