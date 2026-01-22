const { app, BrowserWindow, ipcMain, shell } = require('electron');
const childProcess = require('child_process');
const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const { URL } = require('url');

let apiProcess = null;
let webServer = null;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isPortFree(port) {
  return await new Promise((resolve) => {
    const server = net
      .createServer()
      .once('error', () => resolve(false))
      .once('listening', () => server.close(() => resolve(true)))
      .listen(port, '127.0.0.1');
  });
}

async function findAvailablePort(startPort, maxTries = 50) {
  let p = Number(startPort);
  for (let i = 0; i < maxTries; i += 1) {
    if (await isPortFree(p)) return p;
    p += 1;
  }
  throw new Error(`No free port found starting at ${startPort}`);
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.html') return 'text/html; charset=utf-8';
  if (ext === '.js') return 'application/javascript; charset=utf-8';
  if (ext === '.css') return 'text/css; charset=utf-8';
  if (ext === '.json') return 'application/json; charset=utf-8';
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.svg') return 'image/svg+xml';
  if (ext === '.woff') return 'font/woff';
  if (ext === '.woff2') return 'font/woff2';
  return 'application/octet-stream';
}

function repoRootFromHere() {
  // apps/desktop/src -> repo root is 3 levels up
  return path.resolve(__dirname, '..', '..', '..');
}

function resolveRuntimePaths() {
  if (app.isPackaged) {
    const resources = process.resourcesPath;
    const pythonExe = process.platform === 'win32' ? 'python.exe' : 'python';
    return {
      mode: 'packaged',
      webRoot: path.join(resources, 'web'),
      pyRoot: path.join(resources, 'py'),
      pythonBin: path.join(resources, 'python', pythonExe),
    };
  }

  const repoRoot = repoRootFromHere();
  const pythonBin =
    process.env.NEUROLEAGUE_DESKTOP_PYTHON ||
    (process.platform === 'win32' ? 'python' : 'python3');
  return {
    mode: 'dev',
    webRoot: path.join(repoRoot, 'apps', 'web', 'dist'),
    pyRoot: repoRoot,
    pythonBin,
  };
}

function proxyToApi(req, res, apiPort) {
  const opts = {
    hostname: '127.0.0.1',
    port: apiPort,
    method: req.method,
    path: req.url,
    headers: {
      ...req.headers,
      host: `127.0.0.1:${apiPort}`,
    },
  };

  const upstream = http.request(opts, (up) => {
    res.writeHead(up.statusCode || 502, up.headers);
    up.pipe(res);
  });

  upstream.on('error', (err) => {
    res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
    res.end(`proxy_error: ${String(err && err.message ? err.message : err)}`);
  });

  req.pipe(upstream);
}

function startWebServer({ port, apiPort, webRoot }) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const u = new URL(req.url || '/', `http://127.0.0.1:${port}`);
      const pathname = u.pathname || '/';
      if (pathname.startsWith('/api') || pathname.startsWith('/s/')) {
        return proxyToApi(req, res, apiPort);
      }

      let rel = decodeURIComponent(pathname);
      if (rel === '/') rel = '/index.html';

      const tryPath = path.join(webRoot, rel);
      const safe = path.resolve(tryPath);
      const rootResolved = path.resolve(webRoot);
      if (!safe.startsWith(rootResolved)) {
        res.writeHead(403, { 'content-type': 'text/plain; charset=utf-8' });
        return res.end('forbidden');
      }

      const sendIndex = () => {
        const indexPath = path.join(webRoot, 'index.html');
        try {
          const buf = fs.readFileSync(indexPath);
          res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
          res.end(buf);
        } catch (err) {
          res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' });
          res.end(`index_missing: ${String(err && err.message ? err.message : err)}`);
        }
      };

      try {
        if (fs.existsSync(safe) && fs.statSync(safe).isFile()) {
          const buf = fs.readFileSync(safe);
          res.writeHead(200, { 'content-type': contentTypeFor(safe) });
          return res.end(buf);
        }
      } catch {
        // ignore
      }

      // SPA fallback
      return sendIndex();
    });

    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

function httpGetJson(urlStr) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const req = http.request(
      {
        hostname: u.hostname,
        port: Number(u.port),
        path: u.pathname + (u.search || ''),
        method: 'GET',
      },
      (res) => {
        const chunks = [];
        res.on('data', (d) => chunks.push(d));
        res.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf-8');
          try {
            resolve({ status: res.statusCode || 0, json: JSON.parse(body) });
          } catch (err) {
            reject(err);
          }
        });
      }
    );
    req.on('error', reject);
    req.end();
  });
}

async function waitForReady({ apiPort, timeoutMs = 30_000 }) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const out = await httpGetJson(`http://127.0.0.1:${apiPort}/api/ready`);
      if (out.status === 200 && out.json && out.json.status === 'ok') return true;
    } catch {
      // ignore
    }
    await sleep(500);
  }
  return false;
}

function startApi({ pythonBin, apiPort, webPort, pyRoot }) {
  const userData = app.getPath('userData');
  const artifactsDir = path.join(userData, 'artifacts');
  fs.mkdirSync(artifactsDir, { recursive: true });

  const dbPath = path.join(artifactsDir, 'neuroleague.db');
  const dbUrl = `sqlite:///${dbPath.replaceAll('\\', '/')}`;

  let pythonPath;
  if (app.isPackaged) {
    pythonPath = [
      path.join(pyRoot, 'services', 'api'),
      path.join(pyRoot, 'packages', 'sim'),
      path.join(pyRoot, 'packages', 'shared'),
    ].join(path.delimiter);
  } else {
    const repoRoot = pyRoot;
    pythonPath = [
      path.join(repoRoot, 'services', 'api'),
      path.join(repoRoot, 'packages', 'sim'),
      path.join(repoRoot, 'packages', 'shared'),
    ].join(path.delimiter);
  }

  const env = {
    ...process.env,
    PYTHONPATH: pythonPath,
    CUDA_VISIBLE_DEVICES: '',
    NEUROLEAGUE_DESKTOP_MODE: '1',
    NEUROLEAGUE_DEMO_MODE: process.env.NEUROLEAGUE_DEMO_MODE || '1',
    NEUROLEAGUE_DB_URL: process.env.NEUROLEAGUE_DB_URL || dbUrl,
    NEUROLEAGUE_ARTIFACTS_DIR: process.env.NEUROLEAGUE_ARTIFACTS_DIR || artifactsDir,
    NEUROLEAGUE_PUBLIC_BASE_URL: process.env.NEUROLEAGUE_PUBLIC_BASE_URL || `http://127.0.0.1:${webPort}`,
    NEUROLEAGUE_DISCORD_OAUTH_MOCK: process.env.NEUROLEAGUE_DISCORD_OAUTH_MOCK || '1',
    NEUROLEAGUE_DISCORD_MODE: process.env.NEUROLEAGUE_DISCORD_MODE || 'mock',
  };

  const args = [
    '-m',
    'uvicorn',
    'neuroleague_api.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    String(apiPort),
    '--log-level',
    'info',
  ];

  const proc = childProcess.spawn(pythonBin, args, {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  proc.stdout.on('data', (d) => console.log(`[api] ${String(d)}`.trimEnd()));
  proc.stderr.on('data', (d) => console.error(`[api] ${String(d)}`.trimEnd()));
  proc.on('exit', (code) => console.log(`[api] exited: ${code}`));
  return proc;
}

function createErrorWindow(message) {
  const win = new BrowserWindow({
    width: 900,
    height: 600,
    show: true,
  });
  const html = `<!doctype html><html><body style="font-family:sans-serif;padding:24px;">
  <h2>NeuroLeague Desktop Demo</h2>
  <pre style="white-space:pre-wrap;background:#111827;color:#e5e7eb;padding:16px;border-radius:12px;">${message
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')}</pre>
  </body></html>`;
  win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  return win;
}

async function createMainWindow(webPort) {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await win.loadURL(`http://127.0.0.1:${webPort}/`);
  win.show();
  return win;
}

async function bootstrap() {
  const runtime = resolveRuntimePaths();
  const apiPort = await findAvailablePort(Number(process.env.NEUROLEAGUE_DESKTOP_API_PORT || 8000));
  const webPort = await findAvailablePort(Number(process.env.NEUROLEAGUE_DESKTOP_WEB_PORT || 3100));

  if (!fs.existsSync(runtime.webRoot)) {
    createErrorWindow(
      `Web build not found at: ${runtime.webRoot}\n\nBuild it first:\n- cd apps/web && npm ci && npm run build`
    );
    return;
  }

  apiProcess = startApi({ pythonBin: runtime.pythonBin, apiPort, webPort, pyRoot: runtime.pyRoot });
  const ready = await waitForReady({ apiPort, timeoutMs: 45_000 });
  if (!ready) {
    createErrorWindow(
      `API failed to become ready.\n\nPort: ${apiPort}\nPython: ${runtime.pythonBin}\nMode: ${runtime.mode}\n\nTip: set NEUROLEAGUE_DESKTOP_PYTHON to a valid python path.`
    );
    return;
  }

  webServer = await startWebServer({ port: webPort, apiPort, webRoot: runtime.webRoot });
  await createMainWindow(webPort);
}

function cleanup() {
  try {
    if (webServer) webServer.close();
  } catch {
    // ignore
  }
  webServer = null;

  try {
    if (apiProcess && !apiProcess.killed) apiProcess.kill();
  } catch {
    // ignore
  }
  apiProcess = null;
}

ipcMain.handle('neuroleague:openExternal', async (_evt, urlRaw) => {
  const url = String(urlRaw || '').trim();
  if (!url) return false;
  try {
    await shell.openExternal(url);
    return true;
  } catch {
    return false;
  }
});

app.on('window-all-closed', () => {
  cleanup();
  app.quit();
});

app.on('before-quit', () => cleanup());

app.whenReady().then(bootstrap).catch((err) => {
  createErrorWindow(String(err && err.stack ? err.stack : err));
});

