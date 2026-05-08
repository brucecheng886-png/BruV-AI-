const { app, BrowserWindow, shell, ipcMain, globalShortcut, Menu, MenuItem, Tray, nativeImage, clipboard, dialog, net, safeStorage } = require('electron')
const path = require('path')
const https = require('https')
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')
const { exec, spawn } = require('child_process')
const { autoUpdater } = require('electron-updater')

autoUpdater.autoDownload = false
autoUpdater.autoInstallOnAppQuit = false

const TARGET_URL = 'http://localhost:80'
const BACKEND_HEALTH_URL = 'http://localhost:80/api/health'
const RETRY_INTERVAL_MS = 2000
const MAX_RETRIES = 90 // 最多等 180 秒
const UPDATE_CHECK_INTERVAL_MS = 60 * 1000 // 每 60 秒檢查前端是否有新版本

let mainWindow = null
let splashWindow = null
let setupWizardWindow = null
let tray = null
let currentBundleHash = null // 記錄目前載入的前端 bundle hash
let updateCheckTimer = null

// docker-compose.yml 路徑（打包後從 extraResources，開發時從專案根目錄）
const resourcePath = app.isPackaged
  ? process.resourcesPath
  : path.join(__dirname, '..')
const composePath = path.join(resourcePath, 'docker-compose.yml')
const COMPOSE_PROJECT = 'bruv-ai'
// .env 放在 userData（%APPDATA%\BruV AI\.env），確保 installer 升級時不會被覆蓋
// 開發模式下沿用專案根目錄的 .env，方便調試
const envPath = app.isPackaged
  ? path.join(app.getPath('userData'), '.env')
  : path.join(resourcePath, '.env')
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
  let freshlyCreated = false
  try {
    // 確保 envPath 的目錄存在（userData 在打包模式下可能還沒建）
    const envDir = path.dirname(envPath)
    if (!fs.existsSync(envDir)) fs.mkdirSync(envDir, { recursive: true })
    if (!fs.existsSync(envPath)) {
      freshlyCreated = true
      const resourcesEnvPath = path.join(resourcePath, '.env')
      if (fs.existsSync(envExamplePath)) {
        fs.copyFileSync(envExamplePath, envPath)
      } else if (resourcesEnvPath !== envPath && fs.existsSync(resourcesEnvPath)) {
        // 以 extraResources 放置的 resources/.env 作為初始範本
        fs.copyFileSync(resourcesEnvPath, envPath)
      } else {
        // 無範本可複製，建立空白檔；missingTemplate=true 讓呼叫者顯示警告
        fs.writeFileSync(envPath, '', 'utf8')
        return { freshlyCreated: true, missingTemplate: true }
      }
    }
    // 隨機化佔位符（幂等：已被替換的欄位不會重生）
    randomizeEnvPlaceholders(envPath)
    // 將 userData/.env 同步到 resources/.env，確保 docker-compose env_file: .env
    // 讀到的是已隨機化的密碼（而非 resources 裡打包的原始 template）
    try {
      const resourcesEnvDest = path.join(resourcePath, '.env')
      if (app.isPackaged && resourcesEnvDest !== envPath) {
        fs.copyFileSync(envPath, resourcesEnvDest)
      }
    } catch (copyErr) {
      console.warn('[ensureEnvFile] 無法同步 .env 到 resources：', copyErr.message)
    }
  } catch (err) {
    console.error('[ensureEnvFile] 失敗：', err)
  }
  return { freshlyCreated, missingTemplate: false }
}

// ── .env 全新建立時，必須清除舊有 stateful volume，避免密碼不符 ───────────
// PostgreSQL/Redis 等 volume 會保留首次初始化的密碼，若 .env 重建為新密碼
// 但 volume 仍是舊密碼，backend 會認證失敗 (InvalidPasswordError)。
// 用 compose down -v 只清本專案的 volume，不會誤傷其他 compose 專案。
function purgeStatefulVolumes () {
  return new Promise((resolve) => {
    const cmd = `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}" --env-file "${envPath}" down -v --remove-orphans`
    exec(cmd, { timeout: 120000 }, () => resolve())
  })
}

// ── 偵測關鍵 Port 是否已被非 Docker 程序佔用 ────────────────────────────────
const REQUIRED_PORTS = [
  { port: 80,    name: 'Nginx (前端 proxy)' },
  { port: 8000,  name: 'Backend API' },
  { port: 5432,  name: 'PostgreSQL' },
  { port: 6333,  name: 'Qdrant' },
  { port: 6379,  name: 'Redis' },
  { port: 7474,  name: 'Neo4j HTTP' },
  { port: 7687,  name: 'Neo4j Bolt' },
  { port: 11434, name: 'Ollama' },
]
function checkPortFree (port) {
  return new Promise((resolve) => {
    const srv = require('net').createServer()
    srv.once('error', () => resolve(false))
    srv.once('listening', () => { srv.close(); resolve(true) })
    srv.listen(port, '127.0.0.1')
  })
}
async function checkRequiredPorts () {
  const busy = []
  for (const { port, name } of REQUIRED_PORTS) {
    const free = await checkPortFree(port)
    if (!free) busy.push(`  • Port ${port}  (${name})`)
  }
  return busy
}

// ── 確認 docker-compose 所需的資料目錄與檔案 bind-mount 來源存在 ──────────
// 必須在 docker compose up 之前預建為「空檔案」。
function ensureDataDirs () {
  try {
    const dataDir   = path.join(resourcePath, 'data')
    const subDirs   = ['uploads', 'screenshots']
    const fileMounts = ['saga.db']
    if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true })
    for (const d of subDirs) {
      const p = path.join(dataDir, d)
      if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true })
    }
    for (const f of fileMounts) {
      const p = path.join(dataDir, f)
      if (!fs.existsSync(p)) fs.writeFileSync(p, '', 'utf8')
      else if (fs.statSync(p).isDirectory()) {
        // Docker 已誤建為資料夾，移除並重建為空檔
        fs.rmSync(p, { recursive: true, force: true })
        fs.writeFileSync(p, '', 'utf8')
      }
    }
  } catch (err) {
    console.error('[ensureDataDirs] 失敗：', err)
  }
}

// ── 偵測 NVIDIA GPU；無 GPU 時產生 compose gpu-override 移除 ollama GPU 依賴 ──
// 寫入 userData 確保有寫入權限（packaged 版 resourcesPath 可能在 Program Files）
function getGpuOverridePath () {
  return path.join(app.getPath('userData'), 'docker-compose.gpu-override.yml')
}
async function ensureGpuOverride () {
  const gpuOverridePath = getGpuOverridePath()
  let hasGpu = false
  try {
    await runCommand('nvidia-smi -L', 5000)
    hasGpu = true
  } catch { hasGpu = false }

  if (!hasGpu) {
    // 無 GPU：確保不殘留舊的 GPU override
    if (fs.existsSync(gpuOverridePath)) {
      try { fs.unlinkSync(gpuOverridePath) } catch {}
    }
    return null
  }

  // 有 GPU：寫入 override 啟用 nvidia GPU（base compose 預設 CPU）
  const overrideYaml = [
    'services:',
    '  ollama:',
    '    environment:',
    '      - OLLAMA_NUM_GPU=${OLLAMA_NUM_GPU:-999}',
    '    deploy:',
    '      resources:',
    '        reservations:',
    '          devices:',
    '            - driver: nvidia',
    '              count: all',
    '              capabilities: [gpu]',
    ''
  ].join('\n')
  try {
    fs.mkdirSync(path.dirname(gpuOverridePath), { recursive: true })
    fs.writeFileSync(gpuOverridePath, overrideYaml, 'utf8')
    return gpuOverridePath
  } catch (err) {
    console.error('[ensureGpuOverride] 失敗：', err)
    return null
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

  // Splash 規控 IPC
  ipcMain.on('splash:minimize', () => { if (splashWindow && !splashWindow.isDestroyed()) splashWindow.minimize() })
  ipcMain.on('splash:close',    () => app.quit())
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
      shell.openExternal('https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe?utm_source=docker&utm_medium=webreferral&utm_campaign=dd-smartbutton&utm_location=module&_gl=1*1e17a7q*_gcl_au*ODIxNTI0NS4xNzc3NjQ0NDEw*_ga*MjEwNzEyMDc2MS4xNzc3NjQ0NDEw*_ga_XJWPQMJYHQ*czE3Nzc3MDM5NjckbzMkZzEkdDE3Nzc3MDM5NzIkajU1JGwwJGgw')
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
  const { missingTemplate } = ensureEnvFile()
  if (missingTemplate) {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      title: 'BruV AI — 設定不完整',
      message: '找不到 .env.example 範本檔案',
      detail: '安裝可能不完整，docker 服務可能無法正常啟動。建議重新安裝。\n\n是否仍要繼續？',
      buttons: ['繼續', '取消'],
      defaultId: 0,
      cancelId: 1
    })
    if (response === 1) { app.quit(); return false }
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.show()
  }
  ensureDataDirs()

  // Port 衝突預檢：若有非 Docker 程序佔用關鍵 port，提早告知使用者
  const busyPorts = await checkRequiredPorts()
  if (busyPorts.length > 0) {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    const { response: portResp } = await dialog.showMessageBox({
      type: 'warning',
      title: 'BruV AI — Port 衝突偵測',
      message: '以下 Port 已被其他程序佔用',
      detail: busyPorts.join('\n') + '\n\n請關閉衝突程序後再啟動 BruV AI，否則部分服務可能無法正常運作。\n\n是否仍要繼續？',
      buttons: ['繼續', '取消'],
      defaultId: 1,
      cancelId: 1
    })
    if (portResp === 1) { app.quit(); return false }
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.show()
  }

  const gpuOverridePath = await ensureGpuOverride()
  const overrideFlag = gpuOverridePath ? ` -f "${gpuOverridePath}"` : ''
  const upCmd = `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}"${overrideFlag} --env-file "${envPath}" up -d --remove-orphans`
  const downCmd = `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}"${overrideFlag} --env-file "${envPath}" down --remove-orphans`
  const runUp = () => new Promise((resolve, reject) => {
    exec(upCmd, { timeout: 1800000, maxBuffer: 64 * 1024 * 1024 },
      (err, _stdout, stderr) => {
        if (err) { err.stderr = stderr || ''; reject(err) } else resolve()
      })
  })
  try {
    try {
      await runUp()
    } catch (err) {
      const msg = (err.stderr || err.message || '').toString()
      if (/is already in use by container|Conflict\.|name .* is already in use|was not created for project/i.test(msg)) {
        // 強制清除所有 bruv_ai_* 容器（不論 project name），解決跨版本 project name 遷移衝突
        await new Promise((resolve) => exec(downCmd, { timeout: 120000 }, () => resolve()))
        await new Promise((resolve) => {
          exec(
            `powershell -NoProfile -Command "& { $ids = docker ps -aq --filter name=bruv_ai_; if ($ids) { $ids | ForEach-Object { docker rm -f $_ } } }"`,
            { timeout: 60000 }, () => resolve()
          )
        })
        // 移除殘留的 bruv_ai_network（可能屬於其他 project）
        await new Promise((resolve) => exec('docker network rm bruv_ai_network', { timeout: 15000 }, () => resolve()))
        await runUp()
      } else if (/dependency failed to start|is unhealthy/i.test(msg)) {
        // postgres / 其他服務 healthcheck 超時導致依賴服務啟動失敗
        // 等 20 秒讓 postgres 完全就緒後再執行一次 up（重啟 Error 狀態的容器）
        updateLoadingStatus('資料庫啟動中，自動重試...')
        await new Promise((resolve) => setTimeout(resolve, 20000))
        await runUp()
      } else {
        throw err
      }
    }
    return true
  } catch (err) {
    if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
    await dialog.showMessageBox({
      type: 'error',
      buttons: ['確定'],
      title: 'BruV AI — 服務啟動失敗',
      message: '無法啟動容器服務',
      detail: String(err?.message ?? err).slice(0, 1500)
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
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      // 允許 SSE / EventSource 對 localhost
      webSecurity: true
    }
  })

  // 每次啟動清除 HTTP cache，確保載入最新前端 bundle
  mainWindow.webContents.session.clearCache().then(() => {
    mainWindow.loadURL(TARGET_URL)
  })

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

  // close 事件：攔截並詢問使用者（或套用已記住的偏好）
  mainWindow.on('close', async (e) => {
    e.preventDefault()
    const prefPath = path.join(app.getPath('userData'), 'close-preference.json')
    let savedPref = null
    try {
      if (fs.existsSync(prefPath)) {
        savedPref = JSON.parse(fs.readFileSync(prefPath, 'utf8')).preference
      }
    } catch { savedPref = null }

    if (savedPref === 'minimize') {
      mainWindow.hide()
      return
    }
    if (savedPref === 'quit') {
      await stopDockerAndQuit()
      return
    }
    if (savedPref === 'quit-only') {
      app.exit(0)
      return
    }

    // 無記住的偏好 → 顯示對話框
    const { response, checkboxChecked } = await dialog.showMessageBox(mainWindow, {
      type: 'question',
      buttons: ['收到系統匣', '直接退出', '停止服務並退出', '取消'],
      defaultId: 0,
      cancelId: 3,
      title: 'BruV AI',
      message: '關閉 BruV AI',
      detail: '收到系統匣：服務繼續運行，下次開啟更快\n直接退出：關閉應用程式，服務繼續在背景運行\n停止服務並退出：關閉所有容器，釋放記憶體',
      checkboxLabel: '記住我的選擇，不再詢問',
      checkboxChecked: false
    })

    if (response === 0) {
      if (checkboxChecked) {
        try {
          fs.mkdirSync(path.dirname(prefPath), { recursive: true })
          fs.writeFileSync(prefPath, JSON.stringify({ preference: 'minimize' }), 'utf8')
        } catch {}
      }
      mainWindow.hide()
    } else if (response === 1) {
      if (checkboxChecked) {
        try {
          fs.mkdirSync(path.dirname(prefPath), { recursive: true })
          fs.writeFileSync(prefPath, JSON.stringify({ preference: 'quit-only' }), 'utf8')
        } catch {}
      }
      app.exit(0)
    } else if (response === 2) {
      if (checkboxChecked) {
        try {
          fs.mkdirSync(path.dirname(prefPath), { recursive: true })
          fs.writeFileSync(prefPath, JSON.stringify({ preference: 'quit' }), 'utf8')
        } catch {}
      }
      await stopDockerAndQuit()
    }
    // response === 3 取消：不做任何事
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

  createTray()
}

// ── 停止 Docker 服務後退出 ───────────────────────────────────────────────────
async function stopDockerAndQuit () {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide()
  try {
    await Promise.race([
      new Promise((resolve) => {
        exec(`docker compose -p ${COMPOSE_PROJECT} -f "${composePath}" --env-file "${envPath}" stop`,
          { timeout: 15000 }, () => resolve())
      }),
      new Promise((resolve) => setTimeout(resolve, 15000))
    ])
  } catch { /* ignore */ }
  tray?.destroy()
  tray = null
  app.exit(0)
}

// ── 系統匣 ────────────────────────────────────────────────────────────────────
function createTray () {
  if (tray && !tray.isDestroyed()) return
  const icoPath = path.join(__dirname, 'assets', 'icon.ico')
  const icon = fs.existsSync(icoPath)
    ? nativeImage.createFromPath(icoPath)
    : nativeImage.createEmpty()
  tray = new Tray(icon.resize({ width: 16, height: 16 }))
  tray.setToolTip('BruV AI 知識庫')

  const buildMenu = () => Menu.buildFromTemplate([
    {
      label: '開啟 BruV AI',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        }
      }
    },
    { type: 'separator' },
    {
      label: '停止服務並退出',
      click: () => stopDockerAndQuit()
    }
  ])

  tray.setContextMenu(buildMenu())

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.focus()
      } else {
        mainWindow.show()
        mainWindow.focus()
      }
    }
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
  ipcMain.on('relaunch-for-update', () => {
    try { fs.writeFileSync(path.join(app.getPath('appData'), 'bruv-ai-kb', 'auto-update.flag'), '1') } catch {}
    spawnUpdateBridge()  // 先啟動橋接視窗，Electron 退出後仍顯示「正在更新」
    autoUpdater.quitAndInstall(true, true)
  })
  // ── 手動更新 IPC ──
  ipcMain.handle('updater:check', async () => {
    try {
      const result = await autoUpdater.checkForUpdates()
      return { hasUpdate: !!result?.updateInfo?.version && result.updateInfo.version !== app.getVersion(), version: result?.updateInfo?.version }
    } catch (err) {
      return { hasUpdate: false, error: err?.message || String(err) }
    }
  })
  ipcMain.handle('updater:download', async () => {
    try {
      await autoUpdater.downloadUpdate()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err?.message || String(err) }
    }
  })
  ipcMain.on('updater:install', () => {
    try { fs.writeFileSync(path.join(app.getPath('appData'), 'bruv-ai-kb', 'auto-update.flag'), '1') } catch {}
    spawnUpdateBridge()
    autoUpdater.quitAndInstall(true, true)
  })
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

  // ── 關閉偏好 ──
  const closePrefPath = () => path.join(app.getPath('userData'), 'close-preference.json')

  ipcMain.handle('app:get-close-preference', () => {
    try {
      const fp = closePrefPath()
      if (!fs.existsSync(fp)) return { preference: null }
      return JSON.parse(fs.readFileSync(fp, 'utf8'))
    } catch {
      return { preference: null }
    }
  })

  ipcMain.handle('app:reset-close-preference', () => {
    try {
      const fp = closePrefPath()
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
    // F12 → DevTools
    if (input.type === 'keyDown' && input.key === 'F12') {
      mainWindow.webContents.toggleDevTools()
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
      updateLoadingStatus('後端啟動逾時，正在收集錯誤資訊...')
      let logs = ''
      try {
        logs = await runCommand(
          `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}" --env-file "${envPath}" logs --tail=20 --no-color`,
          15000
        )
      } catch (e) {
        logs = '（無法取得容器 log：' + (e?.message || String(e)) + '）'
      }
      if (splashWindow && !splashWindow.isDestroyed()) splashWindow.hide()
      const { response } = await dialog.showMessageBox({
        type: 'error',
        title: 'BruV AI — 後端啟動逾時',
        message: '後端服務 180 秒內未回應，可能仍在初始化中。',
        detail: '容器 Log（最後 20 行）：\n\n' + logs.slice(0, 1500),
        buttons: ['重試', '繼續開啟（可能無法使用）'],
        defaultId: 0
      })
      if (response === 0) {
        if (splashWindow && !splashWindow.isDestroyed()) {
          splashWindow.show()
        } else {
          createSplash()
          await new Promise(r => splashWindow.webContents.once('did-finish-load', r))
        }
        waitForBackend(0)
      } else {
        createMain()
      }
      return
    }
    setTimeout(() => waitForBackend(retries + 1), RETRY_INTERVAL_MS)
  }
}

// ── Setup Wizard ──────────────────────────────────────────────────────────────
function createSetupWizard () {
  setupWizardWindow = new BrowserWindow({
    width: 800,
    height: 820,
    minWidth: 800,
    minHeight: 820,
    resizable: true,
    frame: false,
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

  // 偵測 NVIDIA GPU（供 wizard Step 4 顯示 GPU 偏好選項）
  ipcMain.handle('setup:detectGpu', async () => {
    try {
      const out = await runCommand('nvidia-smi --query-gpu=name --format=csv,noheader', 5000)
      const name = out.trim().split('\n')[0].trim()
      return { hasGpu: true, name: name || 'NVIDIA GPU' }
    } catch {
      return { hasGpu: false }
    }
  })

  // ── Step 4: 列出已安裝的 Ollama 模型（供 wizard 判斷是否跳過 pull）──
  ipcMain.handle('setup:listOllamaModels', async () => {
    try {
      const out = await runCommand('ollama list', 8000)
      // 輸出格式：NAME  ID  SIZE  MODIFIED
      const lines = out.split(/\r?\n/).slice(1)
      const models = lines
        .map(l => l.trim().split(/\s+/)[0])
        .filter(name => name && name !== 'NAME')
      return { success: true, models }
    } catch (err) {
      return { success: false, models: [], error: String(err?.message ?? err) }
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
    if (settings.ollamaNumGpu   !== undefined) updates.OLLAMA_NUM_GPU     = settings.ollamaNumGpu

    try {
      updateEnvFile(envPath, updates)
      return { success: true }
    } catch (err) {
      return { success: false, error: err.message }
    }
  })

  // ── Step 6: 啟動容器服務 ──
  ipcMain.handle('setup:startServices', async (event) => {
    const { missingTemplate } = ensureEnvFile()
    if (missingTemplate) {
      return { success: false, error: '找不到 .env.example，安裝可能不完整。請重新安裝 BruV AI。' }
    }
    ensureDataDirs()
    const gpuOverridePath = await ensureGpuOverride()
    const overrideFlag = gpuOverridePath ? ` -f "${gpuOverridePath}"` : ''

    const upCmd = `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}"${overrideFlag} --env-file "${envPath}" up -d --pull always --remove-orphans`
    const downCmd = `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}"${overrideFlag} --env-file "${envPath}" down --remove-orphans`
    const rmConflictCmd = `docker ps -aq --filter name=^bruv_ai_`

    // 首次/重試都先強制清除殘留同名容器（任何 bruv_ai_* 都刪除）
    await new Promise((resolve) => {
      exec(downCmd, { timeout: 120000 }, () => resolve())
    })
    // 保險上：連同非 compose 產生的 bruv_ai_* 也刪掉
    await new Promise((resolve) => {
      exec(
        `powershell -NoProfile -Command "& { $ids = (${rmConflictCmd}); if ($ids) { $ids | ForEach-Object { docker rm -f $_ } } }"`,
        { timeout: 60000 }, () => resolve()
      )
    })
    // ⚠️ Setup wizard 執行時，舊 volume 的密碼可能與當前 .env 不符（解除安裝/重裝導致），
    //    必須無條件清除舊 volume，確保 postgres 以當前 .env 密碼全新初始化。
    //    freshlyCreated 機制已不可靠（saveEnvSettings 也會呼叫 ensureEnvFile，
    //    導致 startServices 到達時 freshlyCreated 永遠是 false）。
    event.sender.send('setup:dockerLog', '正在清除舊資料庫 volume（確保密碼一致）...')
    await purgeStatefulVolumes()

    // 用 spawn 串流 stdout/stderr，即時傳給前端顯示
    const upArgs = ['compose', '-p', COMPOSE_PROJECT, '-f', composePath]
    if (gpuOverridePath) upArgs.push('-f', gpuOverridePath)
    upArgs.push('--env-file', envPath, 'up', '-d', '--pull', 'always', '--remove-orphans')

    const runUp = () => new Promise((resolve, reject) => {
      const child = spawn('docker', upArgs, { stdio: ['ignore', 'pipe', 'pipe'] })
      let logBuf = ''

      const handleData = (data) => {
        const lines = data.toString().split(/\r?\n/).filter(l => l.trim())
        for (const line of lines) {
          logBuf += line + '\n'
          if (!event.sender.isDestroyed()) {
            event.sender.send('setup:dockerLog', line)
          }
        }
      }
      child.stdout.on('data', handleData)
      child.stderr.on('data', handleData)

      const timeoutId = setTimeout(() => {
        child.kill()
        reject(new Error('docker compose up 超過 30 分鐘逾時'))
      }, 1800000)

      child.on('close', (code) => {
        clearTimeout(timeoutId)
        if (code === 0) resolve()
        else {
          const tail = logBuf.split(/\r?\n/).slice(-20).join(' | ')
          reject(new Error(tail.slice(0, 1500)))
        }
      })
      child.on('error', (err) => {
        clearTimeout(timeoutId)
        reject(err)
      })
    })

    try {
      await runUp()
      return { success: true }
    } catch (err) {
      const msg = String(err?.message ?? err)
      // postgres 首次初始化在慢速機器上可能短暫崩潰後重啟，導致 celery 依賴失敗
      // 等 30 秒讓 postgres 完全就緒後自動重試一次
      if (/dependency failed to start|is unhealthy/i.test(msg)) {
        if (!event.sender.isDestroyed()) {
          event.sender.send('setup:dockerLog', '資料庫啟動中，30 秒後自動重試...')
        }
        await new Promise((resolve) => setTimeout(resolve, 30000))
        try {
          await runUp()
          return { success: true }
        } catch (retryErr) {
          return { success: false, error: String(retryErr?.message ?? retryErr).slice(0, 1500) }
        }
      }
      return { success: false, error: msg.slice(0, 1500) }
    }
  })

  // ── Step 6: 輪詢後端 health（最多 300 秒） ──
  ipcMain.handle('setup:waitForBackend', async (event) => {
    for (let i = 0; i < 150; i++) {
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
            `等待後端回應... (${(i + 1) * 2}s / 300s)`)
        }
      }
    }
    let logs = ''
    try {
      logs = await runCommand(
        `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}" --env-file "${envPath}" logs --tail=30 --no-color`,
        15000
      )
    } catch (e) {
      logs = '（無法取得容器 log）'
    }
    return { success: false, error: '後端服務無法在 300 秒內啟動', logs: logs.slice(0, 2000) }
  })

  // ── 初始化管理員帳號（呼叫後端 API，最多重試 4 次，每次間隔 5 秒）──
  ipcMain.handle('setup:initAdmin', async (_, { email, password }) => {
    // 先確認後端的 DB 連線真正就緒（/api/health 不碰 DB，需要呼叫會真正查詢的 endpoint）
    // 用 /api/auth/me（無 token → 401，但 401 代表 DB 可連），最多等 60 秒
    const waitForDb = async () => {
      for (let i = 0; i < 12; i++) {
        await new Promise(r => setTimeout(r, 5000))
        try {
          const ok = await new Promise((resolve) => {
            http.get('http://localhost:80/api/health/services', (res) => {
              res.resume()
              resolve(res.statusCode === 200)
            }).on('error', () => resolve(false))
          })
          if (ok) return
        } catch {}
      }
    }
    await waitForDb()

    const tryOnce = () => new Promise((resolve) => {
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
            try { const j = JSON.parse(body); detail = j.detail || j.error || body } catch {}
            resolve({ success: false, status: res.statusCode, error: detail })
          }
        })
      })
      req.on('error', err => resolve({ success: false, error: err.message }))
      req.on('timeout', () => { req.destroy(); resolve({ success: false, error: '請求逾時' }) })
      req.write(data)
      req.end()
    })
    let lastResult = { success: false, error: 'init-admin 未執行' }
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt > 0) await new Promise(r => setTimeout(r, 5000))
      lastResult = await tryOnce()
      if (lastResult.success || lastResult.status === 403) return lastResult
      console.warn(`[setup:initAdmin] 第 ${attempt + 1} 次嘗試失敗：`, lastResult.error)
    }
    // 最終失敗時，自動抓取 backend container log 供診斷
    try {
      const logs = await runCommand(
        `docker compose -p ${COMPOSE_PROJECT} -f "${composePath}" --env-file "${envPath}" logs backend --tail=80 --no-color`,
        10000
      )
      lastResult.logs = logs.slice(0, 2000)
    } catch { /* 抓 log 失敗不影響主流程 */ }
    return lastResult
  })

  // ── Step 6: 完成設定，寫入標記，開啟主視窗 ──
  ipcMain.handle('setup:completeSetup', async () => {
    try {
      fs.mkdirSync(path.dirname(setupCompleteFile), { recursive: true })
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

  // ── 視窗控制 ──
  ipcMain.handle('setup:minimize',    () => { setupWizardWindow?.minimize() })
  ipcMain.handle('setup:maximize',    () => { setupWizardWindow?.isMaximized() ? setupWizardWindow.unmaximize() : setupWizardWindow.maximize() })
  ipcMain.handle('setup:closeWindow', () => { setupWizardWindow?.close() })
}

// ── App 生命週期 ──────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  const setupCompleteFile = path.join(app.getPath('userData'), 'setup-complete.json')

  // 注冊 setup IPC handlers（精靈視窗需要）
  setupSetupIPC(setupCompleteFile)

  // 開發模式（非 packaged）跳過設定精靈，假設容器已由 開發啟動.bat 啟動
  const isDev = !app.isPackaged
  const setupComplete = isDev || fs.existsSync(setupCompleteFile)

  if (!setupComplete) {
    // 首次執行：開啟設定精靈
    createSetupWizard()
  } else if (isDev) {
    // 開發模式：直接開啟主視窗，不啟動 Docker（容器應已由 .bat 啟動）
    createSplash()
    splashWindow.webContents.once('did-finish-load', () => {
      waitForBackend()
    })
  } else {
    // 已設定完成（packaged）：走正常啟動流程
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

  // ── 自動更新（僅在已安裝版生效）──
  if (app.isPackaged) {
    setupAutoUpdater()
  }
})

// window-all-closed：因為 close 事件已 preventDefault 並由 Tray 保持存活，
// 此事件僅在 mainWindow 尚未建立（setup wizard 階段）時可能觸發，不需處理。
app.on('window-all-closed', () => {
  // darwin 以外：Tray 存在時不退出
  if (process.platform !== 'darwin' && tray && !tray.isDestroyed()) return
  if (process.platform === 'darwin') return
  app.quit()
})

// ── 自動更新（electron-updater + GitHub Releases）─────────────────────────
// ── 更新橋接視窗：在 Electron 程序退出後仍保持可見，直到新版本啟動 ────────────
function spawnUpdateBridge () {
  if (process.platform !== 'win32') return
  // 使用 UTF-16LE base64 編碼傳遞腳本，避免引號/換行問題
  const script = [
    'Add-Type -AssemblyName System.Windows.Forms',
    'Add-Type -AssemblyName System.Drawing',
    '$f = New-Object System.Windows.Forms.Form',
    '$f.Text = "BruV AI"',
    '$f.Size = New-Object System.Drawing.Size(400, 130)',
    '$f.StartPosition = "CenterScreen"',
    '$f.FormBorderStyle = "FixedSingle"',
    '$f.MaximizeBox = $false',
    '$f.MinimizeBox = $false',
    '$f.TopMost = $true',
    '$f.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#f0f0f0")',
    '$lbl = New-Object System.Windows.Forms.Label',
    '$lbl.Text = "BruV AI 正在安裝更新，請稍候..."',
    '$lbl.Location = New-Object System.Drawing.Point(20, 25)',
    '$lbl.Size = New-Object System.Drawing.Size(360, 32)',
    '$lbl.Font = New-Object System.Drawing.Font("Microsoft JhengHei UI", 12)',
    '$sub = New-Object System.Windows.Forms.Label',
    '$sub.Text = "更新完成後應用程式將自動重新啟動"',
    '$sub.Location = New-Object System.Drawing.Point(20, 60)',
    '$sub.Size = New-Object System.Drawing.Size(360, 20)',
    '$sub.Font = New-Object System.Drawing.Font("Microsoft JhengHei UI", 9)',
    '$sub.ForeColor = [System.Drawing.Color]::FromArgb(120, 120, 120)',
    '$f.Controls.Add($lbl)',
    '$f.Controls.Add($sub)',
    '$f.Show()',
    '$t = Get-Date',
    'while ($true) {',
    '    [System.Windows.Forms.Application]::DoEvents()',
    '    Start-Sleep -Milliseconds 300',
    '    if (Get-Process -Name "BruV AI" -ErrorAction SilentlyContinue) { break }',
    '    if ((New-TimeSpan -Start $t).TotalSeconds -gt 180) { break }',
    '}',
    '$f.Close()'
  ].join('\n')

  // 編碼為 UTF-16LE base64（PowerShell -EncodedCommand 要求）
  const buf = Buffer.alloc(script.length * 2)
  for (let i = 0; i < script.length; i++) buf.writeUInt16LE(script.charCodeAt(i), i * 2)
  const encoded = buf.toString('base64')

  const proc = spawn('powershell.exe',
    ['-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
    { detached: true, stdio: 'ignore', windowsHide: true }
  )
  proc.unref()
}

function setupAutoUpdater () {
  // Private repo 需要 GH_TOKEN 才能取得 release 資訊
  const ghToken = process.env.GH_TOKEN
  if (ghToken) {
    autoUpdater.addAuthHeader(`token ${ghToken}`)
  }
  autoUpdater.autoInstallOnAppQuit = false  // 使用者必須明確觸發更新，避免關閉視窗時靜默安裝
  autoUpdater.on('update-available', (info) => {
    console.log('[autoUpdater] 偵測到新版本：', info.version)
    mainWindow?.webContents.send('update-available', { version: info.version })
  })
  autoUpdater.on('update-not-available', () => {
    console.log('[autoUpdater] 已是最新版本')
    mainWindow?.webContents.send('update-not-available')
  })
  autoUpdater.on('error', (err) => {
    console.error('[autoUpdater] 錯誤：', err?.message || err)
  })
  autoUpdater.on('download-progress', (p) => {
    const pct = Math.round(p.percent)
    console.log(`[autoUpdater] 下載中 ${pct}%`)
    mainWindow?.webContents.send('update-download-progress', { percent: pct, bytesPerSecond: p.bytesPerSecond, transferred: p.transferred, total: p.total })
  })
  autoUpdater.on('update-downloaded', async (info) => {
    mainWindow?.webContents.send('update-downloaded', { version: info.version })
    // 由前端 Settings 頁觸發安裝，此處不再顯示 native dialog
  })
}

// 禁止導航到非 localhost 頁面（安全防護）
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost')) {
      event.preventDefault()
    }
  })
})
