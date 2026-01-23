import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Slider } from '../components/ui';
import { apiFetch } from '../lib/api';
import { TRANSLATIONS } from '../lib/translations';
import { useAuthStore } from '../stores/auth';
import { useSettingsStore } from '../stores/settings';

type Health = { status: string; ruleset_version: string };
type Me = { user_id: string; display_name: string; is_guest: boolean; discord_connected?: boolean; avatar_url?: string | null };

export const SettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].common;
  const setLanguage = useSettingsStore((s) => s.setLanguage);

  const fontScale = useSettingsStore((s) => s.fontScale);
  const contrast = useSettingsStore((s) => s.contrast);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const colorblind = useSettingsStore((s) => s.colorblind);
  const soundEnabled = useSettingsStore((s) => s.soundEnabled);
  const hapticsEnabled = useSettingsStore((s) => s.hapticsEnabled);
  const setFontScale = useSettingsStore((s) => s.setFontScale);
  const setContrast = useSettingsStore((s) => s.setContrast);
  const setReduceMotion = useSettingsStore((s) => s.setReduceMotion);
  const setColorblind = useSettingsStore((s) => s.setColorblind);
  const setSoundEnabled = useSettingsStore((s) => s.setSoundEnabled);
  const setHapticsEnabled = useSettingsStore((s) => s.setHapticsEnabled);

  const setToken = useAuthStore((s) => s.setToken);
  const token = useAuthStore((s) => s.token);

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiFetch<Health>('/api/health'),
    staleTime: 60_000,
  });

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiFetch<Me>('/api/auth/me'),
    staleTime: 30_000,
  });

  const connectDiscord = async () => {
    if (!token) return;
    const resp = await fetch(`/api/auth/discord/start?format=json&next=${encodeURIComponent('/me')}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) throw new Error(`discord_start_failed: ${resp.status}`);
    const json = (await resp.json()) as { authorize_url: string };
    window.location.href = json.authorize_url;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <Card className="lg:col-span-7">
        <CardHeader>
          <CardTitle>{t.accessibility}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setLanguage(lang === 'ko' ? 'en' : 'ko')}>
              {lang === 'ko' ? 'ENG' : '한글'}
            </Button>
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-slate-700">{t.fontScale}</span>
              <span className="text-xs font-mono text-slate-500">{fontScale.toFixed(2)}x</span>
            </div>
            <Slider min={0.9} max={1.3} step={0.05} value={fontScale} onChange={(e) => setFontScale(Number(e.target.value))} />
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-slate-700">{t.contrast}</span>
              <span className="text-xs font-mono text-slate-500">{contrast.toFixed(2)}x</span>
            </div>
            <Slider min={1} max={1.4} step={0.05} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">{t.reduceMotion}</span>
            <button
              type="button"
              className={`w-12 h-7 rounded-full border transition-colors ${reduceMotion ? 'bg-brand-600 border-brand-600' : 'bg-slate-200 border-slate-300'}`}
              role="switch"
              aria-checked={reduceMotion}
              onClick={() => setReduceMotion(!reduceMotion)}
            >
              <span className={`block w-5 h-5 bg-white rounded-full shadow transform transition-transform ${reduceMotion ? 'translate-x-5' : 'translate-x-1'}`} />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">{t.colorblind}</span>
            <button
              type="button"
              className={`w-12 h-7 rounded-full border transition-colors ${colorblind ? 'bg-brand-600 border-brand-600' : 'bg-slate-200 border-slate-300'}`}
              role="switch"
              aria-checked={colorblind}
              onClick={() => setColorblind(!colorblind)}
            >
              <span className={`block w-5 h-5 bg-white rounded-full shadow transform transition-transform ${colorblind ? 'translate-x-5' : 'translate-x-1'}`} />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">{lang === 'ko' ? '사운드' : 'Sound'}</span>
            <button
              type="button"
              className={`w-12 h-7 rounded-full border transition-colors ${soundEnabled ? 'bg-brand-600 border-brand-600' : 'bg-slate-200 border-slate-300'}`}
              role="switch"
              aria-checked={soundEnabled}
              onClick={() => setSoundEnabled(!soundEnabled)}
            >
              <span className={`block w-5 h-5 bg-white rounded-full shadow transform transition-transform ${soundEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">{lang === 'ko' ? '진동' : 'Haptics'}</span>
            <button
              type="button"
              className={`w-12 h-7 rounded-full border transition-colors ${hapticsEnabled ? 'bg-brand-600 border-brand-600' : 'bg-slate-200 border-slate-300'}`}
              role="switch"
              aria-checked={hapticsEnabled}
              onClick={() => setHapticsEnabled(!hapticsEnabled)}
            >
              <span className={`block w-5 h-5 bg-white rounded-full shadow transform transition-transform ${hapticsEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
            </button>
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-5">
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-xs text-slate-600">
            <div className="flex justify-between">
              <span>User</span>
              <span className="font-mono">{me?.user_id ?? '...'}</span>
            </div>
            <div className="flex justify-between">
              <span>Display</span>
              <span className="font-mono">{me?.display_name ?? '...'}</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">Discord</span>
            <Badge variant={me?.discord_connected ? 'success' : 'neutral'}>{me?.discord_connected ? 'connected' : 'not connected'}</Badge>
          </div>
          <Button variant="secondary" onClick={connectDiscord} disabled={!token || Boolean(me?.discord_connected)}>
            {lang === 'ko' ? 'Discord 연결' : 'Connect Discord'}
          </Button>
          <div className="text-[11px] text-slate-500">
            {lang === 'ko'
              ? '게스트는 Discord로 연결하면 계정으로 승격됩니다.'
              : 'Guests can upgrade by connecting Discord.'}
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-5">
        <CardHeader>
          <CardTitle>Dev</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-xs text-slate-600">
            <div className="flex justify-between">
              <span>API</span>
              <span className="font-mono">{health?.status ?? '...'}</span>
            </div>
            <div className="flex justify-between">
              <span>ruleset_version</span>
              <span className="font-mono">{health?.ruleset_version ?? '...'}</span>
            </div>
          </div>

          <Button
            variant="destructive"
            onClick={() => {
              setToken(null);
              navigate('/play');
            }}
          >
            {t.logout}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
