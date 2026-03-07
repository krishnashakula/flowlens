/**
 * FlowLens — Electron Main Process
 * Creates a compact always-on-top floating window and manages
 * screen capture permissions and IPC with the renderer.
 */

const {
  app,
  BrowserWindow,
  ipcMain,
  desktopCapturer,
  systemPreferences,
  screen: electronScreen,
  session,
} = require("electron");
const path = require("path");
const isDev = process.env.NODE_ENV === "development" || !app.isPackaged;

// Suppress Electron's security warnings in development — they are dev-only
// reminders and vanish automatically when the app is packaged.
if (isDev) process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = "true";

// Suppress Chrome DevTools Protocol autofill errors (Autofill.enable / setAddresses
// are not implemented in Electron and cause noisy console errors).
app.commandLine.appendSwitch("disable-features", "AutofillServerCommunication,AutofillBrowserDelegate");

let mainWindow = null;

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------

function createWindow() {
  const { width: screenW, height: screenH } =
    electronScreen.getPrimaryDisplay().workAreaSize;

  const WIN_W = 380;
  const WIN_H = 520;

  mainWindow = new BrowserWindow({
    width: WIN_W,
    height: WIN_H,
    x: screenW - WIN_W - 16,
    y: screenH - WIN_H - 16,
    alwaysOnTop: true,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
      // Allow media access from renderer
      webSecurity: true,
    },
  });

  // Grant media permissions (screen + mic) automatically
  session.defaultSession.setPermissionRequestHandler(
    (webContents, permission, callback) => {
      const allowedPermissions = ["media", "display-capture", "mediaKeySystem"];
      callback(allowedPermissions.includes(permission));
    }
  );

  session.defaultSession.setPermissionCheckHandler(
    (webContents, permission) => {
      const allowedPermissions = ["media", "display-capture"];
      return allowedPermissions.includes(permission);
    }
  );

  // Electron 22+: intercept getDisplayMedia() calls from renderer and
  // auto-select the primary screen — no system picker shown.
  session.defaultSession.setDisplayMediaRequestHandler(
    async (request, callback) => {
      try {
        const sources = await desktopCapturer.getSources({ types: ["screen"] });
        const primary = sources.find((s) => s.name.toLowerCase().includes("entire") ||
                                            s.name.toLowerCase().includes("screen")) ||
                        sources[0];
        callback({ video: primary || sources[0], audio: "loopback" });
      } catch (err) {
        console.error("setDisplayMediaRequestHandler error:", err);
        callback({});
      }
    }
  );

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    // Use 'undocked' (local bundled DevTools) instead of 'detach' which tries
    // to load a remote appspot.com frontend and causes JSON parse errors.
    mainWindow.webContents.openDevTools({ mode: "undocked" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
    // Request screen recording permission on macOS
    requestScreenPermission();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// Screen recording permission (macOS only)
// ---------------------------------------------------------------------------

async function requestScreenPermission() {
  if (process.platform !== "darwin") return;

  const status = systemPreferences.getMediaAccessStatus("screen");
  if (status !== "granted") {
    // Trigger the system permission dialog
    await desktopCapturer.getSources({ types: ["screen"] });
  }
}

// ---------------------------------------------------------------------------
// IPC handlers
// ---------------------------------------------------------------------------

/**
 * Returns list of available screen sources for getDisplayMedia.
 * Called by renderer before startCapture().
 */
ipcMain.handle("get-screen-sources", async () => {
  try {
    const sources = await desktopCapturer.getSources({
      types: ["screen", "window"],
      thumbnailSize: { width: 160, height: 90 },
    });
    return sources.map((s) => ({
      id: s.id,
      name: s.name,
      thumbnail: s.thumbnail.toDataURL(),
    }));
  } catch (err) {
    console.error("get-screen-sources error:", err);
    return [];
  }
});

/**
 * Returns list of available audio input devices.
 */
ipcMain.handle("get-audio-devices", async () => {
  try {
    // Delegate to renderer via webContents — renderer has access to navigator.mediaDevices
    return [];
  } catch (err) {
    return [];
  }
});

/**
 * Quit the application cleanly.
 */
ipcMain.on("quit-app", () => {
  app.quit();
});

/**
 * Minimise the window to taskbar.
 */
ipcMain.on("minimize-window", () => {
  mainWindow?.minimize();
});

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}
