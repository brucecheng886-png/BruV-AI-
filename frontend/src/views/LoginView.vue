<template>
  <div class="login-page">
    <!-- 左側：品牌視覺 -->
    <div class="brand-pane">
      <svg class="bg-lines" viewBox="0 0 600 800" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="lg1" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"  stop-color="#6366f1" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>
          </linearGradient>
          <linearGradient id="lg2" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%"  stop-color="#8b5cf6" stop-opacity="0.25"/>
            <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <line x1="-50" y1="120" x2="650" y2="380" stroke="url(#lg1)" stroke-width="1.2"/>
        <line x1="-50" y1="220" x2="650" y2="480" stroke="url(#lg1)" stroke-width="1"/>
        <line x1="-50" y1="320" x2="650" y2="580" stroke="url(#lg2)" stroke-width="1.4"/>
        <line x1="-50" y1="420" x2="650" y2="680" stroke="url(#lg2)" stroke-width="1"/>
        <circle cx="540" cy="160" r="180" fill="url(#lg1)" opacity="0.4"/>
        <circle cx="80"  cy="640" r="220" fill="url(#lg2)" opacity="0.35"/>
      </svg>

      <div class="brand-center">
        <svg class="brand-logo" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%"  stop-color="#6366f1"/>
              <stop offset="100%" stop-color="#8b5cf6"/>
            </linearGradient>
          </defs>
          <rect x="6" y="6" width="84" height="84" rx="20" fill="url(#logo-grad)"/>
          <path d="M28 32 L28 64 L42 64 Q54 64 54 56 Q54 49 46 48 Q54 47 54 40 Q54 32 42 32 Z M36 38 L42 38 Q46 38 46 41 Q46 44 42 44 L36 44 Z M36 50 L43 50 Q47 50 47 54 Q47 58 43 58 L36 58 Z"
            fill="#ffffff"/>
          <circle cx="68" cy="48" r="8" fill="#ffffff" opacity="0.85"/>
        </svg>
        <h1 class="brand-title">BruV AI</h1>
        <p class="brand-subtitle">私有 AI 知識庫系統</p>
      </div>

      <div class="brand-badges">
        <span class="badge">完全本地部署</span>
        <span class="badge">知識庫 RAG</span>
        <span class="badge">AI 智慧問答</span>
      </div>
    </div>

    <!-- 右側：登入表單 -->
    <div class="form-pane">
      <div class="form-wrapper">
        <h2 class="form-title">歡迎回來</h2>
        <p class="form-subtitle">請登入您的帳號</p>

        <form @submit.prevent="handleLogin" class="login-form">
          <div class="field">
            <label for="login-email">帳號</label>
            <input
              id="login-email"
              v-model="form.email"
              type="text"
              placeholder="admin"
              autocomplete="username"
              required
            />
          </div>

          <div class="field">
            <label for="login-password">密碼</label>
            <div class="password-wrap">
              <input
                id="login-password"
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="請輸入密碼"
                autocomplete="current-password"
                required
              />
              <button
                type="button"
                class="toggle-pw"
                @click="showPassword = !showPassword"
                :aria-label="showPassword ? '隱藏密碼' : '顯示密碼'"
              >
                <component :is="showPassword ? EyeOff : Eye" :size="18" :stroke-width="1.6" />
              </button>
            </div>
          </div>

          <label class="remember-row">
            <input type="checkbox" v-model="form.remember" />
            <span>記住我</span>
          </label>

          <button type="submit" class="submit-btn" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            <span>{{ loading ? '登入中...' : '登入' }}</span>
          </button>

          <p v-if="error" class="error-msg">{{ error }}</p>
          <p class="forgot-link"><router-link to="/forgot-password">忘記密碼？</router-link></p>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth.js'

const router    = useRouter()
const authStore = useAuthStore()

const form = reactive({ email: '', password: '', remember: false })
const showPassword = ref(false)
const loading = ref(false)
const error   = ref('')

async function handleLogin () {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(form.email, form.password, form.remember)
    router.push('/chat')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: #0f0f1a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif;
  color: #fff;
}

/* ── 左側 ──────────────────────────────────────────── */
.brand-pane {
  flex: 0 0 55%;
  position: relative;
  background: #0f0f1a;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  overflow: hidden;
}
.bg-lines {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.brand-center {
  position: relative;
  z-index: 1;
  text-align: center;
}
.brand-logo {
  width: 88px;
  height: 88px;
  margin-bottom: 20px;
  filter: drop-shadow(0 0 24px rgba(99, 102, 241, 0.45));
}
.brand-title {
  font-size: 36px;
  font-weight: 700;
  color: #ffffff;
  margin: 0 0 8px;
  letter-spacing: 1.5px;
}
.brand-subtitle {
  font-size: 14px;
  color: #8b8ba7;
  margin: 0;
}
.brand-badges {
  position: absolute;
  bottom: 48px;
  display: flex;
  gap: 10px;
  z-index: 1;
}
.badge {
  font-size: 12px;
  color: #c5c5d6;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 6px 14px;
  border-radius: 100px;
  letter-spacing: 0.5px;
}

/* ── 右側 ──────────────────────────────────────────── */
.form-pane {
  flex: 0 0 45%;
  background: #1a1a2e;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.form-wrapper {
  width: 100%;
  max-width: 360px;
}
.form-title {
  font-size: 24px;
  color: #ffffff;
  font-weight: 600;
  margin: 0 0 6px;
}
.form-subtitle {
  font-size: 14px;
  color: #8b8ba7;
  margin: 0 0 32px;
}
.login-form { display: flex; flex-direction: column; gap: 18px; }
.field { display: flex; flex-direction: column; gap: 8px; }
.field label {
  font-size: 13px;
  color: #c5c5d6;
  font-weight: 500;
}
.field input {
  width: 100%;
  background: #252540;
  border: 1px solid #2e2e4a;
  border-radius: 8px;
  padding: 11px 14px;
  color: #ffffff;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}
.field input::placeholder { color: #5e5e7a; }
.field input:focus { border-color: #6366f1; }

.password-wrap { position: relative; }
.password-wrap input { padding-right: 42px; }
.toggle-pw {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  border: none;
  color: #8b8ba7;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.toggle-pw:hover { color: #c5c5d6; }

.remember-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #c5c5d6;
  cursor: pointer;
  user-select: none;
}
.remember-row input[type="checkbox"] {
  width: 16px; height: 16px;
  accent-color: #6366f1;
  cursor: pointer;
}

.submit-btn {
  width: 100%;
  background: #6366f1;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: background 0.15s;
  margin-top: 4px;
}
.submit-btn:hover:not(:disabled) { background: #5254cc; }
.submit-btn:disabled { opacity: 0.7; cursor: not-allowed; }

.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-msg {
  margin: 4px 0 0;
  color: #f87171;
  font-size: 13px;
  text-align: center;
}

.forgot-link {
  margin: 8px 0 0;
  text-align: right;
  font-size: 13px;
}
.forgot-link a {
  color: #6b7fff;
  text-decoration: none;
}
.forgot-link a:hover {
  text-decoration: underline;
}

/* ── 響應式 ──────────────────────────────────────── */
@media (max-width: 768px) {
  .brand-pane { display: none; }
  .form-pane { flex: 1 1 100%; }
}
</style>
