const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('setupBridge', {
  // Step 2: Docker 安裝檢測
  checkDocker: () => ipcRenderer.invoke('setup:checkDocker'),

  // Step 3: Docker daemon 運行檢測
  checkDockerRunning: () => ipcRenderer.invoke('setup:checkDockerRunning'),

  // Step 3: 啟動 Docker Desktop（長時間操作，內部輪詢並送進度事件）
  startDockerDesktop: () => ipcRenderer.invoke('setup:startDockerDesktop'),
  onDockerStartProgress: (cb) =>
    ipcRenderer.on('setup:dockerProgress', (_, text) => cb(text)),

  // Step 4: Ollama 安裝檢測
  checkOllama: () => ipcRenderer.invoke('setup:checkOllama'),

  // Step 4: 下載 Ollama 模型（流式進度）
  pullOllamaModel: (modelName) =>
    ipcRenderer.invoke('setup:pullOllamaModel', modelName),
  onOllamaProgress: (cb) =>
    ipcRenderer.on('setup:ollamaProgress', (_, data) => cb(data)),

  // Step 5: 將設定寫入 .env 檔案
  saveEnvSettings: (settings) =>
    ipcRenderer.invoke('setup:saveEnvSettings', settings),

  // Step 6: 啟動容器服務
  startServices: () => ipcRenderer.invoke('setup:startServices'),

  // Step 6: 等待後端就緒（輪詢 health，附進度事件）
  waitForBackend: () => ipcRenderer.invoke('setup:waitForBackend'),
  onBackendProgress: (cb) =>
    ipcRenderer.on('setup:backendProgress', (_, text) => cb(text)),

  // Step 6: 寫入完成標記，關閉精靈，開啟主視窗
  completeSetup: () => ipcRenderer.invoke('setup:completeSetup'),

  // 通用：在系統瀏覽器開啟外部連結
  openExternal: (url) => ipcRenderer.invoke('setup:openExternal', url),
})
