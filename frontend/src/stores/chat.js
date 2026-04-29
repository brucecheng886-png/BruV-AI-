import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { conversationsApi, chatStream } from '../api/index.js'
import { useAuthStore } from './auth.js'

export const useChatStore = defineStore('chat', () => {
  // ── 對話列表 ──────────────────────────────────────────
  const conversations = ref([])
  const currentConvId = ref(null)
  const messages = ref([])

  // ── 串流狀態（全域，不跟元件生命週期綁定） ────────────
  const streaming = ref(false)
  const abortController = ref(null)

  // ── 通知狀態 ──────────────────────────────────────────
  const hasNewMessage = ref(false)  // FAB 紅點

  // ── 選擇的模型（全域共用）────────────────────────────────
  const selectedModel = ref(localStorage.getItem('last-selected-model') || '')

  // ── AgentPanel tab 狀態（三個 tab 各自的 convId） ─────
  const agentTabConvIds = ref({ page: null, global: null, kb: null })

  // ── 計算屬性 ──────────────────────────────────────────
  const currentConversation = computed(() =>
    conversations.value.find(c => c.id === currentConvId.value) || null
  )

  // ── 對話列表操作 ──────────────────────────────────────
  async function loadConversations() {
    try { conversations.value = await conversationsApi.list() } catch {}
  }

  async function loadMessages(convId) {
    try {
      const data = await conversationsApi.get(convId)
      messages.value = data || []
    } catch {}
  }

  async function selectConversation(conv) {
    currentConvId.value = conv.id
    await loadMessages(conv.id)
  }

  function addConversation(conv) {
    conversations.value.unshift(conv)
    currentConvId.value = conv.id
  }

  function removeConversation(id) {
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConvId.value === id) {
      currentConvId.value = null
      messages.value = []
    }
  }

  function updateConversationTitle(id, title) {
    const conv = conversations.value.find(c => c.id === id)
    if (conv) conv.title = title
  }

  // ── 訊息操作 ──────────────────────────────────────────
  function appendMessage(msg) {
    messages.value.push(msg)
  }

  function updateLastMessage(patch) {
    if (!messages.value.length) return
    const last = messages.value[messages.value.length - 1]
    Object.assign(last, patch)
  }

  function clearMessages() {
    messages.value = []
    currentConvId.value = null
  }

  // ── 串流控制 ──────────────────────────────────────────
  function stopStreaming() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    streaming.value = false
  }

  // ── 通知 ──────────────────────────────────────────────
  function markNewMessage() {
    hasNewMessage.value = true
  }

  function clearNewMessage() {
    hasNewMessage.value = false
  }

  function setSelectedModel(model) {
    selectedModel.value = model
    try { localStorage.setItem('last-selected-model', model) } catch {}
  }

  return {
    conversations, currentConvId, messages, streaming,
    abortController, hasNewMessage, agentTabConvIds,
    currentConversation, selectedModel,
    loadConversations, loadMessages, selectConversation,
    addConversation, removeConversation, updateConversationTitle,
    appendMessage, updateLastMessage, clearMessages,
    stopStreaming, markNewMessage, clearNewMessage, setSelectedModel,
  }
})
