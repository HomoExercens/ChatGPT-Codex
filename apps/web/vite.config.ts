import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.NEUROLEAGUE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';

function hostFromBaseUrl(value: string | undefined): string | null {
  const raw = (value ?? '').trim();
  if (!raw) return null;
  try {
    return new URL(raw).hostname;
  } catch {
    return null;
  }
}

function parseAllowedHosts(): string[] {
  const out = new Set<string>();
  // Needed for Cloudflare Quick Tunnel (Host header will be <random>.trycloudflare.com).
  out.add('.trycloudflare.com');

  // When using a stable preview domain (named tunnel / staging), allow that hostname in dev.
  const baseHost = hostFromBaseUrl(process.env.NEUROLEAGUE_PUBLIC_BASE_URL);
  if (baseHost) out.add(baseHost);

  const extra = (process.env.VITE_ALLOWED_HOSTS ?? '').split(',');
  for (const h of extra) {
    const v = h.trim();
    if (v) out.add(v);
  }
  return Array.from(out);
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Dev-only Host allowlist to support public preview tunnels safely.
    allowedHosts: parseAllowedHosts(),
    proxy: {
      '/api': proxyTarget,
      '/s/': proxyTarget,
      '/.well-known': proxyTarget,
    },
  },
})
