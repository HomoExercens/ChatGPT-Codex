import { useAuthStore } from '../stores/auth';

const DEVICE_ID_KEY = 'neuroleague.device_id';
const SESSION_ID_KEY = 'neuroleague.session_id';
const ADMIN_TOKEN_KEY = 'neuroleague.admin_token';
const APP_CONTAINER_KEY = 'neuroleague.app_container';

function safeGetStorage(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function safeSetStorage(storage: Storage | undefined, key: string, value: string): void {
  try {
    storage?.setItem(key, value);
  } catch {
    // ignore
  }
}

function randomId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return `${prefix}${crypto.randomUUID()}`;
  return `${prefix}${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`;
}

function getOrCreateDeviceId(): string {
  const ls = typeof localStorage !== 'undefined' ? localStorage : undefined;
  const existing = safeGetStorage(ls, DEVICE_ID_KEY);
  if (existing && existing.trim()) return existing;
  const id = randomId('dev_');
  safeSetStorage(ls, DEVICE_ID_KEY, id);
  return id;
}

function getOrCreateSessionId(): string {
  const ss = typeof sessionStorage !== 'undefined' ? sessionStorage : undefined;
  const ls = typeof localStorage !== 'undefined' ? localStorage : undefined;
  const existing = safeGetStorage(ss, SESSION_ID_KEY) ?? safeGetStorage(ls, SESSION_ID_KEY);
  if (existing && existing.trim()) return existing;
  const id = randomId('sess_');
  safeSetStorage(ss, SESSION_ID_KEY, id);
  return id;
}

function getAdminToken(): string | null {
  const ls = typeof localStorage !== 'undefined' ? localStorage : undefined;
  const raw = safeGetStorage(ls, ADMIN_TOKEN_KEY);
  return raw && raw.trim() ? raw.trim() : null;
}

function normalizeAppContainer(raw: unknown): string | null {
  const v = String(raw ?? '').trim().toLowerCase();
  if (v === 'twa' || v === 'chrome' || v === 'safari') return v;
  return null;
}

function appContainerFromLocation(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const u = new URL(window.location.href);
    const direct = normalizeAppContainer(u.searchParams.get('nl_container') || u.searchParams.get('container'));
    if (direct) return direct;
    const twa = u.searchParams.get('twa');
    if (twa === '1' || twa === 'true') return 'twa';
  } catch {
    // ignore
  }
  return null;
}

function getAppContainer(): string | null {
  const ls = typeof localStorage !== 'undefined' ? localStorage : undefined;
  const stored = normalizeAppContainer(safeGetStorage(ls, APP_CONTAINER_KEY));
  const fromUrl = appContainerFromLocation();
  const chosen = fromUrl ?? stored;
  if (chosen && chosen !== stored) safeSetStorage(ls, APP_CONTAINER_KEY, chosen);
  return chosen;
}

export function getAppContainerHint(): string | null {
  return getAppContainer();
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(init?.headers);

  if (token) headers.set('Authorization', `Bearer ${token}`);
  headers.set('X-Device-Id', getOrCreateDeviceId());
  headers.set('X-Session-Id', getOrCreateSessionId());
  const container = getAppContainer();
  if (container) headers.set('X-App-Container', container);

  if (path.startsWith('/api/ops/') && !headers.has('X-Admin-Token')) {
    const adminToken = getAdminToken();
    if (adminToken) headers.set('X-Admin-Token', adminToken);
  }

  const body = init?.body;
  const hasBody = body != null && body !== undefined;
  const isForm =
    typeof FormData !== 'undefined' && body instanceof FormData;
  const isBlob =
    typeof Blob !== 'undefined' && body instanceof Blob;
  const isParams =
    typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams;
  if (hasBody && !isForm && !isBlob && !isParams && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(body || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function apiFetchBlob(path: string, init?: RequestInit): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(init?.headers);

  if (token) headers.set('Authorization', `Bearer ${token}`);
  headers.set('X-Device-Id', getOrCreateDeviceId());
  headers.set('X-Session-Id', getOrCreateSessionId());
  const container = getAppContainer();
  if (container) headers.set('X-App-Container', container);

  if (path.startsWith('/api/ops/') && !headers.has('X-Admin-Token')) {
    const adminToken = getAdminToken();
    if (adminToken) headers.set('X-Admin-Token', adminToken);
  }

  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(body || `HTTP ${resp.status}`);
  }
  return await resp.blob();
}
