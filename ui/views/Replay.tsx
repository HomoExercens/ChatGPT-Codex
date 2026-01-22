import React, { useState } from 'react';
import { Card, Button, Badge } from '../components/ui';
import { Play, Pause, SkipBack, SkipForward, Maximize2, Camera, Share2, Flame, Skull } from 'lucide-react';
import { TRANSLATIONS, Language } from '../lib/translations';

export const Replay: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = TRANSLATIONS[lang].common;

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(12); // seconds

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] gap-4">
      
      {/* HEADER INFO */}
      <div className="flex justify-between items-center bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
         <div className="flex items-center gap-6">
           <div className="flex flex-col items-center">
              <span className="font-bold text-xl text-blue-600">{t.replayYou}</span>
              <Badge variant="info">Mech Rush</Badge>
           </div>
           <div className="text-2xl font-bold text-slate-300">VS</div>
           <div className="flex flex-col items-center">
              <span className="font-bold text-xl text-red-500">{t.replayOpponent}</span>
              <Badge variant="error">Nature Heal</Badge>
           </div>
         </div>
         <div className="flex gap-2">
            <Button variant="secondary" size="sm"><Share2 size={16} className="mr-2" /> {t.share}</Button>
            <Button variant="ghost" size="icon"><Maximize2 size={18} /></Button>
         </div>
      </div>

      {/* VIEWPORT */}
      <div className="flex-1 bg-slate-900 rounded-3xl relative overflow-hidden shadow-inner group">
         {/* Simulated Game Render */}
         <div className="absolute inset-0 flex items-center justify-center">
            {/* Units */}
            <div className="absolute top-1/2 left-1/3 transform -translate-y-1/2">
               <div className="w-16 h-16 bg-blue-500 rounded-full border-4 border-white shadow-[0_0_20px_rgba(59,130,246,0.5)] flex items-center justify-center text-white font-bold animate-pulse-slow">
                 Tank
               </div>
            </div>
            <div className="absolute top-1/2 right-1/3 transform -translate-y-1/2">
               <div className="w-16 h-16 bg-red-500 rounded-full border-4 border-white shadow-[0_0_20px_rgba(239,68,68,0.5)] flex items-center justify-center text-white font-bold">
                 Boss
               </div>
            </div>
            
            {/* Effects */}
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-yellow-400 font-bold text-4xl animate-bounce">
               CRIT!
            </div>
         </div>

         {/* Overlays */}
         <div className="absolute top-4 right-4 bg-black/50 text-white px-3 py-1 rounded-full font-mono text-sm backdrop-blur-md">
            00:{currentTime < 10 ? '0'+currentTime : currentTime} / 03:00
         </div>
      </div>

      {/* TIMELINE CONTROLS */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
         {/* Scrubber */}
         <div className="relative h-8 mb-4 cursor-pointer group">
            {/* Track */}
            <div className="absolute top-1/2 w-full h-2 bg-slate-100 rounded-full transform -translate-y-1/2"></div>
            <div className="absolute top-1/2 w-[20%] h-2 bg-brand-500 rounded-full transform -translate-y-1/2"></div>
            
            {/* Markers */}
            <div className="absolute top-1/2 left-[15%] w-3 h-3 bg-yellow-400 rounded-full transform -translate-y-1/2 border-2 border-white shadow-sm" title={t.firstBlood}></div>
            <div className="absolute top-1/2 left-[60%] w-3 h-3 bg-red-500 rounded-full transform -translate-y-1/2 border-2 border-white shadow-sm" title={t.ultCombo}></div>

            {/* Thumb */}
            <div className="absolute top-1/2 left-[20%] w-6 h-6 bg-white border-2 border-brand-600 rounded-full transform -translate-y-1/2 shadow-md hover:scale-110 transition-transform"></div>
         </div>

         {/* Buttons */}
         <div className="flex justify-center items-center gap-4">
            <Button variant="ghost" size="icon"><SkipBack size={20} /></Button>
            <Button size="icon" className="w-12 h-12 rounded-full" onClick={() => setIsPlaying(!isPlaying)}>
               {isPlaying ? <Pause size={24} className="fill-current" /> : <Play size={24} className="fill-current ml-1" />}
            </Button>
            <Button variant="ghost" size="icon"><SkipForward size={20} /></Button>
            
            <div className="w-px h-8 bg-slate-200 mx-4"></div>
            
            <div className="flex gap-2">
              <span className="text-xs font-bold text-slate-400 uppercase">{t.events}:</span>
              <Badge variant="warning" className="cursor-pointer"><Flame size={10} className="mr-1"/> {t.highDamage}</Badge>
              <Badge variant="error" className="cursor-pointer"><Skull size={10} className="mr-1"/> {t.kills}</Badge>
            </div>
         </div>
      </div>
    </div>
  );
};