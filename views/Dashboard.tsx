import React from 'react';
import { NavView } from '../types';
import { RECENT_MATCHES, PATCH_NOTES, CURRENT_USER } from '../constants';
import { Card, CardHeader, CardTitle, CardContent, Button, Badge } from '../components/ui';
import { ArrowRight, Trophy, Zap, Clock, TrendingUp, AlertCircle } from 'lucide-react';
import { TRANSLATIONS, Language } from '../lib/translations';

interface DashboardProps {
  onNavigate: (view: NavView) => void;
  lang: Language;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate, lang }) => {
  const t = TRANSLATIONS[lang].common;

  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
      
      {/* HERO SECTION */}
      <div className="md:col-span-12">
        <div className="relative overflow-hidden bg-gradient-to-r from-brand-600 to-accent-500 rounded-3xl p-6 md:p-10 text-white shadow-xl">
           <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
             <div>
               <div className="flex items-center gap-2 mb-2">
                 <Badge variant="brand" className="bg-white/20 text-white border-transparent">{t.season} 4</Badge>
                 <span className="text-white/80 text-sm font-medium">{t.week} 3</span>
               </div>
               <h1 className="text-3xl md:text-4xl font-bold mb-2">{t.welcome}, {CURRENT_USER.displayName}</h1>
               <p className="text-brand-100 max-w-xl">
                 {t.aiMessage}
               </p>
               <div className="mt-8 flex flex-wrap gap-3">
                 <Button onClick={() => onNavigate(NavView.TRAINING)} size="lg" className="bg-white text-brand-700 hover:bg-brand-50 border-0 shadow-lg">
                   {t.continueTraining}
                 </Button>
                 <Button onClick={() => onNavigate(NavView.RANKED)} variant="secondary" size="lg" className="bg-brand-700/50 text-white border-white/20 hover:bg-brand-700/70">
                   {t.enterRanked}
                 </Button>
               </div>
             </div>
             
             {/* Stats Pill */}
             <div className="bg-white/10 backdrop-blur-md rounded-2xl p-4 md:p-6 border border-white/10 min-w-[200px]">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-yellow-400 rounded-lg text-yellow-900"><Trophy size={20} /></div>
                  <div>
                    <div className="text-xs text-brand-100 uppercase font-bold">{t.currentRank}</div>
                    <div className="font-bold text-xl">{CURRENT_USER.division}</div>
                  </div>
                </div>
                <div className="flex justify-between items-end">
                   <div>
                     <div className="text-2xl font-bold">{CURRENT_USER.elo}</div>
                     <div className="text-xs text-green-300 font-medium">+42 {t.eloChange}</div>
                   </div>
                   <TrendingUp className="text-green-300 mb-1" size={20} />
                </div>
             </div>
           </div>
           
           {/* Background Decoration */}
           <div className="absolute top-0 right-0 -mr-20 -mt-20 w-96 h-96 bg-white/5 rounded-full blur-3xl pointer-events-none"></div>
        </div>
      </div>

      {/* LEFT COLUMN */}
      <div className="md:col-span-8 space-y-6">
        {/* Recent Matches */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock size={18} className="text-slate-400" />
              {t.recentMatches}
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => onNavigate(NavView.REPLAY)}>{t.viewAll}</Button>
          </CardHeader>
          <div className="divide-y divide-slate-100">
            {RECENT_MATCHES.map(match => (
              <div key={match.id} className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors group cursor-pointer">
                <div className="flex items-center gap-4">
                  <div className={`w-1.5 h-12 rounded-full ${match.result === 'win' ? 'bg-green-500' : 'bg-red-400'}`}></div>
                  <div>
                    <div className="font-bold text-slate-800">{match.opponent}</div>
                    <div className="text-xs text-slate-500 flex items-center gap-1">
                      {match.result === 'win' ? t.victory : t.defeat} • {match.duration} • <span className="text-slate-400">{match.date}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="hidden sm:block text-right">
                    <div className="text-xs font-semibold text-slate-400 uppercase">{t.archetype}</div>
                    <div className="text-sm font-medium text-slate-700">{match.opponentArchetype}</div>
                  </div>
                  <Badge variant={match.result === 'win' ? 'success' : 'error'}>
                    {match.eloChange > 0 ? '+' : ''}{match.eloChange} Elo
                  </Badge>
                  <Button size="icon" variant="ghost" className="opacity-0 group-hover:opacity-100 transition-opacity">
                    <ArrowRight size={16} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* RIGHT COLUMN */}
      <div className="md:col-span-4 space-y-6">
        {/* Meta Snapshot */}
        <Card className="border-accent-200 bg-gradient-to-b from-white to-brand-50/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-accent-700">
              <Zap size={18} /> {t.metaSnapshot}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-white border border-slate-100 shadow-sm">
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
                <p className="text-xs text-blue-700 leading-relaxed">
                  {t.metaTip}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Patch Notes */}
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