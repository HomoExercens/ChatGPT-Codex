import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, Button, Badge, Input } from '../components/ui';
import { MOCK_CREATURES } from '../constants';
import { Creature, Rarity } from '../types';
import { Search, Info, Shield, Sword, UserPlus, Filter, Save, UploadCloud } from 'lucide-react';
import { TRANSLATIONS, Language } from '../lib/translations';

export const Forge: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = TRANSLATIONS[lang].common;

  const [team, setTeam] = useState<(Creature | null)[]>([null, null, null, null, null]);
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);

  const handleSelectCreature = (creature: Creature) => {
    if (selectedSlot !== null) {
      const newTeam = [...team];
      newTeam[selectedSlot] = creature;
      setTeam(newTeam);
      setSelectedSlot(null);
    }
  };

  const getRarityColor = (r: Rarity) => {
    switch(r) {
      case Rarity.COMMON: return 'bg-slate-200 text-slate-700';
      case Rarity.RARE: return 'bg-blue-100 text-blue-700';
      case Rarity.EPIC: return 'bg-purple-100 text-purple-700';
      case Rarity.LEGENDARY: return 'bg-amber-100 text-amber-700';
      default: return 'bg-slate-100';
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-140px)]">
      
      {/* LEFT: INVENTORY */}
      <Card className="lg:col-span-3 flex flex-col h-full overflow-hidden">
        <CardHeader className="py-3">
          <Input placeholder={t.searchCreatures} className="h-9 text-sm" />
          <div className="flex gap-2 mt-2 overflow-x-auto pb-1 no-scrollbar">
             {['Tank', 'DPS', 'Support'].map(role => (
               <Badge key={role} variant="neutral" className="cursor-pointer hover:bg-slate-200 whitespace-nowrap">{role}</Badge>
             ))}
          </div>
        </CardHeader>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
           {MOCK_CREATURES.map(creature => (
             <div 
               key={creature.id} 
               onClick={() => selectedSlot !== null && handleSelectCreature(creature)}
               className={`flex items-center gap-3 p-2 rounded-xl border cursor-pointer hover:bg-slate-50 transition-all ${selectedSlot !== null ? 'ring-2 ring-brand-200 hover:ring-brand-400' : 'border-slate-100'}`}
             >
               <img src={creature.imageUrl} className="w-10 h-10 rounded-lg bg-slate-200 object-cover" alt={creature.name} />
               <div className="flex-1 min-w-0">
                 <div className="font-bold text-sm text-slate-800 truncate">{creature.name}</div>
                 <div className="flex gap-1 mt-0.5">
                   <span className={`text-[10px] px-1 rounded ${getRarityColor(creature.rarity)}`}>{creature.role}</span>
                 </div>
               </div>
             </div>
           ))}
        </div>
      </Card>

      {/* CENTER: CANVAS */}
      <div className="lg:col-span-6 flex flex-col gap-4">
         {/* Toolbar */}
         <div className="bg-white p-2 rounded-xl border border-slate-200 shadow-sm flex justify-between items-center">
            <div className="flex items-center gap-2 px-2">
              <span className="text-sm font-bold text-slate-600">{t.targetBlueprint}:</span>
              <span className="text-sm font-medium">Mech Counter V1</span>
              <Badge variant="warning">{t.draft}</Badge>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost"><Save size={16} className="mr-2" /> {t.save}</Button>
              <Button size="sm"><UploadCloud size={16} className="mr-2" /> {t.submit}</Button>
            </div>
         </div>

         {/* Hex Grid / Slots */}
         <div className="flex-1 bg-slate-100 rounded-3xl border-2 border-slate-200 border-dashed relative overflow-hidden flex items-center justify-center">
            {/* Background Grid Pattern */}
            <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'radial-gradient(#94a3b8 1px, transparent 1px)', backgroundSize: '24px 24px' }}></div>
            
            <div className="relative z-10 grid grid-cols-3 gap-8">
               {/* 5 Slot Formation */}
               {[0, 1, 2, 3, 4].map(index => (
                  <div 
                    key={index} 
                    onClick={() => setSelectedSlot(index)}
                    className={`
                      w-24 h-24 md:w-32 md:h-32 rounded-3xl flex flex-col items-center justify-center transition-all cursor-pointer shadow-lg
                      ${index === 1 || index === 3 ? 'mt-12' : ''} /* Pseudo-hex layout offset */
                      ${team[index] ? 'bg-white border-2 border-brand-500' : 'bg-slate-200/50 border-2 border-slate-300 border-dashed hover:bg-slate-200'}
                      ${selectedSlot === index ? 'ring-4 ring-brand-400 ring-offset-2 scale-105' : ''}
                    `}
                  >
                    {team[index] ? (
                      <>
                        <img src={team[index]!.imageUrl} className="w-12 h-12 md:w-16 md:h-16 rounded-xl mb-1 object-cover" />
                        <span className="text-[10px] font-bold text-slate-700 bg-slate-100 px-2 rounded-full max-w-[90%] truncate">{team[index]!.name}</span>
                      </>
                    ) : (
                      <UserPlus className="text-slate-400" />
                    )}
                  </div>
               ))}
            </div>
         </div>
      </div>

      {/* RIGHT: INSPECTOR */}
      <Card className="lg:col-span-3 h-full">
         <CardHeader>
           <CardTitle>{t.synergies}</CardTitle>
         </CardHeader>
         <CardContent>
           {team.some(t => t) ? (
             <div className="space-y-4">
               {/* Mock Synergy */}
               <div>
                  <div className="flex justify-between items-center mb-1">
                    <span className="font-bold text-sm text-slate-700 flex items-center gap-2">
                       <Shield size={14} className="text-blue-500" /> Mech
                    </span>
                    <span className="text-xs text-slate-500">2/4</span>
                  </div>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 w-1/2"></div>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-1">All Mechs gain +20% Shield at start of combat.</p>
               </div>
               
               <div className="pt-4 border-t border-slate-100">
                  <h4 className="text-xs font-bold text-slate-400 uppercase mb-2">{t.teamStats}</h4>
                  <div className="grid grid-cols-2 gap-2">
                     <div className="bg-slate-50 p-2 rounded-lg">
                        <div className="text-[10px] text-slate-400">{t.totalHp}</div>
                        <div className="font-mono font-bold">4250</div>
                     </div>
                     <div className="bg-slate-50 p-2 rounded-lg">
                        <div className="text-[10px] text-slate-400">{t.dps}</div>
                        <div className="font-mono font-bold">320</div>
                     </div>
                  </div>
               </div>
             </div>
           ) : (
             <div className="text-center text-slate-400 py-10">
               <Info size={32} className="mx-auto mb-2 opacity-50" />
               <p className="text-sm">{t.noSynergy}</p>
             </div>
           )}
         </CardContent>
      </Card>
    </div>
  );
};