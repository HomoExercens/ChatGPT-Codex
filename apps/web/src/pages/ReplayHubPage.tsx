import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PlaySquare } from 'lucide-react';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { MatchRow } from '../api/types';

export const ReplayHubPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].nav;

  const { data: matches = [], isLoading, error } = useQuery({
    queryKey: ['matches'],
    queryFn: () => apiFetch<MatchRow[]>('/api/matches'),
  });

  const ready = matches.filter(
    (m): m is MatchRow & { result: 'win' | 'loss' | 'draw' } => m.status === 'done' && m.result !== null
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PlaySquare size={18} className="text-brand-600" /> {t.replay}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? <div className="text-sm text-slate-500">Loading…</div> : null}
        {error ? <div className="text-sm text-red-600">{String(error)}</div> : null}
        {ready.length === 0 && !isLoading ? <div className="text-sm text-slate-500">No replays yet.</div> : null}

        <div className="divide-y divide-slate-100 -mx-5">
          {ready.map((m) => (
            <button
              key={m.id}
              type="button"
              className="w-full px-5 py-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
              onClick={() => navigate(`/replay/${m.id}`)}
            >
              <div className="min-w-0 text-left">
                <div className="font-bold text-slate-800 truncate">{m.opponent}</div>
                <div className="text-xs text-slate-500 font-mono truncate">{m.id}</div>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="neutral">{m.mode === 'team' ? 'Team (3v3)' : '1v1'}</Badge>
                <Badge variant={m.result === 'win' ? 'success' : m.result === 'loss' ? 'error' : 'neutral'}>
                  {m.result}
                </Badge>
                <span className="text-sm font-bold text-slate-800">
                  {m.elo_change > 0 ? '+' : ''}
                  {m.elo_change}
                </span>
              </div>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
