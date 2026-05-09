const { contextBridge, ipcRenderer } = require('electron')
const path = require('path')

contextBridge.exposeInMainWorld('electronApp', {
  version: require(path.join(__dirname, 'package.json')).version,
  reload:       () => ipcRenderer.send('win-reload'),
  forceReload:  () => ipcRenderer.send('win-force-reload'),
  toggleDevTools: () => ipcRenderer.send('win-devtools'),
  minimize:     () => ipcRenderer.send('win-minimize'),
  maximize:     () => ipcRenderer.send('win-maximize'),
  quit:         () => ipcRenderer.send('win-quit'),
  onUpdateAvailable:    (cb) => ipcRenderer.on('update-available',        (_, info) => cb(info)),
  onUpdateDownloaded:   (cb) => ipcRenderer.on('update-downloaded',       (_, info) => cb(info)),
  onUpdateNotAvailable: (cb) => ipcRenderer.on('update-not-available',    (_)       => cb()),
  onDownloadProgress:   (cb) => ipcRenderer.on('update-download-progress',(_, info) => cb(info)),
  onUpdateError:        (cb) => ipcRenderer.on('update-error',            (_, msg)  => cb(msg)),
  checkForUpdate:  () => ipcRenderer.invoke('updater:check'),
  downloadUpdate:  () => ipcRenderer.invoke('updater:download'),
  installUpdate:   () => ipcRenderer.send('updater:install'),
  generateDiagnostic: () => ipcRenderer.invoke('diagnostic:generate'),
})

// Token 持久化（safeStorage）
contextBridge.exposeInMainWorld('electronAPI', {
  saveToken:  (token) => ipcRenderer.invoke('auth:save-token', token),
  loadToken:  ()      => ipcRenderer.invoke('auth:load-token'),
  clearToken: ()      => ipcRenderer.invoke('auth:clear-token'),
  getClosePreference:   () => ipcRenderer.invoke('app:get-close-preference'),
  resetClosePreference: () => ipcRenderer.invoke('app:reset-close-preference'),
  relaunchForUpdate:    () => ipcRenderer.send('relaunch-for-update'),
})
