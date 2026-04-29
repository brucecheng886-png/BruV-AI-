const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronApp', {
  version: process.versions.electron,
  reload:       () => ipcRenderer.send('win-reload'),
  forceReload:  () => ipcRenderer.send('win-force-reload'),
  toggleDevTools: () => ipcRenderer.send('win-devtools'),
  minimize:     () => ipcRenderer.send('win-minimize'),
  maximize:     () => ipcRenderer.send('win-maximize'),
  quit:         () => ipcRenderer.send('win-quit'),
})

// Token 持久化（safeStorage）
contextBridge.exposeInMainWorld('electronAPI', {
  saveToken:  (token) => ipcRenderer.invoke('auth:save-token', token),
  loadToken:  ()      => ipcRenderer.invoke('auth:load-token'),
  clearToken: ()      => ipcRenderer.invoke('auth:clear-token'),
})
