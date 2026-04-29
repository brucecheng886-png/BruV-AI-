const { app, BrowserWindow, shell, ipcMain, globalShortcut, Menu, MenuItem, clipboard, dialog, net, safeStorage } = require('electron')
const path = require('path')
const https = require('https')
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')
const { exec, spawn } = require('child_process')

const TARGET_URL = 'http://localhost:80'
const BACKEND_HEALTH_URL = 'http://localhost:80/api/health'
const RETRY_INTERVAL_MS = 2000
const MAX_RETRIES = 30 // 最多等 60 秒
const UPDATE_CHECK_INTERVAL_MS = 60 * 1000 // 每 60 秒檢查前端是否有新版本

let mainWindow = null
let splashWindow = null
let setupWizardWindow = null
let currentBundleHash = null // 記錄目前載入的前端 bundle hash
let updateCheckTimer = null

// docker-compose.yml 路徑（打包後從 extraResources，開發時從專案根目錄）
const resourcePath = app.isPackaged
  ? process.resourcesPath
  : path.join(__dirname, '..')
const composePath = path.join(resourcePath, 'docker-compose.yml')
const envPath = path.join(resourcePath, '.env')
const envExamplePath = path.join(resourcePath, '.env.example')

// ── 確認 .env 存在；若否，從 .env.example 複製一份 ────────────────────────
function randomAlnum (length) {
  // 使用 crypto.randomBytes 產生 base64，去掉非英數字，裁切指定長度
  const bytes = crypto.randomBytes(length * 2)
  const s = bytes.toString('base64').replace(/[^A-Za-z0-9]/g, '')
  return s.slice(0, length)
}

/**
 * 將 .env 中所有 changeme_ 佔位符及 PLUGIN_ENCRYPT_KEY 的 your_fernet_key_here
 * 替換為隨機金鑰。已被替換過的欄位不會重複產生。
 * 同步 NEO4J_AUTH = neo4j/<NEO4J_PASSWORD>。
 */
function randomizeEnvPlaceholders (filePath) {
  if (!fs.existsSync(filePath)) return
  const content = fs.readFileSync(filePath, 'utf8')
  const lines = content.split(/\r?\n/)
  const map = {}

  // 長度規則：JWT_SECRET_KEY 用 32 字元，其餘 16
  const lengthOf = (key) => key === 'JWT_SECRET_KEY' ? 32 : 16

  // 第一輪：替換 changeme_* 與 PLUGIN_ENCRYPT_KEY 佔位符
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^([A-Z_][A-Z0-9_]*)=(.*)$/)
    if (!m) continue
    const key = m[1]
    const val = m[2]
    let newVal = null
    if (val.startsWith('changeme_')) {
      newVal = randomAlnum(lengthOf(key))
    } else if (key === 'PLUGIN_ENCRYPT_KEY' && val === 'your_fernet_key_here') {
      // Fernet 金鑰：32 bytes 的 URL-safe base64
      newVal = crypto.randomBytes(32).toString('base64url') + '='
    } else if (key === 'NEO4J_AUTH' && /^neo4j\/changeme_/.test(val)) {
      // 第二輪才能引用 NEO4J_PASSWORD，此處先註記
      continue
    }
    if (newVal !== null) {
      lines[i] = `${key}=${newVal}`
      map[key] = newVal
    } else {
      map[key] = val
    }
  }

  // 第二輪：同步 NEO4J_AUTH
  if (map.NEO4J_PASSWORD) {
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^NEO4J_AUTH=neo4j\/(.*)$/)
      if (m && m[1].startsWith('changeme_')) {
        lines[i] = `NEO4J_AUTH=neo4j/${map.NEO4J_PASSWORD}`
      }
    }
  }

  fs.writeFileSync(filePath, lines.join('\n'), 'utf8')
}

function ensureEnvFile () {
  try {
    if (!fs.existsSync(envPath)) {
      if (fs.existsSync(envExamplePath)) {
        fs.copyFileSync(envExamplePath, envPath)
      } else {
        // 無範本可複製，建立空白檔避免 docker compose 找不到
        fs.writeFileSync(envPath, '', 'utf8')
      }
    }
    // 隨機化佔位符（幂等：已被替換的欄位不會重生）
    randomizeEnvPlaceholders(envPath)
  } catch (err) {
    console.error('[ensureEnvFile] 失敗：', err)
  }
}

// ── Helper：Promise 包裝 exec ─────────────────────────────────────────────
function runCommand (cmd, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    exec(cmd, { timeout: timeoutMs }, (err, stdout) => {
      if (err) reject(err)
      else resolve(stdout)
    })
  })
}

// ── 更新 loading 視窗狀態文字 ─────────────────────────────────────────
function updateLoadingStatus (text) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('loading-status', text)
  }
}

// ── 建立 Splash 等待視窗 ─────────────────────────────────────────────────────
function createSplash () {
  splashWindow = new BrowserWindow({
    width: 440,
    height: 300,
    frame: false,
    alwaysOnTop: true,
    transparent: false,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'loading-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    }
  })
  splashWindow.loadFile(path.join(__dirname, 'loading.html'))
}

// ── Docker 環境檢測與啟動流程 ─────────────────────────────────────────────
/**
 * Step 1: 確認 Docker 已安裝。未安裝則引導下載并退出。
 * @returns {Promise<boolean>}
 */
async function checkDocker () {
  updateLoadingStatus('正在檢測 Docker 環境...')
  try {
    await runCommand('docker --version')
    return true
  } catch {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      buttons: ['立即下載安裝', '取消'],
      defaultId: 0,
      cancelId: 1,
      title: 'BruV AI — 需要安裝 Docker',
      message: '需要安裝 Docker Desktop 才能使用 BruV AI。是否立即下載安裝？',
      detail: '請安裝 Docker Desktop 後重新啟動 BruV AI。'
    })
    if (response === 0) {
      shell.openExternal('https://www.docker.com/products/docker-desktop/')
      await dialog.showMessageBox({
        type: 'info',
        buttons: ['確定'],
        title: 'BruV AI',
        message: '請安裝完成後重新啟動 BruV AI'
      })
    }
    app.quit()
    return false
  }
}

/**
 * Step 2: 確認 Docker daemon 正在執行。若否，自動啟動 Docker Desktop 並等待。
 * @returns {Promise<boolean>}
 */
async function ensureDockerRunning () {
  try {
    await runCommand('docker info')
    return true
  } catch {
    updateLoadingStatus('正在啟動 Docker Desktop...')
    try {
      if (process.platform === 'win32') {
        exec('start "" "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"')
      } else if (process.platform === 'darwin') {
        exec('open -a Docker')
      }
    } catch { /* 忽略啟動錯誤，持續輸詢 */ }

    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 3000))
      try {
        await runCommand('docker info')
        updateLoadingStatus('Docker 已就緒')
        return true
      } catch {
        updateLoadingStatus(`正在等待 Docker 啟動... (${(i + 1) * 3}s / 60s)`)
      }
    }

    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    await dialog.showMessageBox({
      type: 'error',
      buttons: ['確定'],
      title: 'BruV AI — 啟動失敗',
      message: 'Docker Desktop 無法在 60 秒內啟動',
      detail: '請手動開啟 Docker Desktop 後重新啟動 BruV AI。'
    })
    app.quit()
    return false
  }
}

/**
 * Step 3: 執行 docker compose up -d 啟動所有容器服務。
 * @returns {Promise<boolean>}
 */
async function startDockerServices () {
  updateLoadingStatus('正在啟動容器服務...')
  ensureEnvFile()
  try {
    await new Promise((resolve, reject) => {
      exec(
        `docker compose -f "${composePath}" --env-file "${envPath}" up -d`,
        { timeout: 120000 },
        (err) => { if (err) reject(err); else resolve() }
      )
    })
    return true
  } catch (err) {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    await dialog.showMessageBox({
      type: 'error',
      buttons: ['確定'],
      title: 'BruV AI — 服務啟動失敗',
      message: '無法啟動容器服務',
      detail: String(err?.message ?? err).slice(0, 500)
    })
    app.quit()
    return false
  }
}

// ── 建立主視窗 ────────────────────────────────────────────────────────────────
function createMain () {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: 'BruV AI 知識庫',
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#f0f0f0', symbolColor: '#333', height: 38 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      // 允許 SSE / EventSource 對 localhost
      webSecurity: true
    }
  })

  mainWindow.loadURL(TARGET_URL)

  // 視窗準備好才顯示（避免白屏閃爍）
  mainWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close()
      splashWindow = null
    }
    mainWindow.show()
    mainWindow.focus()
  })

  // 外部連結用系統瀏覽器開啟
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith('http://localhost')) {
      shell.openExternal(url)
      return { action: 'deny' }
    }
    return { action: 'allow' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
    stopUpdateCheck()
  })

  // 移除原生選單列（改由前端 TitleBar 處理）
  Menu.setApplicationMenu(null)
  setupKeyboardShortcuts()
  setupContextMenu()
  setupIPC()

  // 記錄初始 bundle hash，並啟動自動更新偵測
  fetchBundleHash().then(hash => {
    currentBundleHash = hash
    startUpdateCheck()
  })
}

// ── IPC 橋接（供前端 TitleBar 呼叫）──────────────────────────────────────────
function setupIPC () {
  const { ipcMain } = require('electron')
  ipcMain.on('win-reload',       () => mainWindow?.webContents.reload())
  ipcMain.on('win-force-reload', () => mainWindow?.webContents.reloadIgnoringCache())
  ipcMain.on('win-devtools',     () => mainWindow?.webContents.toggleDevTools())
  ipcMain.on('win-minimize',     () => mainWindow?.minimize())
  ipcMain.on('win-maximize',     () => mainWindow?.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize())
  ipcMain.on('win-quit',         () => app.quit())

  // ── Token 持久化（safeStorage）──
  const tokenFilePath = () => path.join(app.getPath('userData'), 'token.enc')

  ipcMain.handle('auth:save-token', (_, token) => {
    try {
      if (!safeStorage.isEncryptionAvailable()) {
        return { success: false, error: 'safeStorage 不可用' }
      }
      const encrypted = safeStorage.encryptString(String(token || ''))
      fs.writeFileSync(tokenFilePath(), encrypted)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.message }
    }
  })

  ipcMain.handle('auth:load-token', () => {
    try {
      const fp = tokenFilePath()
      if (!fs.existsSync(fp)) return { success: false }
      if (!safeStorage.isEncryptionAvailable()) return { success: false }
      const buf = fs.readFileSync(fp)
      const token = safeStorage.decryptString(buf)
      return { success: true, token }
    } catch (err) {
      return { success: false, error: err.message }
    }
  })

  ipcMain.handle('auth:clear-token', () => {
    try {
      const fp = tokenFilePath()
      if (fs.existsSync(fp)) fs.unlinkSync(fp)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.message }
    }
  })
}

// ── 右鍵選單（原生實作）─────────────────────────────────────────────────────
function setupContextMenu () {
  if (!mainWindow) return
  mainWindow.webContents.on('context-menu', (event, params) => {
    const menu = new Menu()
    const wc = mainWindow.webContents

    // 連結相關
    if (params.linkURL) {
      menu.append(new MenuItem({
        label: '在瀏覽器中開啟連結',
        click: () => shell.openExternal(params.linkURL)
      }))
      menu.append(new MenuItem({
        label: '複製連結位址',
        click: () => clipboard.writeText(params.linkURL)
      }))
      menu.append(new MenuItem({ type: 'separator' }))
    }

    // 圖片相關
    if (params.hasImageContents && params.srcURL) {
      menu.append(new MenuItem({
        label: '複製圖片',
        click: () => wc.copyImageAt(params.x, params.y)
      }))
      menu.append(new MenuItem({
        label: '複製圖片網址',
        click: () => clipboard.writeText(params.srcURL)
      }))
      menu.append(new MenuItem({
        label: '圖片另存為…',
        click: () => wc.downloadURL(params.srcURL)
      }))
      menu.append(new MenuItem({ type: 'separator' }))
    }

    // 拼字建議
    if (params.misspelledWord && params.dictionarySuggestions?.length) {
      for (const suggestion of params.dictionarySuggestions.slice(0, 5)) {
        menu.append(new MenuItem({
          label: suggestion,
          click: () => wc.replaceMisspelling(suggestion)
        }))
      }
      menu.append(new MenuItem({ type: 'separator' }))
    }

    // 編輯操作
    if (params.editFlags.canCut && params.selectionText) {
      menu.append(new MenuItem({ label: '剪下', role: 'cut' }))
    }
    if (params.editFlags.canCopy && params.selectionText) {
      menu.append(new MenuItem({ label: '複製', role: 'copy' }))
    }
    if (params.editFlags.canPaste) {
      menu.append(new MenuItem({ label: '貼上', role: 'paste' }))
      menu.append(new MenuItem({ label: '貼上為純文字', role: 'pasteAndMatchStyle' }))
    }
    if (params.editFlags.canSelectAll) {
      menu.append(new MenuItem({ label: '全選', role: 'selectAll' }))
    }

    if (menu.items.length > 0) {
      menu.popup({ window: mainWindow })
    }
  })
}

// ── 鍵盤快捷鍵（在 webContents 層攔截，不需可見選單）────────────────────────
function setupKeyboardShortcuts () {
  if (!mainWindow) return
  mainWindow.webContents.on('before-input-event', (event, input) => {
    // F5 → 一般重載
    if (input.type === 'keyDown' && input.key === 'F5') {
      mainWindow.webContents.reload()
      event.preventDefault()
    }
    // Ctrl+R → 一般重載
    if (input.type === 'keyDown' && input.key === 'r' && input.control) {
      mainWindow.webContents.reload()
      event.preventDefault()
    }
  })
}

// ── 自動偵測前端更新（比對 bundle hash）──────────────────────────────────────
function fetchBundleHash () {
  return new Promise((resolve) => {
    http.get(TARGET_URL, (res) => {
      let body = ''
      res.on('data', chunk => { body += chunk })
      res.on('end', () => {
        // 從 index.html 取出 /assets/index-*.js 的 hash 片段
        const match = body.match(/\/assets\/(index-[^"']+\.js)/)
        resolve(match ? match[1] : null)
      })
    }).on('error', () => resolve(null))
  })
}

function startUpdateCheck () {
  stopUpdateCheck()
  updateCheckTimer = setInterval(async () => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    const newHash = await fetchBundleHash()
    if (newHash && currentBundleHash && newHash !== currentBundleHash) {
      currentBundleHash = newHash
      const { response } = await dialog.showMessageBox(mainWindow, {
        type: 'info',
        buttons: ['立即更新', '稍後'],
        defaultId: 0,
        title: '前端有新版本',
        message: '偵測到前端已更新，是否立即重新整理？'
      })
      if (response === 0) {
        mainWindow.webContents.reloadIgnoringCache()
      }
    }
  }, UPDATE_CHECK_INTERVAL_MS)
}

function stopUpdateCheck () {
  if (updateCheckTimer) {
    clearInterval(updateCheckTimer)
    updateCheckTimer = null
  }
}

// ── 輪詢後端 health ───────────────────────────────────────────────────────────
async function waitForBackend (retries = 0) {
  if (retries === 0) updateLoadingStatus('正在等待後端服務啟動...')
  try {
    await new Promise((resolve, reject) => {
      http.get(BACKEND_HEALTH_URL, (res) => {
        if (res.statusCode === 200) resolve()
        else reject(new Error(`Status ${res.statusCode}`))
        res.resume() // 消費 response body
      }).on('error', reject)
    })
    // 後端正常 → 關閉 splash，開主視窗
    createMain()
  } catch {
    if (retries >= MAX_RETRIES) {
      // 超時仍嘗試開啟（可能後端很慢）
      createMain()
      return
    }
    setTimeout(() => waitForBackend(retries + 1), RETRY_INTERVAL_MS)
  }
}

// ── Setup Wizard ──────────────────────────────────────────────────────────────
function createSetupWizard () {
  setupWizardWindow = new BrowserWindow({
    width: 800,
    height: 600,
    resizable: false,
    frame: true,
    title: 'BruV AI — 初始設定',
    webPreferences: {
      preload: path.join(__dirname, 'setup-preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    }
  })
  setupWizardWindow.loadFile(path.join(__dirname, 'setup-wizard.html'))
  Menu.setApplicationMenu(null)

  setupWizardWindow.on('closed', () => {
    setupWizardWindow = null
  })
}

/**
 * 讀取 .env 檔案，更新指定 key，寫回。
 * 不存在的 key 會新增在末尾。
 */
function updateEnvFile (envPath, updates) {
  let lines = []
  try {
    lines = fs.readFileSync(envPath, 'utf8').split('\n')
  } catch { /* 檔案不存在，從空白開始 */ }

  const keyMap = new Map()
  const order  = []
  for (const line of lines) {
    const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/)
    if (m) {
      keyMap.set(m[1], m[2])
      order.push(m[1])
    } else {
      order.push(null) // 保留空行、註解
    }
  }

  // 套用更新
  for (const [k, v] of Object.entries(updates)) {
    if (v === undefined || v === null) continue
    if (!keyMap.has(k)) order.push(k)
    keyMap.set(k, String(v))
  }

  const out = order.map(k => {
    if (k === null) return ''      // 空行/註解（簡化：以空行替代）
    return `${k}=${keyMap.get(k)}`
  }).join('\n')
  fs.writeFileSync(envPath, out, 'utf8')
}

/**
 * 注冊 Setup Wizard 專用的 IPC handlers。
 * 必須在 app.whenReady() 之後呼叫。
 */
function setupSetupIPC (setupCompleteFile) {
  // ── Step 2: 檢測 Docker 是否安裝 ──
  ipcMain.handle('setup:checkDocker', async () => {
    try {
      const out = await runCommand('docker --version', 8000)
      return { installed: true, version: out.trim() }
    } catch {
      return { installed: false }
    }
  })

  // ── Step 3: 檢測 Docker daemon 是否運行 ──
  ipcMain.handle('setup:checkDockerRunning', async () => {
    try {
      await runCommand('docker info', 10000)
      return { running: true }
    } catch {
      return { running: false }
    }
  })

  // ── Step 3: 啟動 Docker Desktop 並輪詢等待 ──
  ipcMain.handle('setup:startDockerDesktop', async (event) => {
    try {
      if (process.platform === 'win32') {
        exec('start "" "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe"')
      } else if (process.platform === 'darwin') {
        exec('open -a Docker')
      } else {
        exec('systemctl --user start docker-desktop')
      }
    } catch { /* 忽略啟動錯誤，持續輪詢 */ }

    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 3000))
      try {
        await runCommand('docker info', 8000)
        if (!event.sender.isDestroyed()) {
          event.sender.send('setup:dockerProgress', 'Docker 已就緒')
        }
        return { success: true }
      } catch {
        if (!event.sender.isDestroyed()) {
          event.sender.send('setup:dockerProgress',
            `正在等待 Docker 啟動... (${(i + 1) * 3}s / 60s)`)
        }
      }
    }
    return { success: false, error: 'Docker 無法在 60 秒內啟動，請手動開啟 Docker Desktop 後重試。' }
  })

  // ── Step 4: 檢測 Ollama 是否安裝 ──
  ipcMain.handle('setup:checkOllama', async () => {
    try {
      const out = await runCommand('ollama --version', 8000)
      return { installed: true, version: out.trim() }
    } catch {
      return { installed: false }
    }
  })

  // ── Step 4: 下載 Ollama 模型（流式進度） ──
  ipcMain.handle('setup:pullOllamaModel', (event, modelName) => {
    return new Promise((resolve) => {
      const child = spawn('ollama', ['pull', modelName], {
        stdio: ['ignore', 'pipe', 'pipe']
      })
      let currentPercent = 0

      const handleData = (data) => {
        if (event.sender.isDestroyed()) return
        // 移除 ANSI 色碼、Carriage Return
        const text = data.toString()
          .replace(/\x1B\[[0-9;]*m/g, '')
          .replace(/\r/g, '\n')
        const lines = text.split('\n').filter(l => l.trim())

        for (const line of lines) {
          const pctMatch = line.match(/(\d+)%/)
          if (pctMatch) currentPercent = parseInt(pctMatch[1])
          const isDone = line.trim().toLowerCase() === 'success'
          event.sender.send('setup:ollamaProgress', {
            model: modelName,
            line: line.trim(),
            percent: pctMatch ? currentPercent : null,
            done: isDone
          })
        }
      }

      child.stdout.on('data', handleData)
      child.stderr.on('data', handleData)

      child.on('close', (code) => {
        resolve({ success: code === 0 })
      })
      child.on('error', (err) => {
        resolve({ success: false, error: err.message })
      })
    })
  })

  // ── Step 5: 儲存環境變數設定 ──
  ipcMain.handle('setup:saveEnvSettings', async (_, settings) => {
    ensureEnvFile()
    const updates = {}
    if (settings.anthropicApiKey !== undefined) updates.ANTHROPIC_API_KEY = settings.anthropicApiKey
    if (settings.openaiApiKey   !== undefined) updates.OPENAI_API_KEY     = settings.openaiApiKey
    if (settings.groqApiKey     !== undefined) updates.GROQ_API_KEY       = settings.groqApiKey

    try {
      updateEnvFile(envPath, updates)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.message }
    }
  })

  // ── Step 6: 啟動容器服務 ──
  ipcMain.handle('setup:startServices', async () => {
    ensureEnvFile()
    try {
      await new Promise((resolve, reject) => {
        exec(
          `docker compose -f "${composePath}" --env-file "${envPath}" up -d`,
          { timeout: 120000 },
          (err) => { if (err) reject(err); else resolve() }
        )
      })
      return { success: true }
    } catch (err) {
      return { success: false, error: String(err?.message ?? err).slice(0, 300) }
    }
  })

  // ── Step 6: 輪詢後端 health（最多 90 秒） ──
  ipcMain.handle('setup:waitForBackend', async (event) => {
    for (let i = 0; i < 45; i++) {
      await new Promise(r => setTimeout(r, 2000))
      try {
        const ok = await new Promise((resolve, reject) => {
          http.get(BACKEND_HEALTH_URL, (res) => {
            if (res.statusCode === 200) resolve(true)
            else reject(new Error(`HTTP ${res.statusCode}`))
            res.resume()
          }).on('error', reject)
        })
        if (ok) return { success: true }
      } catch {
        if (!event.sender.isDestroyed()) {
          event.sender.send('setup:backendProgress',
            `等待後端回應... (${(i + 1) * 2}s / 90s)`)
        }
      }
    }
    return { success: false, error: '後端服務無法在 90 秒內啟動' }
  })

  // ── 初始化管理員帳號（呼叫後端 API）──
  ipcMain.handle('setup:initAdmin', async (_, { email, password }) => {
    return await new Promise((resolve) => {
      const data = JSON.stringify({ email, password })
      const req = http.request({
        hostname: 'localhost',
        port: 80,
        path: '/api/auth/init-admin',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data)
        },
        timeout: 15000,
      }, (res) => {
        let body = ''
        res.on('data', chunk => { body += chunk })
        res.on('end', () => {
          if (res.statusCode === 200) {
            try { resolve({ success: true, ...JSON.parse(body) }) }
            catch { resolve({ success: true }) }
          } else {
            let detail = body
            try { detail = JSON.parse(body).detail || body } catch {}
            resolve({ success: false, status: res.statusCode, error: detail })
          }
        })
      })
      req.on('error', err => resolve({ success: false, error: err.message }))
      req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '請求逾時' }) })
      req.write(data)
      req.end()
    })
  })

  // ── Step 6: 完成設定，寫入標記，開啟主視窗 ──
  ipcMain.handle('setup:completeSetup', async () => {
    try {
      fs.writeFileSync(
        setupCompleteFile,
        JSON.stringify({ completedAt: new Date().toISOString() }),
        'utf8'
      )
    } catch (err) {
      return { success: false, error: err.message }
    }

    // 開啟主視窗（後端此時應已就緒）
    createMain()

    // 稍後關閉精靈視窗（讓主視窗先出現）
    setTimeout(() => {
      if (setupWizardWindow && !setupWizardWindow.isDestroyed()) {
        setupWizardWindow.close()
        setupWizardWindow = null
      }
    }, 800)

    return { success: true }
  })

  // ── 通用：開啟外部連結 ──
  ipcMain.handle('setup:openExternal', (_, url) => {
    shell.openExternal(url)
  })
}

// ── App 生命週期 ──────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  const setupCompleteFile = path.join(app.getPath('userData'), 'setup-complete.json')

  // 注冊 setup IPC handlers（精靈視窗需要）
  setupSetupIPC(setupCompleteFile)

  const setupComplete = fs.existsSync(setupCompleteFile)

  if (!setupComplete) {
    // 首次執行：開啟設定精靈
    createSetupWizard()
  } else {
    // 已設定完成：走正常啟動流程
    createSplash()
    splashWindow.webContents.once('did-finish-load', async () => {
      if (!await checkDocker()) return
      if (!await ensureDockerRunning()) return
      if (!await startDockerServices()) return
      waitForBackend()
    })
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      if (!fs.existsSync(setupCompleteFile)) {
        createSetupWizard()
      } else {
        createSplash()
        waitForBackend()
      }
    }
  })
})

app.on('window-all-closed', async () => {
  if (process.platform === 'darwin') return

  const { response } = await dialog.showMessageBox({
    type: 'question',
    buttons: ['停止服務並退出', '僅關閉視窗'],
    defaultId: 0,
    title: 'BruV AI',
    message: '是否同時停止後台服務？',
    detail: '停止服務將關閉所有 Docker 容器，下次啟動需要重新等待服務啟動。'
  })
  if (response === 0) {
    exec(`docker compose -f "${composePath}" --env-file "${envPath}" down`)
  }
  app.quit()
})

// 禁止導航到非 localhost 頁面（安全防護）
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost')) {
      event.preventDefault()
    }
  })
})
