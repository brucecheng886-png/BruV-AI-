<template>
  <div class="auth-wrap">
    <div class="auth-card">
      <h2 class="card-title">忘記密碼</h2>

      <template v-if="!sent">
        <p class="card-desc">請輸入您的帳號 Email，系統將寄送密碼重設連結。</p>
        <form @submit.prevent="submit">
          <div class="field">
            <label>Email</label>
            <input
              v-model="email"
              type="email"
              autocomplete="email"
              placeholder="your@email.com"
              required
            />
          </div>
          <p v-if="error" class="msg-error">{{ error }}</p>
          <button type="submit" :disabled="loading" class="btn-primary">
            {{ loading ? '傳送中...' : '傳送重設連結' }}
          </button>
        </form>
      </template>

      <template v-else>
        <div class="msg-success">
          若帳號存在，密碼重設連結已寄至 <strong>{{ email }}</strong>。<br />
          請檢查信箱（含垃圾郵件匣），連結 15 分鐘內有效。
        </div>
      </template>

      <p class="back-link"><router-link to="/login">← 返回登入</router-link></p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const email   = ref('')
const loading = ref(false)
const error   = ref('')
const sent    = ref(false)

async function submit () {
  error.value = ''
  loading.value = true
  try {
    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      error.value = data.detail || '發送失敗，請稍後再試'
    } else {
      sent.value = true
    }
  } catch {
    error.value = '網路錯誤，請稍後再試'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f1117;
}
.auth-card {
  background: #1a1d2e;
  border: 1px solid #2e3150;
  border-radius: 12px;
  padding: 40px 36px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.card-title {
  font-size: 22px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0 0 8px;
}
.card-desc {
  font-size: 14px;
  color: #8892a4;
  margin: 0 0 24px;
}
.field {
  margin-bottom: 16px;
}
.field label {
  display: block;
  font-size: 13px;
  color: #8892a4;
  margin-bottom: 6px;
}
.field input {
  width: 100%;
  padding: 10px 12px;
  background: #0f1117;
  border: 1px solid #2e3150;
  border-radius: 8px;
  color: #e2e8f0;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
}
.field input:focus { border-color: #6b7fff; }
.btn-primary {
  width: 100%;
  padding: 11px;
  background: #4f5fff;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  cursor: pointer;
  margin-top: 4px;
  transition: background 0.2s;
}
.btn-primary:hover:not(:disabled) { background: #6b7fff; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.msg-error {
  color: #f87171;
  font-size: 13px;
  margin-bottom: 8px;
}
.msg-success {
  color: #4ade80;
  font-size: 14px;
  line-height: 1.7;
  background: rgba(74, 222, 128, 0.08);
  border: 1px solid rgba(74, 222, 128, 0.2);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 8px;
}
.back-link {
  margin-top: 20px;
  text-align: center;
  font-size: 13px;
}
.back-link a {
  color: #6b7fff;
  text-decoration: none;
}
.back-link a:hover { text-decoration: underline; }
</style>
