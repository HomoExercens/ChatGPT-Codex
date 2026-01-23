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
      <div className="min-h-screen flex items-center justify-center p-4 bg-slate-950 text-white">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="font-extrabold tracking-tight text-lg">Something went wrong</div>
          <div className="text-sm text-white/70 mt-2">Try reloading. If it keeps happening, report it.</div>
          <pre className="mt-3 text-[11px] text-red-100/80 whitespace-pre-wrap break-words">{this.state.error.message}</pre>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <a
              className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold"
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

