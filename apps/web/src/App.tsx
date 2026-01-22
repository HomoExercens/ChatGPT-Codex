import React from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

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
import { ProfilePage } from './pages/ProfilePage';
import { QuickPage } from './pages/QuickPage';
import { ReplayPage } from './pages/ReplayPage';
import { ReplayHubPage } from './pages/ReplayHubPage';
import { RankedPage } from './pages/RankedPage';
import { SettingsPage } from './pages/SettingsPage';
import { SocialPage } from './pages/SocialPage';
import { StartPage } from './pages/StartPage';
import { TrainingPage } from './pages/TrainingPage';
import { MetaPage } from './pages/MetaPage';
import { TournamentPage } from './pages/TournamentPage';

const RequireAuth: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const token = useAuthStore((s) => s.token);
  const location = useLocation();
  if (!token) return <Navigate to="/" replace state={{ from: location.pathname }} />;
  return children;
};

const RedirectIfAuthed: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const token = useAuthStore((s) => s.token);
  if (token) return <Navigate to="/home" replace />;
  return children;
};

function App() {
  useApplyA11ySettings();

  return (
    <Routes>
      <Route
        path="/"
        element={
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        }
      />
      <Route path="/start" element={<StartPage />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/home" element={<HomePage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/forge" element={<ForgePage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/quick" element={<QuickPage />} />
        <Route path="/clips" element={<ClipsPage />} />
        <Route path="/challenge/:id" element={<ChallengePage />} />
        <Route path="/ranked" element={<RankedPage />} />
        <Route path="/replay" element={<ReplayHubPage />} />
        <Route path="/replay/:id" element={<ReplayPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/meta" element={<MetaPage />} />
        <Route path="/tournament" element={<TournamentPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/profile/:userId" element={<ProfilePage />} />
        <Route path="/ops" element={<OpsPage />} />
        <Route path="/ops/moderation" element={<OpsModerationPage />} />
        <Route path="/ops/featured" element={<OpsFeaturedPage />} />
        <Route path="/ops/build-of-day" element={<OpsBuildOfDayPage />} />
        <Route path="/ops/discord" element={<OpsDiscordPage />} />
        <Route path="/ops/packs" element={<OpsPacksPage />} />
        <Route path="/ops/quests" element={<OpsQuestsPage />} />
        <Route path="/ops/weekly" element={<OpsWeeklyPage />} />
        <Route path="/social" element={<SocialPage />} />
        <Route path="/store" element={<PlaceholderPage title="Store" />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}

export default App;
