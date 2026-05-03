const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('loadingBridge', {
  onStatus:  (cb) => ipcRenderer.on('loading-status', (_, text) => cb(text)),
  minimize:  ()   => ipcRenderer.send('splash:minimize'),
  close:     ()   => ipcRenderer.send('splash:close'),
})
