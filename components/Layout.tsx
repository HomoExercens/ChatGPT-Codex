import React from 'react';
import { NavView } from '../types';
import { 
  LayoutDashboard, 
  FlaskConical, 
  Hammer, 
  Trophy, 
  PlaySquare, 
  BarChart3, 
  Settings, 
  Bell,
  HelpCircle,
  Menu,
  MoreHorizontal
} from 'lucide-react';
import { CURRENT_USER } from '../constants';
import { TRANSLATIONS, Language } from '../lib/translations';

interface LayoutProps {
  currentView: NavView;
  onChangeView: (view: NavView) => void;
  children: React.ReactNode;
  lang: Language;
  onToggleLang: () => void;
}

export const Layout: React.FC<LayoutProps> = ({ currentView, onChangeView, children, lang, onToggleLang }) => {
  const t = TRANSLATIONS[lang].nav;
  const tc = TRANSLATIONS[lang].common;

  const navItems = [
    { id: NavView.DASHBOARD, icon: LayoutDashboard, label: t.dashboard },
    { id: NavView.TRAINING, icon: FlaskConical, label: t.training },
    { id: NavView.FORGE, icon: Hammer, label: t.forge },
    { id: NavView.RANKED, icon: Trophy, label: t.ranked },
    { id: NavView.REPLAY, icon: PlaySquare, label: t.replay },
    { id: NavView.ANALYTICS, icon: BarChart3, label: t.analytics },
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* --- TOP HEADER (PC) --- */}
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200 h-16 px-4 md:px-6 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-4">
          <div className="flex items-center gap-2" onClick={() => onChangeView(NavView.DASHBOARD)}>
            <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center text-white font-bold text-xl shadow-lg shadow-brand-500/30 cursor-pointer">
              <FlaskConical size={18} />
            </div>
            <span className="hidden md:block font-bold text-slate-800 tracking-tight cursor-pointer">NeuroLeague</span>
          </div>
          
          {/* PC Nav */}
          <nav className="hidden lg:flex items-center space-x-1 ml-6">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => onChangeView(item.id)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                  currentView === item.id 
                    ? 'bg-brand-50 text-brand-700' 
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <item.icon size={16} />
                {item.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Right Actions */}
        <div className="flex items-center space-x-3 md:space-x-5">
          {/* Language Toggle */}
          <button 
            onClick={onToggleLang}
            className="flex items-center bg-slate-100 rounded-full p-1 cursor-pointer hover:bg-slate-200 transition-colors border border-slate-200"
            title="Switch Language / 언어 변경"
          >
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold transition-all ${lang === 'ko' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-400'}`}>한글</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold transition-all ${lang === 'en' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-400'}`}>ENG</span>
          </button>

          <div className="hidden md:flex flex-col items-end mr-2">
            <span className="text-xs font-bold text-slate-800">{CURRENT_USER.displayName}</span>
            <div className="flex items-center gap-1.5">
               <span className="w-2 h-2 rounded-full bg-green-500"></span>
               <span className="text-[10px] uppercase font-semibold text-slate-500">{CURRENT_USER.tokens.toLocaleString()} {tc.tokens}</span>
            </div>
          </div>
          
          <button className="text-slate-500 hover:text-brand-600 transition-colors relative">
            <Bell size={20} />
            <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
          </button>
          <button className="text-slate-500 hover:text-brand-600 transition-colors">
            <HelpCircle size={20} />
          </button>
          <div className="w-8 h-8 rounded-full bg-slate-200 overflow-hidden border border-slate-300">
             <img src={`https://api.dicebear.com/7.x/notionists/svg?seed=${CURRENT_USER.displayName}`} alt="Avatar" />
          </div>
        </div>
      </header>

      {/* --- MAIN CONTENT --- */}
      <main className="flex-1 container mx-auto p-4 md:p-6 pb-24 md:pb-8 max-w-7xl">
        {children}
      </main>

      {/* --- MOBILE BOTTOM NAV --- */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 pb-safe z-50 px-4 py-2 flex justify-between items-center shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
        {navItems.slice(0, 4).map((item) => (
          <button
            key={item.id}
            onClick={() => onChangeView(item.id)}
            className={`flex flex-col items-center justify-center p-2 rounded-xl transition-colors w-16 ${
              currentView === item.id 
                ? 'text-brand-600 bg-brand-50' 
                : 'text-slate-500'
            }`}
          >
            <item.icon size={20} strokeWidth={currentView === item.id ? 2.5 : 2} />
            <span className="text-[10px] font-medium mt-1">{item.label}</span>
          </button>
        ))}
        <button 
           onClick={() => onChangeView(NavView.SETTINGS)}
           className={`flex flex-col items-center justify-center p-2 rounded-xl transition-colors w-16 ${currentView === NavView.SETTINGS ? 'text-brand-600 bg-brand-50' : 'text-slate-500'}`}
        >
          <MoreHorizontal size={20} />
          <span className="text-[10px] font-medium mt-1">{t.more}</span>
        </button>
      </nav>
    </div>
  );
};