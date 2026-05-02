<template>
  <div v-if="authStore.token" class="app-root">
    <TitleBar v-if="isElectron" />
    <!-- 更新通知橫幅 -->
    <div v-if="updateInfo" class="update-banner">
      🎉 新版本 v{{ updateInfo.version }} 下載中，完成後將提示重啟
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
import TitleBar from './components/TitleBar.vue'
import AgentPanel from './components/AgentPanel.vue'
import { useAuthStore } from './stores/auth.js'

const authStore = useAuthStore()
const route = useRoute()
const isElectron = computed(() => !!window.electronApp?.version)
const appVersion = computed(() => window.electronApp?.version || '')
const agentPanelOpen = ref(false)
const updateInfo = ref(null)

// 對話頁面不顯示 AgentPanel
const showAgentPanel = computed(() => route.path !== '/chat' && route.path !== '/')

// 切成對話頁面時自動關閉面板
watch(showAgentPanel, (val) => { if (!val) agentPanelOpen.value = false })

function applyTitleBarTheme (token) {
  if (window.electronApp?.setTheme) {
    window.electronApp.setTheme(token ? 'light' : 'dark')
  }
}

watch(() => authStore.token, applyTitleBarTheme)

onMounted(() => {
  if (window.electronApp?.version) {
    document.documentElement.classList.add('electron-app')
    window.electronApp.onUpdateAvailable?.((info) => { updateInfo.value = info })
  }
  applyTitleBarTheme(authStore.token)
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'PingFang TC', sans-serif; }

:root { --titlebar-h: 0px; }
html.electron-app { --titlebar-h: 38px; }

.app-root { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.app-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.app-main { flex: 1; overflow-y: auto; overflow-x: hidden; min-width: 0; transition: padding-right 0.25s ease; }
.app-main.agent-panel-open { padding-right: 380px; }

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
}
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
