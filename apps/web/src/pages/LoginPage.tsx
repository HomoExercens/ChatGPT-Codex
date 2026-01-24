import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button, Card, CardContent, CardHeader, CardTitle, Input, Slider, Switch } from '../components/ui';
import { TRANSLATIONS } from '../lib/translations';
import { apiFetch } from '../lib/api';
import { useAuthStore } from '../stores/auth';
import { useSettingsStore } from '../stores/settings';

type AuthResponse = { access_token: string; token_type: 'bearer' };

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);

  const lang = useSettingsStore((s) => s.language);
  const setLanguage = useSettingsStore((s) => s.setLanguage);
  const fontScale = useSettingsStore((s) => s.fontScale);
  const contrast = useSettingsStore((s) => s.contrast);
  const reduceMotion = useSettingsStore((s) => s.reduceMotion);
  const colorblind = useSettingsStore((s) => s.colorblind);
  const setFontScale = useSettingsStore((s) => s.setFontScale);
  const setContrast = useSettingsStore((s) => s.setContrast);
  const setReduceMotion = useSettingsStore((s) => s.setReduceMotion);
  const setColorblind = useSettingsStore((s) => s.setColorblind);

  const t = useMemo(() => TRANSLATIONS[lang].common, [lang]);
  const [username, setUsername] = useState('demo');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const doGuest = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await apiFetch<AuthResponse>('/api/auth/guest', { method: 'POST' });
      setToken(resp.access_token);
      navigate('/play');
    } catch (e) {
      setError(String(e));
    } finally {
      setIsLoading(false);
    }
  };

  const doDiscord = () => {
    const next = '/play';
    window.location.href = `/api/auth/discord/start?next=${encodeURIComponent(next)}`;
  };

  const doLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await apiFetch<AuthResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username }),
      });
      setToken(resp.access_token);
      navigate('/play');
    } catch (e) {
      setError(String(e));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-bg text-fg">
      <div className="w-full max-w-3xl grid grid-cols-1 md:grid-cols-12 gap-6">
        <Card className="md:col-span-7">
          <CardHeader>
            <CardTitle>{t.loginTitle}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted">{t.loginSubtitle}</p>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setLanguage(lang === 'ko' ? 'en' : 'ko')}>
                {lang === 'ko' ? 'ENG' : '한글'}
              </Button>
            </div>

            <div className="grid grid-cols-1 gap-3">
              <Input
                label={t.username}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="demo"
                autoComplete="username"
              />
              {error ? <div className="text-xs text-danger-500">{error}</div> : null}
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              <Button onClick={doLogin} isLoading={isLoading}>
                {t.login}
              </Button>
              <Button onClick={doGuest} variant="secondary" isLoading={isLoading}>
                {t.continueAsGuest}
              </Button>
              <Button onClick={doDiscord} variant="secondary" isLoading={isLoading}>
                {lang === 'ko' ? 'Discord로 계속' : 'Continue with Discord'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-5">
          <CardHeader>
            <CardTitle>{t.accessibility}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-bold text-muted uppercase tracking-wider">{t.fontScale}</span>
                <span className="text-xs font-mono text-muted/70">{fontScale.toFixed(2)}x</span>
              </div>
              <Slider min={0.9} max={1.3} step={0.05} value={fontScale} onChange={(e) => setFontScale(Number(e.target.value))} />
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-bold text-muted uppercase tracking-wider">{t.contrast}</span>
                <span className="text-xs font-mono text-muted/70">{contrast.toFixed(2)}x</span>
              </div>
              <Slider min={1} max={1.4} step={0.05} value={contrast} onChange={(e) => setContrast(Number(e.target.value))} />
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-muted uppercase tracking-wider">{t.reduceMotion}</span>
              <Switch label={t.reduceMotion} checked={reduceMotion} onCheckedChange={setReduceMotion} />
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-muted uppercase tracking-wider">{t.colorblind}</span>
              <Switch label={t.colorblind} checked={colorblind} onCheckedChange={setColorblind} />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
