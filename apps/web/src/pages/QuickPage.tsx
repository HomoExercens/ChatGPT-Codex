import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { readShareVariants } from '../lib/shareVariants';
import type { BlueprintOut, Mode, QueueResponse } from '../api/types';
import { useSettingsStore } from '../stores/settings';

export const QuickPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const lang = useSettingsStore((s) => s.language);
  const [step, setStep] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const buildCode = useMemo(() => (params.get('import') || '').trim() || null, [params]);
  const mode = useMemo(() => {
    const raw = (params.get('mode') as Mode | null) ?? '1v1';
    return raw === 'team' ? 'team' : '1v1';
  }, [params]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setError(null);
      if (!buildCode) {
        setError(lang === 'ko' ? 'build_code(import) 파라미터가 없습니다.' : 'Missing import build_code.');
        return;
      }
      try {
        setStep(lang === 'ko' ? '빌드 가져오는 중…' : 'Importing build…');
        const imported = await apiFetch<BlueprintOut>('/api/blueprints/import', {
          method: 'POST',
          body: JSON.stringify({ build_code: buildCode, name: 'Imported Build (Quick Battle)' }),
        });
        if (cancelled) return;

        setStep(lang === 'ko' ? '제출하는 중…' : 'Submitting…');
        const submitted = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(imported.id)}/submit`, {
          method: 'POST',
          body: JSON.stringify({}),
        });
        if (cancelled) return;

        setStep(lang === 'ko' ? '매치 생성 중…' : 'Queueing match…');
        const queued = await apiFetch<QueueResponse>('/api/ranked/queue', {
          method: 'POST',
          body: JSON.stringify({ blueprint_id: submitted.id, seed_set_count: 1, ...readShareVariants() }),
        });
        if (cancelled) return;

        navigate(`/ranked?mode=${encodeURIComponent(mode)}&match_id=${encodeURIComponent(queued.match_id)}&auto=1`, {
          replace: true,
        });
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [buildCode, lang, mode, navigate]);

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-4">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle>{lang === 'ko' ? '빠른 시작' : 'Quick Start'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? (
            <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              <div className="font-mono break-words">{error}</div>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" onClick={() => navigate('/home', { replace: true })} type="button">
                  {lang === 'ko' ? '홈으로' : 'Go Home'}
                </Button>
                <Button variant="secondary" onClick={() => navigate('/gallery', { replace: true })} type="button">
                  {lang === 'ko' ? '갤러리' : 'Gallery'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-600">{step || (lang === 'ko' ? '준비 중…' : 'Starting…')}</div>
          )}
          <div className="text-xs text-slate-400 break-all">
            mode: {mode}
            {buildCode ? ` · import: ${buildCode.slice(0, 18)}…` : ''}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
