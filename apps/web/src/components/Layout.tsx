import React, { useMemo } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Bell, Hammer, Play, User } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { TRANSLATIONS } from '../lib/translations';
import { apiFetch } from '../lib/api';
import { useSettingsStore } from '../stores/settings';
import type { NotificationsResponse } from '../api/types';

type TabItem = {
  to: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  badge?: number;
};

function titleForPath(pathname: string, t: Record<string, string>): string {
  if (pathname.startsWith('/forge')) return t.forge ?? 'Forge';
  if (pathname.startsWith('/inbox')) return t.inbox ?? 'Inbox';
  if (pathname.startsWith('/me')) return t.profile ?? 'Me';
  if (pathname.startsWith('/settings')) return t.settings ?? 'Settings';
  if (pathname.startsWith('/home')) return t.dashboard ?? 'Home';
  return t.play ?? 'Play';
}

export const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const lang = useSettingsStore((s) => s.language);
  const t = TRANSLATIONS[lang].nav as unknown as Record<string, string>;

  const isPlay = location.pathname === '/play';

  const { data: notifications } = useQuery({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => apiFetch<NotificationsResponse>('/api/notifications?limit=1'),
    staleTime: 10_000,
  });
  const unreadCount = notifications?.unread_count ?? 0;

  const tabs: TabItem[] = useMemo(
    () => [
      { to: '/play', icon: Play, label: t.play ?? 'Play' },
      { to: '/forge', icon: Hammer, label: t.forge ?? 'Forge' },
      { to: '/inbox', icon: Bell, label: t.inbox ?? 'Inbox', badge: unreadCount },
      { to: '/me', icon: User, label: t.profile ?? 'Me' },
    ],
    [t.forge, t.inbox, t.play, t.profile, unreadCount]
  );

  const title = useMemo(() => titleForPath(location.pathname, t), [location.pathname, t]);

  return (
    <div className="min-h-[100dvh] bg-slate-50 flex flex-col font-sans">
      {!isPlay ? (
        <header className="sticky top-0 z-40 bg-white/85 backdrop-blur border-b border-slate-200 pt-safe">
          <div className="h-14 px-4 flex items-center justify-between">
            <button
              type="button"
              className="flex items-center gap-2 text-slate-900"
              onClick={() => navigate('/play')}
              aria-label="Go to Play"
            >
              <div className="w-8 h-8 bg-brand-600 rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-brand-500/25">
                N
              </div>
              <div className="hidden sm:block font-extrabold tracking-tight">NeuroLeague</div>
            </button>

            <div className="text-sm font-extrabold tracking-tight text-slate-900">{title}</div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="relative w-10 h-10 rounded-xl bg-slate-100 hover:bg-slate-200 transition-colors flex items-center justify-center text-slate-700"
                onClick={() => navigate('/inbox')}
                aria-label="Open Inbox"
              >
                <Bell size={18} />
                {unreadCount > 0 ? (
                  <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full border-2 border-white flex items-center justify-center">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                ) : null}
              </button>
              <button
                type="button"
                className="w-10 h-10 rounded-xl bg-slate-100 hover:bg-slate-200 transition-colors flex items-center justify-center text-slate-700"
                onClick={() => navigate('/me')}
                aria-label="Open Profile"
              >
                <User size={18} />
              </button>
            </div>
          </div>
        </header>
      ) : null}

      <main className={isPlay ? 'flex-1 min-h-0' : 'flex-1 w-full max-w-7xl mx-auto px-4 py-4 pb-28'}>
        <Outlet />
      </main>

      <nav className="fixed bottom-0 inset-x-0 z-50 bg-slate-950/92 backdrop-blur border-t border-white/10 pb-safe">
        <div className="h-[var(--nl-tabbar-h)] px-2 flex items-center justify-around">
          {tabs.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `relative flex flex-col items-center justify-center gap-1 w-20 h-[calc(var(--nl-tabbar-h)-8px)] rounded-2xl transition-colors ${
                  isActive ? 'text-white bg-white/10' : 'text-white/70 hover:text-white'
                }`
              }
            >
              <item.icon size={20} />
              <span className="text-[10px] font-semibold">{item.label}</span>
              {item.badge && item.badge > 0 ? (
                <span className="absolute top-2 right-4 min-w-[18px] h-[18px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {item.badge > 99 ? '99+' : item.badge}
                </span>
              ) : null}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
};

