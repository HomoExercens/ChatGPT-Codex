import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent, Button, Badge, Input, Slider, Skeleton } from '../components/ui';
import { TrainingRun } from '../types';
import { Play, Pause, Square, BarChart2, BrainCircuit, Activity, ChevronRight, Settings2 } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip as RechartsTooltip } from 'recharts';
import { TRANSLATIONS, Language } from '../lib/translations';

export const Training: React.FC<{ lang: Language }> = ({ lang }) => {
  const t = TRANSLATIONS[lang].common;
  
  const [activeTab, setActiveTab] = useState<'overview' | 'runs' | 'advanced'>('overview');
  const [trainingState, setTrainingState] = useState<'idle' | 'running' | 'paused' | 'done'>('idle');
  const [progress, setProgress] = useState(0);
  const [budget, setBudget] = useState(500);
  const [selectedPlan, setSelectedPlan] = useState<string>('Stable');
  const [chartData, setChartData] = useState<any[]>([]);

  // Simulation Logic
  useEffect(() => {
    let interval: any;
    if (trainingState === 'running') {
      interval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 100) {
            setTrainingState('done');
            return 100;
          }
          // Add data point
          setChartData(curr => [...curr, { 
            step: curr.length, 
            winRate: 40 + (curr.length * 0.5) + (Math.random() * 5),
            loss: 2 - (curr.length * 0.02)
          }]);
          return prev + 1;
        });
      }, 100); // Fast simulation
    }
    return () => clearInterval(interval);
  }, [trainingState]);

  const handleStart = () => {
    setChartData([{ step: 0, winRate: 40, loss: 2 }]);
    setProgress(0);
    setTrainingState('running');
  };

  const plans = [
    { id: 'Stable', label: t.planStable, icon: '🛡️', desc: t.descStable },
    { id: 'Aggressive', label: t.planAggro, icon: '⚔️', desc: t.descAggro },
    { id: 'Counter', label: t.planCounter, icon: '🎯', desc: t.descCounter },
    { id: 'Exploratory', label: t.planExplore, icon: '🧪', desc: t.descExplore },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-140px)]">
      
      {/* LEFT PANEL: CONFIG */}
      <div className="lg:col-span-4 flex flex-col gap-6 overflow-y-auto pr-2">
        <Card className="flex-1 flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BrainCircuit size={20} className="text-brand-600" />
              {t.trainingConfig}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 flex-1">
            
            {/* Target Blueprint */}
            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">{t.targetBlueprint}</label>
              <select className="w-full px-4 py-2 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-brand-200 outline-none">
                <option>{t.newBlueprint}</option>
                <option>{t.clonedBlueprint}</option>
              </select>
            </div>

            {/* Plan Selection */}
            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 block">{t.trainingPlan}</label>
              <div className="grid grid-cols-2 gap-3">
                {plans.map(plan => (
                  <button
                    key={plan.id}
                    onClick={() => setSelectedPlan(plan.id)}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      selectedPlan === plan.id 
                        ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' 
                        : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <div className="text-xl mb-1">{plan.icon}</div>
                    <div className="font-bold text-sm text-slate-800">{plan.label}</div>
                    <div className="text-[10px] text-slate-500 leading-tight mt-1">{plan.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Budget */}
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
               <div className="flex justify-between items-center mb-2">
                 <label className="text-xs font-bold text-slate-700">{t.computeBudget}</label>
                 <span className="text-xs font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-brand-600">{budget} {t.tokens}</span>
               </div>
               <Slider 
                  min={100} max={2000} step={50} 
                  value={budget} 
                  onChange={(e) => setBudget(parseInt(e.target.value))} 
                  disabled={trainingState === 'running'}
               />
               <div className="mt-2 text-[10px] text-slate-400 flex justify-between">
                 <span>{t.quickCheck}</span>
                 <span>{t.deepLearning}</span>
               </div>
            </div>

            {/* Actions */}
            <div className="pt-4 border-t border-slate-100 flex gap-3">
               {trainingState === 'idle' || trainingState === 'done' ? (
                 <Button className="w-full h-12 text-lg shadow-brand-500/20" onClick={handleStart}>
                   <Play size={20} className="mr-2 fill-current" /> {t.startExperiment}
                 </Button>
               ) : (
                 <>
                   <Button variant="secondary" className="w-full" onClick={() => setTrainingState(trainingState === 'paused' ? 'running' : 'paused')}>
                     {trainingState === 'paused' ? <><Play size={20} className="mr-1" /> {t.resume}</> : <><Pause size={20} className="mr-1" /> {t.pause}</>}
                   </Button>
                   <Button variant="destructive" className="w-full" onClick={() => setTrainingState('idle')}>
                     <Square size={20} className="fill-current mr-1" /> {t.stop}
                   </Button>
                 </>
               )}
            </div>

          </CardContent>
        </Card>
      </div>

      {/* RIGHT PANEL: VISUALIZATION */}
      <div className="lg:col-span-8 flex flex-col gap-6">
        
        {/* Status Bar */}
        <div className="flex items-center gap-4 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
          <div className="flex-1">
             <div className="flex justify-between text-sm mb-2">
               <span className="font-medium text-slate-700">
                 {trainingState === 'idle' ? t.readyToTrain : 
                  trainingState === 'done' ? t.trainingComplete : 
                  t.trainingModel}
               </span>
               <span className="font-mono text-slate-500">{progress}%</span>
             </div>
             <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
               <div 
                  className={`h-full transition-all duration-300 ${trainingState === 'done' ? 'bg-green-500' : 'bg-brand-500'}`} 
                  style={{ width: `${progress}%` }}
                ></div>
             </div>
          </div>
          <div className="hidden md:flex gap-4 border-l border-slate-100 pl-4">
             <div>
               <div className="text-[10px] uppercase text-slate-400 font-bold">{t.estWinrate}</div>
               <div className="text-lg font-bold text-slate-800">
                 {chartData.length > 0 ? chartData[chartData.length - 1].winRate.toFixed(1) : '--'}%
               </div>
             </div>
             <div>
               <div className="text-[10px] uppercase text-slate-400 font-bold">{t.loss}</div>
               <div className="text-lg font-bold text-slate-800">
                  {chartData.length > 0 ? chartData[chartData.length - 1].loss.toFixed(3) : '--'}
               </div>
             </div>
          </div>
        </div>

        {/* Main Viz Area */}
        <Card className="flex-1 flex flex-col min-h-[400px]">
          <CardHeader className="flex justify-between">
             <div className="flex gap-4">
               <button onClick={() => setActiveTab('overview')} className={`text-sm font-medium pb-4 border-b-2 -mb-4 transition-colors ${activeTab === 'overview' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{t.learningCurve}</button>
               <button onClick={() => setActiveTab('runs')} className={`text-sm font-medium pb-4 border-b-2 -mb-4 transition-colors ${activeTab === 'runs' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{t.checkpoints}</button>
             </div>
             <Button variant="ghost" size="sm"><Settings2 size={16} /></Button>
          </CardHeader>
          <CardContent className="flex-1 relative">
            {trainingState === 'idle' && chartData.length === 0 ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400">
                 <Activity size={48} className="mb-4 opacity-50" />
                 <p>Start a training run to see real-time metrics</p>
              </div>
            ) : (
              <div className="w-full h-full min-h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <XAxis dataKey="step" hide />
                    <YAxis domain={[0, 100]} hide />
                    <RechartsTooltip 
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}
                    />
                    <Line type="monotone" dataKey="winRate" stroke="#2563eb" strokeWidth={3} dot={false} animationDuration={300} />
                    <Line type="monotone" dataKey="loss" stroke="#ef4444" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            
            {/* Logs Overlay (Bottom) */}
            <div className="absolute bottom-4 left-4 right-4 h-32 bg-slate-900 rounded-xl p-3 font-mono text-xs text-green-400 overflow-hidden shadow-lg opacity-90">
              <div className="opacity-50 mb-1"> {t.systemLogs}_</div>
              {trainingState === 'running' && (
                <div className="space-y-1">
                   <p>> {t.epoch} {Math.floor(progress / 5)} completed.</p>
                   <p>> {t.logicOptimized}: "Tank Positioning".</p>
                   <p>> {t.discarded}: 140.</p>
                   <p className="animate-pulse">> {t.analyzing}</p>
                </div>
              )}
              {trainingState === 'done' && <p className="text-white">> Training Sequence Complete. Model saved.</p>}
            </div>

          </CardContent>
        </Card>
      </div>
    </div>
  );
};