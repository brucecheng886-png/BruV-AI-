<template>
  <div class="navbar">
    <div class="navbar-logo">
      <img src="/logo.svg" alt="logo" class="logo-img" />
      <span class="logo-text">BruV AI知識庫</span>
    </div>
    <nav class="navbar-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        active-class="nav-active"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        {{ item.label }}
      </router-link>
    </nav>
    <div class="navbar-footer">
      <div class="navbar-email">{{ authStore.userEmail }}</div>
      <el-button size="small" plain @click="handleLogout" style="width:100%;">登出</el-button>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from '../stores/auth.js'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const navItems = [
  { path: '/chat', label: '對話', icon: 'ChatDotRound' },
  { path: '/docs', label: '文件管理', icon: 'Document' },
  { path: '/ontology', label: '知識圖譜', icon: 'Share' },
  { path: '/plugins', label: '插件管理', icon: 'Grid' },
  { path: '/protein', label: '蛋白質圖譜', icon: 'Connection' },
  { path: '/settings', label: '設定 / Wiki', icon: 'Setting' },
]

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.navbar {
  width: 200px;
  min-width: 200px;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

.navbar-logo {
  padding: 14px 16px 12px;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
}

.logo-img {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.navbar-nav {
  flex: 1;
  padding: 8px 8px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  color: #475569;
  text-decoration: none;
  font-size: 14px;
  border-radius: 7px;
  margin-bottom: 2px;
  transition: background 0.15s, color 0.15s;
}

.nav-item:hover {
  background: #e2e8f0;
  color: #1e293b;
}

.nav-active {
  background: #dbeafe !important;
  color: #1d4ed8 !important;
  font-weight: 600;
}

.navbar-footer {
  padding: 14px 16px;
  border-top: 1px solid #e2e8f0;
}

.navbar-email {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
