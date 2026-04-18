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
