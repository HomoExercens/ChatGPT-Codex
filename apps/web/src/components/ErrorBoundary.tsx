import React from 'react';

type Props = { children: React.ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-bg text-fg">
        <div className="w-full max-w-md rounded-3xl border border-border/12 bg-surface-1/70 backdrop-blur p-5 shadow-glass">
          <div className="font-extrabold tracking-tight text-lg">Something went wrong</div>
          <div className="text-sm text-muted mt-2">Try reloading. If it keeps happening, report it.</div>
          <pre className="mt-3 text-[11px] text-danger-500/90 whitespace-pre-wrap break-words">{this.state.error.message}</pre>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className="px-3 py-2 rounded-2xl bg-surface-2/40 hover:bg-surface-2/60 text-fg text-sm font-semibold border border-border/10"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <a
              className="px-3 py-2 rounded-2xl bg-surface-2/40 hover:bg-surface-2/60 text-fg text-sm font-semibold border border-border/10"
              href="/feedback?context=error_boundary"
            >
              Report
            </a>
          </div>
        </div>
      </div>
    );
  }
}
