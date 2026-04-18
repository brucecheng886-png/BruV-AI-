import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userEmail = ref(localStorage.getItem('userEmail') || '')
  const userRole = ref(localStorage.getItem('userRole') || '')

  async function login(email, password) {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail || '登入失敗')
    }
    const data = await resp.json()
    token.value = data.access_token
    userEmail.value = data.email
    userRole.value = data.role
    localStorage.setItem('token', token.value)
    localStorage.setItem('userEmail', userEmail.value)
    localStorage.setItem('userRole', userRole.value)
  }

  function logout() {
    token.value = ''
    userEmail.value = ''
    userRole.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userEmail')
    localStorage.removeItem('userRole')
  }

  return { token, userEmail, userRole, login, logout }
})
