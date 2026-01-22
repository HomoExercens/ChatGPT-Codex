export type UtmParams = Partial<{
  utm_source: string;
  utm_medium: string;
  utm_campaign: string;
  utm_content: string;
  utm_term: string;
}>;

function clamp(value: string, maxLen: number): string {
  const v = (value || '').trim();
  if (!v) return '';
  return v.length > maxLen ? v.slice(0, maxLen) : v;
}

export function appendUtmParams(url: string, utm: UtmParams): string {
  try {
    const base = new URL(url, window.location.origin);
    for (const [k, raw] of Object.entries(utm ?? {})) {
      const key = (k || '').trim();
      if (!key) continue;
      if (base.searchParams.has(key)) continue;
      const value = typeof raw === 'string' ? clamp(raw, 120) : '';
      if (!value) continue;
      base.searchParams.set(key, value);
    }
    const isAbsolute = /^https?:\/\//i.test(url);
    return isAbsolute ? base.toString() : `${base.pathname}${base.search}${base.hash}`;
  } catch {
    return url;
  }
}

