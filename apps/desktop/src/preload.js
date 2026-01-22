const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('neuroleagueDesktop', {
  openExternal: async (url) => {
    return await ipcRenderer.invoke('neuroleague:openExternal', String(url || ''));
  },
});

