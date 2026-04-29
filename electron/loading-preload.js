const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('loadingBridge', {
  onStatus: (cb) => ipcRenderer.on('loading-status', (_, text) => cb(text))
})
