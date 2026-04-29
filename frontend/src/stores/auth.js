import { defineStore } from 'pinia'
import { ref } from 'vue'

const TOKEN_KEY = 'token'
const EMAIL_KEY = 'userEmail'
const ROLE_KEY  = 'userRole'

function readPersistedToken () {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || ''
}
function readPersisted (key) {
  return localStorage.getItem(key) || sessionStorage.getItem(key) || ''
}

export const useAuthStore = defineStore('auth', () => {
  const token       = ref(readPersistedToken())
  const userEmail   = ref(readPersisted(EMAIL_KEY))
  const userRole    = ref(readPersisted(ROLE_KEY))
  const userId      = ref('')
  const displayName = ref('')
  const rememberMe  = ref(!!localStorage.getItem(TOKEN_KEY))

  function _persist (remember) {
    const target  = remember ? localStorage  : sessionStorage
    const cleanup = remember ? sessionStorage : localStorage
    target.setItem(TOKEN_KEY, token.value)
    target.setItem(EMAIL_KEY, userEmail.value)
    target.setItem(ROLE_KEY,  userRole.value)
    cleanup.removeItem(TOKEN_KEY)
    cleanup.removeItem(EMAIL_KEY)
    cleanup.removeItem(ROLE_KEY)
  }

  async function login (email, password, remember = false) {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || '登入失敗')
    }
    const data = await resp.json()
    token.value      = data.access_token
    userEmail.value  = data.email
    userRole.value   = data.role
    userId.value     = data.user_id
    rememberMe.value = !!remember
    _persist(remember)

    if (remember && typeof window !== 'undefined' && window.electronAPI?.saveToken) {
      try { await window.electronAPI.saveToken(token.value) } catch { /* ignore */ }
    } else if (typeof window !== 'undefined' && window.electronAPI?.clearToken) {
      try { await window.electronAPI.clearToken() } catch { /* ignore */ }
    }
  }

  async function logout () {
    token.value       = ''
    userEmail.value   = ''
    userRole.value    = ''
    userId.value      = ''
    displayName.value = ''
    rememberMe.value  = false
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(EMAIL_KEY)
    localStorage.removeItem(ROLE_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(EMAIL_KEY)
    sessionStorage.removeItem(ROLE_KEY)
    if (typeof window !== 'undefined' && window.electronAPI?.clearToken) {
      try { await window.electronAPI.clearToken() } catch { /* ignore */ }
    }
  }

  async function init () {
    if (!token.value && typeof window !== 'undefined' && window.electronAPI?.loadToken) {
      try {
        const result = await window.electronAPI.loadToken()
        if (result?.success && result.token) {
          token.value = result.token
          rememberMe.value = true
        }
      } catch { /* ignore */ }
    }
    if (!token.value) return false

    try {
      const resp = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token.value}` }
      })
      if (!resp.ok) throw new Error('token invalid')
      const me = await resp.json()
      userEmail.value   = me.email || ''
      userRole.value    = me.role  || ''
      userId.value      = me.user_id || me.id || ''
      displayName.value = me.display_name || ''
      return true
    } catch {
      await logout()
      return false
    }
  }

  function setProfile (me) {
    if (!me) return
    if (me.email) userEmail.value = me.email
    if (me.role)  userRole.value  = me.role
    if (me.user_id || me.id) userId.value = me.user_id || me.id
    displayName.value = me.display_name || ''
    const target = rememberMe.value ? localStorage : sessionStorage
    target.setItem(EMAIL_KEY, userEmail.value)
    target.setItem(ROLE_KEY,  userRole.value)
  }

  return {
    token, userEmail, userRole, userId, displayName, rememberMe,
    login, logout, init, setProfile,
  }
})
