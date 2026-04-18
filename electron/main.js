const { app, BrowserWindow, shell, ipcMain, globalShortcut, Menu, dialog, net } = require('electron')
const path = require('path')
const https = require('https')
const http = require('http')

const TARGET_URL = 'http://localhost:80'
const BACKEND_HEALTH_URL = 'http://localhost:80/api/health'
const RETRY_INTERVAL_MS = 2000
const MAX_RETRIES = 30 // 最多等 60 秒
const UPDATE_CHECK_INTERVAL_MS = 60 * 1000 // 每 60 秒檢查前端是否有新版本

let mainWindow = null
let splashWindow = null
let currentBundleHash = null // 記錄目前載入的前端 bundle hash
let updateCheckTimer = null

// ── 建立 Splash 等待視窗 ─────────────────────────────────────────────────────
function createSplash () {
  splashWindow = new BrowserWindow({
    width: 420,
    height: 260,
    frame: false,
    alwaysOnTop: true,
    transparent: false,
    resizable: false,
    webPreferences: { nodeIntegration: false }
  })
  splashWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(`
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
          font-family: -apple-system, "Microsoft JhengHei", sans-serif;
          background: #0f172a; color: #e2e8f0;
          display: flex; flex-direction: column;
          align-items: center; justify-content: center;
          height: 100vh; gap: 20px;
        }
        h1 { font-size: 22px; color: #60a5fa; }
        p  { font-size: 13px; color: #94a3b8; }
        .dot { display: inline-block; animation: blink 1.2s infinite; }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink { 0%,80%,100%{opacity:0} 40%{opacity:1} }
      </style>
    </head>
    <body>
      <h1>BruV AI 知識庫</h1>
      <p>正在等待後端服務啟動<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></p>
    </body>
    </html>
  `))
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
    titleBarOverlay: { color: '#f1f5f9', symbolColor: '#475569', height: 38 },
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

// ── App 生命週期 ──────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createSplash()
  waitForBackend()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createSplash()
      waitForBackend()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// 禁止導航到非 localhost 頁面（安全防護）
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://localhost')) {
      event.preventDefault()
    }
  })
})
