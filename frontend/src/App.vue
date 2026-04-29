<template>
  <div v-if="authStore.token" class="app-root">
    <TitleBar v-if="isElectron" />
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
const agentPanelOpen = ref(false)

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
</style>
