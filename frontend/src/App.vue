<template>
  <div v-if="authStore.token" class="app-root">
    <TitleBar v-if="isElectron" />
    <div class="app-body">
      <NavBar />
      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
  <div v-else>
    <router-view />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import NavBar from './components/NavBar.vue'
import TitleBar from './components/TitleBar.vue'
import { useAuthStore } from './stores/auth.js'

const authStore = useAuthStore()
const isElectron = computed(() => !!window.electronApp?.version)

onMounted(() => {
  if (window.electronApp?.version) {
    document.documentElement.classList.add('electron-app')
  }
})
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'PingFang TC', sans-serif; }

:root { --titlebar-h: 0px; }
html.electron-app { --titlebar-h: 38px; }

.app-root { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.app-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.app-main { flex: 1; overflow-y: auto; overflow-x: hidden; min-width: 0; }
</style>
