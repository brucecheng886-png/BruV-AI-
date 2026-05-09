import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUpdateStore = defineStore('update', () => {
  // '' = 沒有新版；有值表示新版版號
  const newVersion = ref('')
  // true = 下載完成，可以安裝
  const downloadReady = ref(false)

  function setAvailable (version) {
    newVersion.value = version
    downloadReady.value = false
  }

  function setDownloaded (version) {
    newVersion.value = version
    downloadReady.value = true
  }

  function clear () {
    newVersion.value = ''
    downloadReady.value = false
  }

  return { newVersion, downloadReady, setAvailable, setDownloaded, clear }
})
