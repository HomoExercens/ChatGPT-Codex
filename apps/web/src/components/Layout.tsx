import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Bell,
  Clapperboard,
  FlaskConical,
  Hammer,
  HelpCircle,
  LayoutDashboard,
  LayoutGrid,
  MoreHorizontal,
  PlaySquare,
  Star,
  Trophy,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { TRANSLATIONS } from '../lib/translations';
import { useSettingsStore } from '../stores/settings';
import { apiFetch } from '../lib/api';
import type { HomeSummary } from '../types';

type NavItem = {
  to: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
};

export const Layout: React.FC = () => {
  const navigate = useNavigate();
  const lang = useSettingsStore((s) => s.language);
  const setLanguage = useSettingsStore((s) => s.setLanguage);
  const t = TRANSLATIONS[lang].nav;
  const tc = TRANSLATIONS[lang].common;

  const { data: home } = useQuery({
    queryKey: ['homeSummary'],
    queryFn: () => apiFetch<HomeSummary>('/api/home/summary'),
    staleTime: 15_000,
  });

  const navItems: NavItem[] = [
    { to: '/home', icon: LayoutDashboard, label: t.dashboard },
    { to: '/training', icon: FlaskConical, label: t.training },
    { to: '/forge', icon: Hammer, label: t.forge },
    { to: '/gallery', icon: LayoutGrid, label: t.gallery ?? 'Gallery' },
    { to: '/clips', icon: Clapperboard, label: t.clips ?? 'Clips' },
    { to: '/ranked', icon: Trophy, label: t.ranked },
    { to: '/tournament', icon: Star, label: t.tournament ?? 'Tournament' },
    { to: '/replay', icon: PlaySquare, label: t.replay },
    { to: '/analytics', icon: BarChart3, label: t.analytics },
  ];

  const mobileItems: NavItem[] = [
    navItems.find((i) => i.to === '/home')!,
    navItems.find((i) => i.to === '/training')!,
    navItems.find((i) => i.to === '/ranked')!,
    navItems.find((i) => i.to === '/replay')!,
  ].filter(Boolean);

  const toggleLanguage = () => setLanguage(lang === 'ko' ? 'en' : 'ko');

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200 h-16 px-4 md:px-6 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-4">
          <button
            type="button"
            className="flex items-center gap-2"
            onClick={() => navigate('/home')}
            aria-label="Go to Home"
          >
            <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center text-white font-bold text-xl shadow-lg shadow-brand-500/30 cursor-pointer">
              <FlaskConical size={18} />
            </div>
            <span className="hidden md:block font-bold text-slate-800 tracking-tight cursor-pointer">NeuroLeague</span>
          </button>

          <nav className="hidden lg:flex items-center space-x-1 ml-6">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                    isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <item.icon size={16} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center space-x-3 md:space-x-5">
          <button
            onClick={toggleLanguage}
            className="flex items-center bg-slate-100 rounded-full p-1 cursor-pointer hover:bg-slate-200 transition-colors border border-slate-200"
            title="Switch Language / 언어 변경"
            aria-label="Switch Language"
            type="button"
          >
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold transition-all ${
                lang === 'ko' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-400'
              }`}
            >
              한글
            </span>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold transition-all ${
                lang === 'en' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-400'
              }`}
            >
              ENG
            </span>
          </button>

          <div className="hidden md:flex flex-col items-end mr-2">
            <span className="text-xs font-bold text-slate-800">{home?.user.display_name ?? '—'}</span>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              <span className="text-[10px] uppercase font-semibold text-slate-500">
                {(home?.user.tokens ?? 0).toLocaleString()} {tc.tokens}
              </span>
            </div>
          </div>

          <button className="text-slate-500 hover:text-brand-600 transition-colors relative" type="button">
            <Bell size={20} />
            <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
          </button>
          <button className="text-slate-500 hover:text-brand-600 transition-colors" type="button">
            <HelpCircle size={20} />
          </button>
          <div className="w-8 h-8 rounded-full bg-slate-200 overflow-hidden border border-slate-300">
            <img
              src={`https://api.dicebear.com/7.x/notionists/svg?seed=${encodeURIComponent(home?.user.display_name ?? 'Neuro')}`}
              alt="Avatar"
            />
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto p-4 md:p-6 pb-24 md:pb-8 max-w-7xl">
        <Outlet />
      </main>

      <nav className="lg:hidden fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 pb-safe z-50 px-4 py-2 flex justify-between items-center shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
        {mobileItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center p-2 rounded-xl transition-colors w-16 ${
                isActive ? 'text-brand-600 bg-brand-50' : 'text-slate-500'
              }`
            }
          >
            <item.icon size={20} />
            <span className="text-[10px] font-medium mt-1">{item.label}</span>
          </NavLink>
        ))}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex flex-col items-center justify-center p-2 rounded-xl transition-colors w-16 ${
              isActive ? 'text-brand-600 bg-brand-50' : 'text-slate-500'
            }`
          }
        >
          <MoreHorizontal size={20} />
          <span className="text-[10px] font-medium mt-1">{t.more}</span>
        </NavLink>
      </nav>
    </div>
  );
};
