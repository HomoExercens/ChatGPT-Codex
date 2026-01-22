export type ShareVariants = {
  lenv?: string;
  cv?: string;
  ctpl?: string;
};

const STORAGE_KEY = 'neuroleague.share_variants';

function safeGetLocalStorage(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

function clampStr(value: string | null, maxLen: number): string | undefined {
  const v = (value || '').trim();
  if (!v) return undefined;
  return v.length > maxLen ? v.slice(0, maxLen) : v;
}

export function readShareVariants(): ShareVariants {
  const ls = safeGetLocalStorage();
  if (!ls) return {};
  try {
    const raw = ls.getItem(STORAGE_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw) as Record<string, unknown>;
    const lenv = typeof obj.lenv === 'string' ? clampStr(obj.lenv, 16) : undefined;
    const cv = typeof obj.cv === 'string' ? clampStr(obj.cv, 32) : undefined;
    const ctpl = typeof obj.ctpl === 'string' ? clampStr(obj.ctpl, 64) : undefined;
    return { ...(lenv ? { lenv } : {}), ...(cv ? { cv } : {}), ...(ctpl ? { ctpl } : {}) };
  } catch {
    return {};
  }
}

export function writeShareVariants(next: ShareVariants): void {
  const ls = safeGetLocalStorage();
  if (!ls) return;
  const lenv = clampStr(next.lenv ?? null, 16);
  const cv = clampStr(next.cv ?? null, 32);
  const ctpl = clampStr(next.ctpl ?? null, 64);
  try {
    if (!lenv && !cv && !ctpl) {
      ls.removeItem(STORAGE_KEY);
      return;
    }
    ls.setItem(STORAGE_KEY, JSON.stringify({ lenv, cv, ctpl }));
  } catch {
    // ignore
  }
}

