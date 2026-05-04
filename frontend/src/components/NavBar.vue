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
        <component :is="item.icon" :size="18" :stroke-width="1.5" />
        {{ item.label }}
      </router-link>
    </nav>
    <div v-if="appVersion" class="navbar-version" @click="goToUpdateSettings">
      <span class="version-text">v{{ appVersion }}</span>
      <span v-if="hasNewVersion" class="version-new-badge">NEW</span>
    </div>
    <div class="navbar-footer" title="使用者設定" @click="goToUserSettings">
      <div class="footer-avatar">{{ authStore.userEmail ? authStore.userEmail[0].toUpperCase() : '?' }}</div>
      <div class="footer-info">
        <div class="footer-email">{{ authStore.userEmail }}</div>
        <span class="footer-role" :class="{ 'role-admin': authStore.userRole === 'admin' }">{{ authStore.userRole }}</span>
      </div>
      <LogOut :size="16" :stroke-width="1.5" class="footer-logout" @click.stop="handleLogout" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useRouter } from 'vue-router'
import { MessageSquare, FolderOpen, Network, Puzzle, Dna, Settings, LogOut } from 'lucide-vue-next'

const authStore = useAuthStore()
const router = useRouter()

const appVersion = ref(window.electronApp?.version || '')
const hasNewVersion = ref(false)

onMounted(() => {
  window.electronApp?.onUpdateAvailable?.(() => { hasNewVersion.value = true })
})

function goToUpdateSettings() {
  router.push({ path: '/settings', query: { group: 'update' } })
}

const navItems = [
  { path: '/chat',     label: '對話',       icon: MessageSquare },
  { path: '/docs',     label: '文件管理',   icon: FolderOpen },
  { path: '/ontology', label: '知識圖譜',   icon: Network },
  { path: '/plugins',  label: '插件管理',   icon: Puzzle },
  { path: '/protein',  label: '蛋白質圖譜', icon: Dna },
  { path: '/settings', label: '設定 / Wiki', icon: Settings },
]

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function goToUserSettings() {
  router.push({ path: '/settings', query: { group: 'user' } })
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
  height: 100%;
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
  padding: 8px 12px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.navbar-footer:hover { background: #e8f0fe; }

.footer-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.footer-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.footer-email {
  font-size: 12px;
  color: var(--el-text-color-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 90px;
}

.footer-role {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #64748b;
  align-self: flex-start;
}
.footer-role.role-admin {
  background: #fee2e2;
  color: #b91c1c;
}

.footer-logout {
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  flex-shrink: 0;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.footer-logout:hover { color: #ef4444; }

.navbar-version {
  padding: 5px 14px 4px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  border-top: 1px solid #e2e8f0;
}
.navbar-version:hover .version-text { color: #1d4ed8; }

.version-text {
  font-size: 11px;
  color: #94a3b8;
  letter-spacing: 0.02em;
  transition: color 0.15s;
}

.version-new-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: #2563eb;
  color: #fff;
  padding: 1px 5px;
  border-radius: 4px;
  animation: badge-pulse 2s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.6; }
}
</style>
