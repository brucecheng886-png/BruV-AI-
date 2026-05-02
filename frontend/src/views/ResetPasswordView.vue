<template>
  <div class="auth-wrap">
    <div class="auth-card">
      <h2 class="card-title">重設密碼</h2>

      <template v-if="!success">
        <form @submit.prevent="submit">
          <div class="field">
            <label>新密碼</label>
            <input
              v-model="newPassword"
              type="password"
              autocomplete="new-password"
              placeholder="至少 8 個字元"
              required
              minlength="8"
            />
          </div>
          <div class="field">
            <label>確認密碼</label>
            <input
              v-model="confirm"
              type="password"
              autocomplete="new-password"
              placeholder="再輸入一次"
              required
            />
          </div>
          <p v-if="error" class="msg-error">{{ error }}</p>
          <button type="submit" :disabled="loading" class="btn-primary">
            {{ loading ? '處理中...' : '確認重設' }}
          </button>
        </form>
      </template>

      <template v-else>
        <div class="msg-success">密碼已重設成功！請重新登入。</div>
        <router-link to="/login" class="btn-primary" style="display:block;text-align:center;text-decoration:none;margin-top:16px;">
          前往登入
        </router-link>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route  = useRoute()

const newPassword = ref('')
const confirm     = ref('')
const loading     = ref(false)
const error       = ref('')
const success     = ref(false)
const token       = ref('')

onMounted(() => {
  token.value = route.query.token || ''
  if (!token.value) {
    error.value = '無效的重設連結，請重新申請。'
  }
})

async function submit () {
  error.value = ''
  if (newPassword.value !== confirm.value) {
    error.value = '兩次密碼輸入不一致'
    return
  }
  if (!token.value) {
    error.value = '缺少重設 Token'
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token.value, new_password: newPassword.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      error.value = data.detail || '重設失敗，請重新申請'
    } else {
      success.value = true
      setTimeout(() => router.push('/login'), 3000)
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
  font-size: 15px;
  background: rgba(74, 222, 128, 0.08);
  border: 1px solid rgba(74, 222, 128, 0.2);
  border-radius: 8px;
  padding: 16px;
}
</style>
