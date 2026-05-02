const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronApp', {
  version: require('./package.json').version,
  reload:       () => ipcRenderer.send('win-reload'),
  forceReload:  () => ipcRenderer.send('win-force-reload'),
  toggleDevTools: () => ipcRenderer.send('win-devtools'),
  minimize:     () => ipcRenderer.send('win-minimize'),
  maximize:     () => ipcRenderer.send('win-maximize'),
  quit:         () => ipcRenderer.send('win-quit'),
  setTheme:     (theme) => ipcRenderer.send('win-set-theme', theme),
  onUpdateAvailable:  (cb) => ipcRenderer.on('update-available',  (_, info) => cb(info)),
  onUpdateDownloaded: (cb) => ipcRenderer.on('update-downloaded', (_, info) => cb(info)),
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
