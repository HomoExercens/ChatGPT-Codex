import React from 'react';

import { useToastStore } from '../stores/toast';

const stylesByKind: Record<string, { bg: string; border: string; title: string; body: string }> = {
  info: { bg: 'bg-surface-1/85 backdrop-blur-xl', border: 'border-border/12', title: 'text-fg', body: 'text-muted' },
  success: {
    bg: 'bg-success-500/10 backdrop-blur-xl',
    border: 'border-success-500/20',
    title: 'text-fg',
    body: 'text-success-500/90',
  },
  error: { bg: 'bg-danger-500/10 backdrop-blur-xl', border: 'border-danger-500/20', title: 'text-fg', body: 'text-danger-500/90' },
};

export const ToastViewport: React.FC = () => {
  const items = useToastStore((s) => s.items);
  const dismiss = useToastStore((s) => s.dismiss);

  if (!items.length) return null;

  return (
    <div
      className="fixed left-0 right-0 z-[200] px-4 flex flex-col items-center gap-2 pointer-events-none"
      style={{ bottom: `calc(var(--nl-tabbar-h) + env(safe-area-inset-bottom) + 12px)` }}
    >
      {items.map((t) => {
        const s = stylesByKind[t.kind] ?? stylesByKind.info;
        return (
          <div
            key={t.id}
            className={`pointer-events-auto w-full max-w-md rounded-3xl ${s.bg} border ${s.border} shadow-glass`}
            role="status"
            aria-live="polite"
          >
            <div className="px-4 py-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className={`text-sm font-extrabold tracking-tight ${s.title} truncate`}>{t.title}</div>
                {t.message ? <div className={`text-xs mt-1 ${s.body} break-words`}>{t.message}</div> : null}
              </div>
              <button
                type="button"
                className="shrink-0 text-muted hover:text-fg text-xs font-bold px-3 py-2 rounded-2xl bg-surface-2/40 hover:bg-surface-2/60 border border-border/10"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
              >
                Close
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
