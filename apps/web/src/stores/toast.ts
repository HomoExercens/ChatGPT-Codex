import { create } from 'zustand';

export type ToastKind = 'info' | 'success' | 'error';

export type ToastItem = {
  id: string;
  kind: ToastKind;
  title: string;
  message?: string | null;
  created_at_ms: number;
  ttl_ms: number;
};

type ToastState = {
  items: ToastItem[];
  push: (toast: Omit<ToastItem, 'id' | 'created_at_ms'> & { id?: string }) => string;
  dismiss: (id: string) => void;
};

function randomId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return `${prefix}${crypto.randomUUID()}`;
  return `${prefix}${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`;
}

export const useToastStore = create<ToastState>((set, get) => ({
  items: [],
  push: (toast) => {
    const id = toast.id ?? randomId('toast_');
    const created_at_ms = Date.now();
    const item: ToastItem = { ...toast, id, created_at_ms };
    set((s) => ({ items: [...s.items, item].slice(-3) }));

    const ttl = Math.max(1200, Math.min(20_000, toast.ttl_ms));
    try {
      window.setTimeout(() => {
        get().dismiss(id);
      }, ttl);
    } catch {
      // ignore
    }

    return id;
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));

