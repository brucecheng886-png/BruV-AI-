<template>
  <div v-if="authStore.token" class="app-root">
    <!-- 更新中全螢幕遮罩 -->
    <div v-if="isUpdating" class="update-overlay">
      <div class="update-overlay-box">
        <div class="update-spinner"></div>
        <p class="update-overlay-title">正在安裝更新</p>
        <p class="update-overlay-sub">應用程式即將自動重新啟動，請稍候…</p>
      </div>
    </div>
    <!-- 更新通知橫幅 -->
    <div v-if="updateInfo" class="update-banner" :class="{ 'update-banner--ready': updateInfo.ready }">
      <template v-if="!updateInfo.ready">
        ⬇️ 新版本 v{{ updateInfo.version }} 下載中…
      </template>
      <template v-else>
        ✅ 新版本 v{{ updateInfo.version }} 已就緒，重啟後套用
        <button class="update-banner-btn" @click="relaunchApp">立即重啟</button>
      </template>
      <button class="update-banner-close" @click="updateInfo = null">✕</button>
    </div>
    <div class="app-body" :style="{ '--agent-panel-w': (agentPanelOpen && showAgentPanel) ? '380px' : '0px' }">
      <NavBar />
      <main class="app-main" :class="{ 'agent-panel-open': agentPanelOpen && showAgentPanel }">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
      <AgentPanel v-model="agentPanelOpen" />
    </div>
    <!-- 版本號標籤（右下角） -->
    <div v-if="isElectron" class="app-version-badge">v{{ appVersion }}</div>
  </div>
  <div v-else>
    <router-view />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import NavBar from './components/NavBar.vue'
import AgentPanel from './components/AgentPanel.vue'
import { useAuthStore } from './stores/auth.js'
import { useUpdateStore } from './stores/update.js'

const authStore = useAuthStore()
const updateStore = useUpdateStore()
const route = useRoute()
const isElectron = navigator.userAgent.includes('Electron') || !!window.electronApp?.version
const appVersion = computed(() => window.electronApp?.version || '')
const agentPanelOpen = ref(false)
const isUpdating = ref(false)

// 對話頁面不顯示 AgentPanel
const showAgentPanel = computed(() => route.path !== '/chat' && route.path !== '/')

// 切成對話頁面時自動關閉面板
watch(showAgentPanel, (val) => { if (!val) agentPanelOpen.value = false })

function relaunchApp () {
  isUpdating.value = true
  setTimeout(() => {
    window.electronAPI?.relaunchForUpdate?.()
  }, 1500)
}

onMounted(() => {
  if (window.electronApp?.version) {
    document.documentElement.classList.add('electron-app')
    window.electronApp.onUpdateAvailable?.((info) => {
      updateStore.setAvailable(info?.version || '')
    })
    window.electronApp.onUpdateDownloaded?.((info) => {
      updateStore.setDownloaded(info?.version || '')
    })
  }
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'PingFang TC', sans-serif; }

:root { --titlebar-h: 0px; }

.app-root { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.app-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.app-main { flex: 1; overflow-y: auto; overflow-x: hidden; min-width: 0; transition: padding-right 0.25s ease; }
.app-main.agent-panel-open { padding-right: 380px; }

/* ── 更新中全螢幕遮罩 ───────────────── */
.update-overlay {
  position: fixed;
  inset: 0;
  background: #f8f9fa;
  z-index: 99999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.update-overlay-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.update-spinner {
  width: 44px;
  height: 44px;
  border: 4px solid #dee2e6;
  border-top-color: #3b5bdb;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.update-overlay-title {
  font-size: 18px;
  font-weight: 600;
  color: #212529;
}
.update-overlay-sub {
  font-size: 13px;
  color: #868e96;
}

/* ── 更新通知橫幅 ───────────────────── */
.update-banner {
  background: #3b5bdb;
  color: #fff;
  font-size: 13px;
  padding: 7px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  z-index: 9999;
  transition: background 0.3s;
}
.update-banner--ready {
  background: #2f9e44;
}
.update-banner-btn {
  background: rgba(255,255,255,0.2);
  border: 1px solid rgba(255,255,255,0.5);
  color: #fff;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
  margin-left: 4px;
}
.update-banner-btn:hover { background: rgba(255,255,255,0.35); }
.update-banner-close {
  margin-left: auto;
  background: transparent;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.7;
  line-height: 1;
  padding: 0 4px;
}
.update-banner-close:hover { opacity: 1; }

/* ── 版本號標籤（右下角）──────────────── */
.app-version-badge {
  position: fixed;
  bottom: 8px;
  right: 12px;
  font-size: 11px;
  color: rgba(150, 150, 170, 0.6);
  pointer-events: none;
  user-select: none;
  z-index: 9000;
  letter-spacing: 0.3px;
}
</style>
