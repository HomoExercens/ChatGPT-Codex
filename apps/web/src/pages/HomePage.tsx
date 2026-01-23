import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, ArrowRight, Clock, Sparkles, TrendingUp, Trophy, Users, Zap } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from '../components/ui';
import { apiFetch } from '../lib/api';
import { getExperimentVariant, useExperiments } from '../lib/experiments';
import { useMetaFlags } from '../lib/flags';
import { useLabsEnabled } from '../lib/labs';
import { readShareVariants } from '../lib/shareVariants';
import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import type { HomeSummary } from '../types';
import { PATCH_NOTES } from '../domain/constants';
import type {
  BlueprintOut,
  BuildOfDay,
  ClaimQuestOut,
  ClipFeedOut,
  FeaturedItem,
  QueueResponse,
  QuestsTodayOut,
  WeeklyTheme,
} from '../api/types';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].common;
  const { data: experiments } = useExperiments();
  const primaryHomeCta = useMemo(() => {
    const v = getExperimentVariant(experiments, 'quick_battle_default', 'quick_battle');
    return v === 'watch_clips' ? 'watch_clips' : 'quick_battle';
  }, [experiments]);

  const { data: flags } = useMetaFlags();
  const demoMode = Boolean(flags?.demo_mode);
  const labsEnabled = useLabsEnabled();

  const { data: summary } = useQuery({
    queryKey: ['homeSummary'],
    queryFn: () => apiFetch<HomeSummary>('/api/home/summary'),
  });

  const { data: weekly } = useQuery({
    queryKey: ['weeklyTheme'],
    queryFn: () => apiFetch<WeeklyTheme>('/api/meta/weekly'),
    staleTime: 60_000,
  });

  const { data: season } = useQuery({
    queryKey: ['season'],
    queryFn: () => apiFetch<{ season_name: string }>('/api/meta/season'),
    staleTime: 60 * 60 * 1000,
  });

  const user = summary?.user;
  const recent = summary?.recent_matches ?? [];

  const [communityTab, setCommunityTab] = useState<'for_you' | 'following'>('for_you');

  const { data: clipsPreview } = useQuery({
    queryKey: ['homeClipsPreview'],
    queryFn: () => apiFetch<ClipFeedOut>('/api/clips/feed?mode=1v1&sort=trending&algo=v2&limit=3'),
    staleTime: 30_000,
  });

  const { data: questsToday } = useQuery({
    queryKey: ['questsToday'],
    queryFn: () => apiFetch<QuestsTodayOut>('/api/quests/today'),
    staleTime: 5_000,
  });

  const { data: featured } = useQuery({
    queryKey: ['featuredActive'],
    queryFn: () => apiFetch<FeaturedItem[]>('/api/featured?active=true'),
    staleTime: 30_000,
  });

  const { data: buildOfDay } = useQuery({
    queryKey: ['homeBuildOfDay'],
    queryFn: () => apiFetch<BuildOfDay>('/api/gallery/build_of_day?mode=1v1'),
    staleTime: 60_000,
  });
  const bodBlueprint = buildOfDay?.blueprint ?? null;

  const featuredByKind = useMemo(() => {
    const out: Partial<Record<'clip' | 'build' | 'challenge' | 'user', FeaturedItem>> = {};
    for (const it of featured ?? []) {
      const k = it.kind;
      if (k === 'clip' || k === 'build' || k === 'challenge' || k === 'user') {
        if (!out[k]) out[k] = it;
      }
    }
    return out;
  }, [featured]);

  const claimQuestMutation = useMutation({
    mutationFn: async (assignmentId: string) =>
      apiFetch<ClaimQuestOut>('/api/quests/claim', {
        method: 'POST',
        body: JSON.stringify({ assignment_id: assignmentId }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['questsToday'] });
      await queryClient.invalidateQueries({ queryKey: ['profile'] });
    },
  });

  const forkBuildOfDayMutation = useMutation({
    mutationFn: async (blueprintId: string) =>
      apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(blueprintId)}/fork`, {
        method: 'POST',
        body: JSON.stringify({ note: 'home_build_of_day' }),
      }),
    onSuccess: async (bp) => {
      await queryClient.invalidateQueries({ queryKey: ['blueprints'] });
      if (bp?.id) navigate(`/forge/${encodeURIComponent(bp.id)}`);
    },
  });

  const challengeBuildOfDayMutation = useMutation({
    mutationFn: async (blueprintId: string) =>
      apiFetch<{ challenge_id: string }>('/api/challenges', {
        method: 'POST',
        body: JSON.stringify({ kind: 'build', target_blueprint_id: blueprintId }),
      }),
    onSuccess: async (out) => {
      const id = (out as any)?.challenge_id;
      if (typeof id === 'string' && id) navigate(`/challenge/${encodeURIComponent(id)}`);
    },
  });

  const { data: activityPreview } = useQuery({
    queryKey: ['homeActivityPreview'],
    queryFn: () => apiFetch<{ items: any[] }>('/api/feed/activity?limit=5'),
    staleTime: 10_000,
  });

  const quickBattleMutation = useMutation({
    mutationFn: async () => {
      const blueprints = await apiFetch<BlueprintOut[]>('/api/blueprints');
      const submitted = blueprints
        .filter((b) => b.status === 'submitted' && b.mode === '1v1')
        .sort((a, b) => {
          const ta = new Date(a.submitted_at ?? a.updated_at).getTime();
          const tb = new Date(b.submitted_at ?? b.updated_at).getTime();
          return tb - ta;
        });

      let blueprintId = submitted[0]?.id ?? '';
      if (!blueprintId) {
        const bod = await apiFetch<BuildOfDay>('/api/gallery/build_of_day?mode=1v1');
        const sourceId = bod.blueprint?.blueprint_id;
        if (!sourceId) throw new Error('No starter build available');
        const forked = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(sourceId)}/fork`, {
          method: 'POST',
          body: JSON.stringify({ name: `${bod.blueprint?.name ?? 'Build'} (Quick Battle)` }),
        });
        const submittedFork = await apiFetch<BlueprintOut>(`/api/blueprints/${encodeURIComponent(forked.id)}/submit`, {
          method: 'POST',
          body: JSON.stringify({}),
        });
        blueprintId = submittedFork.id;
      }

      const queued = await apiFetch<QueueResponse>('/api/ranked/queue', {
        method: 'POST',
        body: JSON.stringify({ blueprint_id: blueprintId, seed_set_count: 1, ...readShareVariants() }),
      });
      return queued;
    },
    onSuccess: async (queued) => {
      await queryClient.invalidateQueries({ queryKey: ['matches'] });
      await queryClient.invalidateQueries({ queryKey: ['homeSummary'] });
      navigate(`/ranked?mode=1v1&match_id=${encodeURIComponent(queued.match_id)}&auto=1`);
    },
  });

  const [showTutorial, setShowTutorial] = useState(false);
  useEffect(() => {
    try {
      const seen = localStorage.getItem('neuroleague.tutorial.growth') === '1';
      if (!seen) setShowTutorial(true);
    } catch {
      // ignore
    }
  }, []);

  const dismissTutorial = () => {
    setShowTutorial(false);
    try {
      localStorage.setItem('neuroleague.tutorial.growth', '1');
    } catch {
      // ignore
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
      <div className="md:col-span-12">
        <div className="relative overflow-hidden bg-gradient-to-r from-brand-600 to-accent-500 rounded-3xl p-6 md:p-10 text-white shadow-xl">
          <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Badge variant="brand" className="bg-white/20 text-white border-transparent">
                  {season?.season_name ?? `${t.season}`}
                </Badge>
                <span className="text-white/80 text-sm font-medium">{t.week} {weekly?.week_id ?? '—'}</span>
              </div>
              <h1 className="text-3xl md:text-4xl font-bold mb-2">
                {t.welcome}, {user?.display_name ?? '—'}
              </h1>
              <p className="text-brand-100 max-w-xl">{weekly?.name ? `${t.aiMessage} • ${weekly.name}` : t.aiMessage}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                {demoMode ? (
                  <Button
                    onClick={() => navigate('/demo')}
                    size="lg"
                    className="bg-white text-brand-700 hover:bg-brand-50 border-0 shadow-lg"
                    type="button"
                  >
                    {lang === 'ko' ? 'Play Demo Run (5 min)' : 'Play Demo Run (5 min)'}
                  </Button>
                ) : null}
                {primaryHomeCta === 'watch_clips' ? (
                  <>
                    <Button
                      onClick={() => navigate('/clips')}
                      size="lg"
                      className="bg-white text-brand-700 hover:bg-brand-50 border-0 shadow-lg"
                      type="button"
                    >
                      {t.watchClips}
                    </Button>
                    <Button
                      onClick={() => quickBattleMutation.mutate()}
                      variant="secondary"
                      size="lg"
                      className="bg-brand-700/50 text-white border-white/20 hover:bg-brand-700/70"
                      disabled={quickBattleMutation.isPending}
                      type="button"
                    >
                      {quickBattleMutation.isPending ? (lang === 'ko' ? '매치 생성 중…' : 'Queueing…') : t.quickBattle}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      onClick={() => quickBattleMutation.mutate()}
                      size="lg"
                      className="bg-white text-brand-700 hover:bg-brand-50 border-0 shadow-lg"
                      disabled={quickBattleMutation.isPending}
                      type="button"
                    >
                      {quickBattleMutation.isPending ? (lang === 'ko' ? '매치 생성 중…' : 'Queueing…') : t.quickBattle}
                    </Button>
                    <Button
                      onClick={() => navigate('/clips')}
                      variant="secondary"
                      size="lg"
                      className="bg-brand-700/50 text-white border-white/20 hover:bg-brand-700/70"
                      type="button"
                    >
                      {t.watchClips}
                    </Button>
                  </>
                )}
                {labsEnabled ? (
                  <Button
                    variant="secondary"
                    size="lg"
                    className="bg-white/10 text-white border-white/20 hover:bg-white/15"
                    onClick={() => navigate('/training')}
                    type="button"
                  >
                    {demoMode ? (lang === 'ko' ? '나중에 (훈련)' : 'Training (Later)') : t.train}
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="bg-white/10 backdrop-blur-md rounded-2xl p-4 md:p-6 border border-white/10 min-w-[200px]">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-yellow-400 rounded-lg text-yellow-900">
                  <Trophy size={20} />
                </div>
                <div>
                  <div className="text-xs text-brand-100 uppercase font-bold">{t.currentRank}</div>
                  <div className="font-bold text-xl">{user?.division ?? '—'}</div>
                </div>
              </div>
              <div className="flex justify-between items-end">
                <div>
                  <div className="text-2xl font-bold">{user?.elo ?? 0}</div>
                  <div className="text-xs text-green-300 font-medium">+0 {t.eloChange}</div>
                </div>
                <TrendingUp className="text-green-300 mb-1" size={20} />
              </div>
            </div>
          </div>

          <div className="absolute top-0 right-0 -mr-20 -mt-20 w-96 h-96 bg-white/5 rounded-full blur-3xl pointer-events-none"></div>
        </div>
      </div>

      {showTutorial ? (
        <div className="fixed bottom-24 md:bottom-8 right-4 md:right-8 z-50 w-[320px] max-w-[calc(100vw-2rem)]">
          <div className="rounded-2xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
            <div className="p-4 bg-gradient-to-r from-brand-600 to-accent-500 text-white">
              <div className="flex items-center gap-2 font-extrabold">
                <Sparkles size={16} /> {lang === 'ko' ? '60초 성장 루프' : '60-second Loop'}
              </div>
              <div className="text-xs text-white/80 mt-1">
                {lang === 'ko'
                  ? 'Quick Battle → Replay → Share → Remix'
                  : 'Quick Battle → Replay → Share → Remix'}
              </div>
            </div>
            <div className="p-4 space-y-3">
              <div className="text-xs text-slate-600 leading-relaxed">
                {lang === 'ko'
                  ? '훈련 몰라도 괜찮아요. 1번만 돌려보고, 베스트 클립을 공유해보세요.'
                  : "No training required. Run one match, then share your best clip."}
              </div>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={() => {
                    dismissTutorial();
                    quickBattleMutation.mutate();
                  }}
                  disabled={quickBattleMutation.isPending}
                  type="button"
                >
                  {t.quickBattle}
                </Button>
                <Button className="flex-1" variant="secondary" onClick={dismissTutorial} type="button">
                  {lang === 'ko' ? '나중에' : 'Later'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="md:col-span-8 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles size={18} className="text-brand-600" /> {lang === 'ko' ? '오늘의 퀘스트' : "Today's Quests"}
            </CardTitle>
            <Badge variant="neutral">{questsToday?.daily_period_key ?? '—'}</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-xs text-slate-600">
              {lang === 'ko'
                ? '서버 기준(KST)으로 집계됩니다. 완료하면 코스메틱 배지를 획득합니다.'
                : 'Tracked server-side (KST). Complete quests to earn cosmetic badges.'}
            </div>

            <div className="grid grid-cols-1 gap-2">
              {(questsToday?.daily ?? []).map((a) => {
                const goal = a.quest.goal_count || 1;
                const prog = a.progress_count || 0;
                const pct = Math.min(100, Math.round((prog / goal) * 100));
                const claimed = Boolean(a.claimed_at);
                return (
                  <div key={a.assignment_id} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge variant={claimed ? 'success' : a.claimable ? 'warning' : 'neutral'}>
                            {claimed ? 'claimed' : a.claimable ? 'ready' : 'in progress'}
                          </Badge>
                          <span className="font-bold text-slate-800 truncate">{a.quest.title}</span>
                        </div>
                        <div className="mt-1 text-xs text-slate-500 truncate">{a.quest.description}</div>
                        <div className="mt-2 h-2 rounded-full bg-slate-200 overflow-hidden">
                          <div className="h-2 bg-brand-600" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500 font-mono">
                          {prog}/{goal} · reward {a.quest.reward_cosmetic_id}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        {a.claimable && !claimed ? (
                          <Button
                            type="button"
                            onClick={() => claimQuestMutation.mutate(a.assignment_id)}
                            isLoading={claimQuestMutation.isPending}
                            disabled={claimQuestMutation.isPending}
                          >
                            Claim
                          </Button>
                        ) : (
                          <Button type="button" variant="secondary" onClick={() => quickBattleMutation.mutate()}>
                            {lang === 'ko' ? '오늘 1판' : 'Play 1'}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {questsToday?.daily?.length ? null : (
                <div className="text-sm text-slate-500">{lang === 'ko' ? '활성 퀘스트가 없습니다.' : 'No quests yet.'}</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock size={18} className="text-slate-400" />
              {t.recentMatches}
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => navigate('/replay')}>
              {t.viewAll}
            </Button>
          </CardHeader>
          {recent.length === 0 ? (
            <CardContent>
              <div className="text-sm text-slate-500">No matches yet. Enter Ranked to generate your first replay.</div>
            </CardContent>
          ) : (
            <div className="divide-y divide-slate-100">
              {recent.map((match) => (
                <div
                  key={match.id}
                  onClick={() => navigate(`/replay/${match.id}`)}
                  className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors group cursor-pointer"
                >
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-1.5 h-12 rounded-full ${match.result === 'win' ? 'bg-green-500' : 'bg-red-400'}`}
                    ></div>
                    <div>
                      <div className="font-bold text-slate-800">{match.opponent}</div>
                      <div className="text-xs text-slate-500 flex items-center gap-1">
                        {match.result === 'win' ? t.victory : t.defeat} • {match.duration} •{' '}
                        <span className="text-slate-400">{match.date}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="hidden sm:block text-right">
                      <div className="text-xs font-semibold text-slate-400 uppercase">{t.archetype}</div>
                      <div className="text-sm font-medium text-slate-700">{match.opponent_archetype}</div>
                    </div>
                    <Badge variant={match.result === 'win' ? 'success' : 'error'}>
                      {match.elo_change > 0 ? '+' : ''}
                      {match.elo_change} Elo
                    </Badge>
                    <Button size="icon" variant="ghost" className="opacity-0 group-hover:opacity-100 transition-opacity">
                      <ArrowRight size={16} />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="md:col-span-4 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles size={18} className="text-accent-600" /> Featured
            </CardTitle>
            <Badge variant="neutral">{featured?.length ? `${featured.length}` : '—'}</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {featuredByKind.clip ? (
              <a
                className="block rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50"
                href={featuredByKind.clip.href}
              >
                <div className="text-xs text-slate-500 font-mono">Top Clip</div>
                <div className="text-sm font-bold text-slate-800 truncate">
                  {featuredByKind.clip.title_override || featuredByKind.clip.target_id}
                </div>
              </a>
            ) : null}
            {featuredByKind.build ? (
              <a
                className="block rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50"
                href={featuredByKind.build.href}
              >
                <div className="text-xs text-slate-500 font-mono">Build</div>
                <div className="text-sm font-bold text-slate-800 truncate">
                  {featuredByKind.build.title_override || featuredByKind.build.target_id}
                </div>
              </a>
            ) : null}
            {featuredByKind.challenge ? (
              <a
                className="block rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50"
                href={featuredByKind.challenge.href}
              >
                <div className="text-xs text-slate-500 font-mono">Daily Challenge</div>
                <div className="text-sm font-bold text-slate-800 truncate">
                  {featuredByKind.challenge.title_override || featuredByKind.challenge.target_id}
                </div>
              </a>
            ) : (
              <div className="text-sm text-slate-500">{lang === 'ko' ? '오늘의 챌린지가 없습니다.' : 'No daily challenge yet.'}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trophy size={18} className="text-brand-600" /> {lang === 'ko' ? '오늘의 빌드' : 'Build of the Day'}
            </CardTitle>
            <Badge variant="neutral">{buildOfDay?.date ?? '—'}</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {bodBlueprint ? (
              <>
                <div className="min-w-0">
                  <div className="text-sm font-bold text-slate-800 truncate">{bodBlueprint.name}</div>
                  <div className="text-xs text-slate-500 truncate">{bodBlueprint.creator?.display_name ?? '—'}</div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(bodBlueprint.synergy_tags ?? []).slice(0, 6).map((t) => (
                    <Badge key={t} variant="info">
                      {t}
                    </Badge>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => (window.location.href = `/s/build/${encodeURIComponent(bodBlueprint.blueprint_id)}`)}
                  >
                    {lang === 'ko' ? '보기' : 'View'}
                  </Button>
                  <Button
                    onClick={() => forkBuildOfDayMutation.mutate(bodBlueprint.blueprint_id)}
                    isLoading={forkBuildOfDayMutation.isPending}
                  >
                    {lang === 'ko' ? '리믹스' : 'Remix'}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => challengeBuildOfDayMutation.mutate(bodBlueprint.blueprint_id)}
                    isLoading={challengeBuildOfDayMutation.isPending}
                  >
                    {lang === 'ko' ? '도전 만들기' : 'Challenge'}
                  </Button>
                </div>
              </>
            ) : (
              <div className="text-sm text-slate-500">{lang === 'ko' ? '오늘의 빌드가 없습니다.' : 'No build of the day yet.'}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{lang === 'ko' ? '리더보드' : 'Leaderboard'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm text-slate-600">
              {lang === 'ko' ? '상위 연구원들의 Elo와 경기 수를 확인하세요.' : 'See top players by Elo and games played.'}
            </div>
            <Button variant="secondary" onClick={() => navigate('/leaderboard')}>
              {lang === 'ko' ? '리더보드 열기' : 'Open Leaderboard'}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users size={18} className="text-brand-600" /> {lang === 'ko' ? '커뮤니티' : 'Community'}
            </CardTitle>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={communityTab === 'for_you' ? 'primary' : 'secondary'}
                onClick={() => setCommunityTab('for_you')}
                type="button"
              >
                {lang === 'ko' ? '클립' : 'Clips'}
              </Button>
              <Button
                size="sm"
                variant={communityTab === 'following' ? 'primary' : 'secondary'}
                onClick={() => setCommunityTab('following')}
                type="button"
              >
                {lang === 'ko' ? '팔로잉' : 'Following'}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {communityTab === 'for_you' ? (
              <>
                {clipsPreview?.items?.length ? (
                  <div className="space-y-2">
                    {clipsPreview.items.slice(0, 3).map((c) => (
                      <button
                        key={c.replay_id}
                        type="button"
                        onClick={() => navigate(`/replay/${c.match_id}`)}
                        className="w-full text-left rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50"
                      >
                        <div className="text-sm font-bold text-slate-800 truncate">{c.blueprint_name ?? 'Build'}</div>
                        <div className="text-xs text-slate-500 truncate">{c.author?.display_name ?? '—'}</div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">{lang === 'ko' ? '클립이 없습니다.' : 'No clips yet.'}</div>
                )}
                <Button variant="secondary" onClick={() => navigate('/clips')} type="button">
                  {lang === 'ko' ? '클립 피드 열기' : 'Open Clips Feed'}
                </Button>
              </>
            ) : (
              <>
                {Array.isArray(activityPreview?.items) && activityPreview.items.length ? (
                  <div className="space-y-2">
                    {activityPreview.items.slice(0, 5).map((it: any) => (
                      <button
                        key={String(it.id)}
                        type="button"
                        onClick={() => navigate(String(it.href || `/profile/${it.actor?.user_id}`))}
                        className="w-full text-left rounded-xl border border-slate-200 bg-white px-3 py-2 hover:bg-slate-50"
                      >
                        <div className="text-sm font-bold text-slate-800 truncate">{String(it.actor?.display_name || '—')}</div>
                        <div className="text-xs text-slate-500 truncate">{String(it.type || '')}</div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">
                    {lang === 'ko' ? '팔로우한 연구원이 없거나 활동이 없습니다.' : 'No activity yet.'}
                  </div>
                )}
                <Button variant="secondary" onClick={() => navigate('/social')} type="button">
                  {lang === 'ko' ? '팔로잉 피드 열기' : 'Open Following Feed'}
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="border-accent-200 bg-gradient-to-b from-white to-brand-50/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-accent-700">
              <Zap size={18} /> {t.metaSnapshot}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <div className="font-mono text-sm font-bold text-slate-400">#{i}</div>
                  <div className="text-sm font-bold text-slate-700">Mech Rush</div>
                </div>
                <div className="text-xs font-medium text-red-500">54.2% WR</div>
              </div>
            ))}
            <div className="pt-2">
              <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl flex items-start gap-3">
                <AlertCircle size={16} className="text-blue-500 mt-0.5 shrink-0" />
                <p className="text-xs text-blue-700 leading-relaxed">{t.metaTip}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.patchNotes}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {PATCH_NOTES.map((note, idx) => (
              <div key={idx} className="pb-3 border-b border-slate-100 last:border-0 last:pb-0">
                <div className="flex justify-between items-baseline mb-1">
                  <span className="font-bold text-sm text-slate-800">{note.version}</span>
                  <span className="text-[10px] text-slate-400">{note.date}</span>
                </div>
                <p className="text-xs text-slate-600 line-clamp-2">{note.title}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
