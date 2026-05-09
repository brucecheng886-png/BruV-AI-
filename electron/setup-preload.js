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

  // Step 4: 偵測 NVIDIA GPU（供顯示運算模式選擇）
  detectGpu: () => ipcRenderer.invoke('setup:detectGpu'),

  // Step 4: 列出已安裝模型（用於 wizard 自動跳過）
  listOllamaModels: () => ipcRenderer.invoke('setup:listOllamaModels'),

  // Step 4: 下載 Ollama 模型（主機 CLI，流式進度）
  pullOllamaModel: (modelName) =>
    ipcRenderer.invoke('setup:pullOllamaModel', modelName),
  onOllamaProgress: (cb) =>
    ipcRenderer.on('setup:ollamaProgress', (_, data) => cb(data)),

  // Step 6: 檢查模型是否已在 Docker Ollama 容器內
  checkDockerOllamaModel: (modelName) =>
    ipcRenderer.invoke('setup:checkDockerOllamaModel', modelName),

  // Step 6: 在 Docker Ollama 容器內下載模型
  pullDockerOllamaModel: (modelName) =>
    ipcRenderer.invoke('setup:pullDockerOllamaModel', modelName),

  // Step 5: 將設定寫入 .env 檔案
  saveEnvSettings: (settings) =>
    ipcRenderer.invoke('setup:saveEnvSettings', settings),

  // Step 6: 啟動容器服務
  startServices: () => ipcRenderer.invoke('setup:startServices'),

  // Step 6: Docker compose 即時 log（串流）
  onDockerLog: (cb) =>
    ipcRenderer.on('setup:dockerLog', (_, line) => cb(line)),

  // Step 6: 等待後端就緒（輪詢 health，附進度事件）
  waitForBackend: () => ipcRenderer.invoke('setup:waitForBackend'),
  onBackendProgress: (cb) =>
    ipcRenderer.on('setup:backendProgress', (_, text) => cb(text)),

  // Step 6: 寫入完成標記，關閉精靈，開啟主視窗
  completeSetup: () => ipcRenderer.invoke('setup:completeSetup'),

  // Step 6: 初始化管理員帳號（呼叫後端 init-admin API）
  initAdmin: (email, password) =>
    ipcRenderer.invoke('setup:initAdmin', { email, password }),

  // 通用：在系統瀏覽器開啟外部連結
  openExternal: (url) => ipcRenderer.invoke('setup:openExternal', url),

  // Step 1: 環境預檢
  checkEnvironment: () => ipcRenderer.invoke('setup:checkEnvironment'),

  // 視窗控制
  minimize:    () => ipcRenderer.invoke('setup:minimize'),
  maximize:    () => ipcRenderer.invoke('setup:maximize'),
  closeWindow: () => ipcRenderer.invoke('setup:closeWindow'),
})
