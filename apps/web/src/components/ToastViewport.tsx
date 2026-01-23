import React from 'react';

import { useToastStore } from '../stores/toast';

const stylesByKind: Record<string, { bg: string; border: string; title: string; body: string }> = {
  info: { bg: 'bg-slate-950/90', border: 'border-white/10', title: 'text-white', body: 'text-white/70' },
  success: { bg: 'bg-emerald-950/85', border: 'border-emerald-700/30', title: 'text-white', body: 'text-emerald-50/80' },
  error: { bg: 'bg-red-950/85', border: 'border-red-700/30', title: 'text-white', body: 'text-red-50/80' },
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
            className={`pointer-events-auto w-full max-w-md rounded-2xl ${s.bg} border ${s.border} shadow-xl`}
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
                className="shrink-0 text-white/70 hover:text-white text-xs font-bold px-2 py-1 rounded-lg bg-white/10 hover:bg-white/15"
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

