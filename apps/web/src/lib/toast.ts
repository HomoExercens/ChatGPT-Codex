import { useToastStore } from '../stores/toast';

export const toast = {
  info: (title: string, message?: string) => useToastStore.getState().push({ kind: 'info', title, message, ttl_ms: 3500 }),
  success: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'success', title, message, ttl_ms: 3000 }),
  error: (title: string, message?: string) => useToastStore.getState().push({ kind: 'error', title, message, ttl_ms: 6000 }),
};

