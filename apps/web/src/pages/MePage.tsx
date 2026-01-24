import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, ProgressBar } from '../components/ui';
import { apiFetch } from '../lib/api';
import { playSfx, vibrate } from '../lib/juice';
import { useAuthStore } from '../stores/auth';

type Me = { user_id: string; display_name: string; is_guest: boolean; discord_connected?: boolean; avatar_url?: string | null };

type Progress = {
  xp: number;
  level: number;
  streak_days: number;
  last_active_day?: string | null;
  streak_freeze_tokens: number;
  quests_claimed_total: number;
  perfect_wins: number;
  one_shot_wins: number;
  clutch_wins: number;
};

type UserProfile = {
  progress?: Progress;
  badges?: Array<{ id: string; name: string; earned_at: string; source: string }>;
};

const BADGE_DEFS: Array<{
  id: string;
  name: string;
  desc: string;
  progressKey: keyof Progress;
  goal: number;
}> = [
  { id: 'badge_quest_claim_3', name: 'Quest Claimer I', desc: 'Claim 3 quests', progressKey: 'quests_claimed_total', goal: 3 },
  { id: 'badge_streak_3', name: 'Streak 3', desc: 'Play 3 days in a row', progressKey: 'streak_days', goal: 3 },
  { id: 'badge_level_5', name: 'Level 5', desc: 'Reach level 5', progressKey: 'level', goal: 5 },
  { id: 'badge_perfect', name: 'PERFECT', desc: 'Win a Beat This with full HP', progressKey: 'perfect_wins', goal: 1 },
  { id: 'badge_one_shot', name: 'ONE-SHOT', desc: 'Win a fast Beat This', progressKey: 'one_shot_wins', goal: 1 },
  { id: 'badge_clutch', name: 'CLUTCH', desc: 'Win a close Beat This', progressKey: 'clutch_wins', goal: 1 },
];

export const MePage: React.FC = () => {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);

  const { data: me, isFetching, error } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<Me>('/api/auth/me'),
    staleTime: 30_000,
  });

  const { data: profile } = useQuery({
    queryKey: ['meProfile', me?.user_id],
    queryFn: () => apiFetch<UserProfile>(`/api/users/${encodeURIComponent(me!.user_id)}/profile?mode=1v1`),
    enabled: Boolean(me?.user_id),
    staleTime: 10_000,
  });

  const progress: Progress = {
    xp: profile?.progress?.xp ?? 0,
    level: profile?.progress?.level ?? 1,
    streak_days: profile?.progress?.streak_days ?? 0,
    last_active_day: profile?.progress?.last_active_day ?? null,
    streak_freeze_tokens: profile?.progress?.streak_freeze_tokens ?? 0,
    quests_claimed_total: profile?.progress?.quests_claimed_total ?? 0,
    perfect_wins: profile?.progress?.perfect_wins ?? 0,
    one_shot_wins: profile?.progress?.one_shot_wins ?? 0,
    clutch_wins: profile?.progress?.clutch_wins ?? 0,
  };
  const unlocked = new Set((profile?.badges ?? []).map((b) => b.id));
  const xpInLevel = progress.xp % 100;
  const xpToNext = 100 - xpInLevel;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{me?.display_name ?? 'Me'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isFetching ? <div className="text-sm text-slate-500">Loading…</div> : null}
          {error ? <div className="text-sm text-red-600 break-words">{String(error)}</div> : null}

          <div className="text-sm text-slate-700">
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">User</span>
              <span className="font-mono text-xs break-all">{me?.user_id ?? '—'}</span>
            </div>
            <div className="flex justify-between gap-4 mt-1">
              <span className="text-slate-500">Type</span>
              <span className="font-semibold">{me?.is_guest ? 'Guest' : 'Account'}</span>
            </div>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-slate-500">Level</div>
                <div className="text-2xl font-extrabold text-slate-900">{progress.level}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-slate-500">Streak</div>
                <div className="text-lg font-bold text-slate-900">{progress.streak_days}d</div>
                <div className="mt-1 flex items-center justify-end gap-2">
                  <Badge variant={progress.streak_freeze_tokens > 0 ? 'brand' : 'neutral'}>
                    Shield {progress.streak_freeze_tokens}/1
                  </Badge>
                </div>
                <div className="text-[11px] text-slate-500">{progress.last_active_day ? `Last: ${progress.last_active_day}` : '—'}</div>
                <div className="text-[11px] text-slate-500 mt-1">Shield auto-protects 1 missed day per week (earned from quest claims).</div>
              </div>
            </div>
            <div className="mt-3">
              <div className="flex justify-between text-[11px] text-slate-500 mb-1">
                <span>XP</span>
                <span>
                  {xpInLevel}/100 · next in {xpToNext}
                </span>
              </div>
              <ProgressBar value={xpInLevel} max={100} />
            </div>
          </div>

          <div className="pt-2 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => navigate('/settings')}>
              Settings
            </Button>
            <Button variant="secondary" onClick={() => navigate('/home')}>
              Lab Home
            </Button>
          </div>

          <div className="pt-2">
            <Button
              variant="destructive"
              onClick={() => {
                playSfx('click');
                vibrate(20);
                setToken(null);
                navigate('/play', { replace: true });
              }}
            >
              Logout
            </Button>
            <div className="text-[11px] text-slate-500 mt-2">Logging out clears your local token and starts a new guest session next time.</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Badge Cabinet</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-600">Badges are permanent. Earn them via quests and Beat This wins.</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {BADGE_DEFS.map((b) => {
              const have = unlocked.has(b.id);
              const cur = Number(progress[b.progressKey] ?? 0);
              const pct = b.goal > 0 ? Math.max(0, Math.min(1, cur / b.goal)) : 0;
              return (
                <div key={b.id} className={`p-3 rounded-xl border ${have ? 'border-brand-200 bg-brand-50' : 'border-slate-200 bg-white'}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-extrabold text-slate-900 truncate">{b.name}</div>
                      <div className="text-xs text-slate-600">{b.desc}</div>
                      <div className="text-[11px] text-slate-500 font-mono mt-1">{b.id}</div>
                    </div>
                    <Badge variant={have ? 'success' : 'neutral'} className="shrink-0">
                      {have ? 'UNLOCKED' : `${Math.min(cur, b.goal)}/${b.goal}`}
                    </Badge>
                  </div>
                  <div className="mt-2">
                    <ProgressBar value={pct * 100} max={100} />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account upgrade</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="text-sm text-slate-600">Optional: connect Discord in Settings to upgrade a guest to a real account.</div>
          <Button variant="secondary" onClick={() => navigate('/settings')}>
            Open Settings
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
