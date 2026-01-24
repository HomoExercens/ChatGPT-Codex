import React, { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Layout } from './components/Layout';
import { useApplyA11ySettings } from './lib/a11y';
import { useAuthStore } from './stores/auth';
import { ForgePage } from './pages/ForgePage';
import { GalleryPage } from './pages/GalleryPage';
import { HomePage } from './pages/HomePage';
import { LoginPage } from './pages/LoginPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { ClipsPage } from './pages/ClipsPage';
import { ChallengePage } from './pages/ChallengePage';
import { DemoPage } from './pages/DemoPage';
import { LeaderboardPage } from './pages/LeaderboardPage';
import { OpsPage } from './pages/OpsPage';
import { OpsModerationPage } from './pages/OpsModerationPage';
import { OpsFeaturedPage } from './pages/OpsFeaturedPage';
import { OpsDiscordPage } from './pages/OpsDiscordPage';
import { OpsBuildOfDayPage } from './pages/OpsBuildOfDayPage';
import { OpsPacksPage } from './pages/OpsPacksPage';
import { OpsQuestsPage } from './pages/OpsQuestsPage';
import { OpsWeeklyPage } from './pages/OpsWeeklyPage';
import { OpsHeroPage } from './pages/OpsHeroPage';
import { ProfilePage } from './pages/ProfilePage';
import { QuickPage } from './pages/QuickPage';
import { ReplayPage } from './pages/ReplayPage';
import { ReplayHubPage } from './pages/ReplayHubPage';
import { RemixPage } from './pages/RemixPage';
import { BeatPage } from './pages/BeatPage';
import { PlaytestPage } from './pages/PlaytestPage';
import { FeedbackPage } from './pages/FeedbackPage';
import { RankedPage } from './pages/RankedPage';
import { SettingsPage } from './pages/SettingsPage';
import { SocialPage } from './pages/SocialPage';
import { StartPage } from './pages/StartPage';
import { TrainingPage } from './pages/TrainingPage';
import { MetaPage } from './pages/MetaPage';
import { TournamentPage } from './pages/TournamentPage';
import { InboxPage } from './pages/InboxPage';
import { MePage } from './pages/MePage';

type AuthResponse = { access_token: string; token_type: 'bearer' };

const RequireSession: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const token = useAuthStore((s) => s.token);
  const setToken = useAuthStore((s) => s.setToken);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready'>('loading');

  useEffect(() => {
    if (token) {
      setStatus('ready');
      return;
    }
    let cancelled = false;
    const run = async () => {
      try {
        const resp = await fetch('/api/auth/guest', { method: 'POST' });
        if (!resp.ok) throw new Error((await resp.text()) || `HTTP ${resp.status}`);
        const json = (await resp.json()) as AuthResponse;
        if (cancelled) return;
        setToken(json.access_token);
        setStatus('ready');
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [setToken, token]);

  if (token) return children;
  if (status === 'ready') return children;

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-slate-950">
      <div className="w-full max-w-md bg-white/5 border border-white/10 rounded-2xl p-5 text-white">
        <div className="font-extrabold tracking-tight text-lg">Starting NeuroLeague…</div>
        <div className="text-sm text-white/70 mt-2">Preparing your session.</div>
        {error ? (
          <div className="mt-3 text-xs text-red-200 bg-red-950/40 border border-red-900/40 rounded-xl px-3 py-2">
            <div className="font-mono break-words">{error}</div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold"
                onClick={() => window.location.reload()}
              >
                Retry
              </button>
              <a
                className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold"
                href="/login"
              >
                Login
              </a>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

const RedirectIfAuthed: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const token = useAuthStore((s) => s.token);
  if (token) return <Navigate to="/play" replace />;
  return children;
};

function App() {
  useApplyA11ySettings();

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/play" replace />} />
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        }
      />
      <Route path="/start" element={<StartPage />} />
      <Route path="/remix" element={<RemixPage />} />
      <Route path="/beat" element={<BeatPage />} />
      <Route path="/playtest" element={<PlaytestPage />} />
      <Route path="/feedback" element={<FeedbackPage />} />

      <Route
        element={
          <RequireSession>
            <Layout />
          </RequireSession>
        }
      >
        <Route path="/play" element={<ClipsPage />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/forge" element={<ForgePage />} />
        <Route path="/forge/:bpId" element={<ForgePage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/quick" element={<QuickPage />} />
        <Route path="/clips" element={<Navigate to="/play" replace />} />
        <Route path="/challenge/:id" element={<ChallengePage />} />
        <Route path="/ranked" element={<RankedPage />} />
        <Route path="/replay" element={<ReplayHubPage />} />
        <Route path="/replay/:id" element={<ReplayPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/meta" element={<MetaPage />} />
        <Route path="/tournament" element={<TournamentPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/profile/:userId" element={<ProfilePage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/me" element={<MePage />} />
        <Route path="/ops" element={<OpsPage />} />
        <Route path="/ops/moderation" element={<OpsModerationPage />} />
        <Route path="/ops/featured" element={<OpsFeaturedPage />} />
        <Route path="/ops/hero" element={<OpsHeroPage />} />
        <Route path="/ops/build-of-day" element={<OpsBuildOfDayPage />} />
        <Route path="/ops/discord" element={<OpsDiscordPage />} />
        <Route path="/ops/packs" element={<OpsPacksPage />} />
        <Route path="/ops/quests" element={<OpsQuestsPage />} />
        <Route path="/ops/weekly" element={<OpsWeeklyPage />} />
        <Route path="/social" element={<SocialPage />} />
        <Route path="/store" element={<PlaceholderPage title="Store" />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/play" replace />} />
    </Routes>
  );
}

export default App;
