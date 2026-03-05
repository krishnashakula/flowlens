/**
 * FlowLens — Electron Preload Script
 * Exposes a safe, minimal API from the main process to the renderer
 * via contextBridge (contextIsolation: true).
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getScreenSources: () => ipcRenderer.invoke("get-screen-sources"),
  getAudioDevices: () => ipcRenderer.invoke("get-audio-devices"),
  quitApp: () => ipcRenderer.send("quit-app"),
  minimizeWindow: () => ipcRenderer.send("minimize-window"),
  isElectron: true,
});
