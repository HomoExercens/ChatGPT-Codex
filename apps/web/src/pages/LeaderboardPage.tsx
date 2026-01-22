import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Trophy } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import type { Mode } from '../api/types';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';

type LeaderboardRow = {
  user_id: string;
  display_name: string;
  is_guest: boolean;
  elo: number;
  games_played: number;
};

export const LeaderboardPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const [mode, setMode] = useState<Mode>('1v1');

  const title = useMemo(() => (lang === 'ko' ? '리더보드' : 'Leaderboard'), [lang]);

  const { data: rows = [] } = useQuery({
    queryKey: ['leaderboard', mode],
    queryFn: () => apiFetch<LeaderboardRow[]>(`/api/leaderboard?mode=${encodeURIComponent(mode)}&limit=50`),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-12">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trophy size={18} className="text-brand-600" /> {title}
          </CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={mode === '1v1' ? 'primary' : 'secondary'}
              onClick={() => setMode('1v1')}
              aria-pressed={mode === '1v1'}
              type="button"
            >
              1v1
            </Button>
            <Button
              size="sm"
              variant={mode === 'team' ? 'primary' : 'secondary'}
              onClick={() => setMode('team')}
              aria-pressed={mode === 'team'}
              type="button"
            >
              Team (3v3)
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {rows.length === 0 ? (
            <div className="p-4 text-sm text-slate-500">{lang === 'ko' ? '데이터 없음' : 'No data yet.'}</div>
          ) : (
            <div className="divide-y divide-slate-100">
              {rows.map((r, idx) => (
                <button
                  key={r.user_id}
                  type="button"
                  onClick={() => navigate(`/profile/${encodeURIComponent(r.user_id)}?mode=${encodeURIComponent(mode)}`)}
                  className="w-full text-left p-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Badge variant="neutral" className="font-mono">
                      #{idx + 1}
                    </Badge>
                    <div className="font-bold text-slate-800">{r.display_name}</div>
                    {r.is_guest ? <Badge variant="neutral">GUEST</Badge> : null}
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <div className="text-xs text-slate-500">Elo</div>
                      <div className="text-sm font-bold text-slate-800">{r.elo}</div>
                    </div>
                    <div className="text-right hidden sm:block">
                      <div className="text-xs text-slate-500">{lang === 'ko' ? '경기 수' : 'Games'}</div>
                      <div className="text-sm font-bold text-slate-800">{r.games_played}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

