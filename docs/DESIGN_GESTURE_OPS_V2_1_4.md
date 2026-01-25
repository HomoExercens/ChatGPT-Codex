# Gesture Ops v2.1.4 — Segment Filters + Sampling Bias Observability

This document is generated from the `gemini_ui_design` MCP tool output and records the UI spec + provenance per AGENTS.md.

## Gemini UI Spec (raw)

# UI Spec: NeuroLeague Gesture Ops v2.1.4

## 1. UI Concept
**"Tactical HUD"**: A high-density, data-rich interface designed for rapid operational assessment. The aesthetic leans into a "Premium Dark Ops" motif using deep slate backgrounds, high-contrast neon data points, and distinct bordering to separate control logic (filtering) from observability data. The hierarchy flows from **Context** (Filters) → **Reliability** (Sampling/Bias) → **Performance** (Variant Cards), ensuring operators verify data integrity before interpreting KPIs.

## 2. Layout Structure
*   **Header / Global Scope**
    *   Page Title & Breadcrumbs.
    *   **Segment Filter Control**: A unified bar containing split-dropdowns for Platform (Android/iOS/Desktop) and Container (TWA/Chrome/Webview).
*   **Observability Panel (The "Bias Strip")**
    *   A sticky or high-visibility row displaying global sampling health: `n_sessions`, `n_attempts`, `sample_rate_used`, `cap_hit_rate`, and `avg_dropped_count`.
    *   Visual warning indicators if sampling < threshold or cap hit > 90%.
*   **Variant Grid (Main Content)**
    *   Comparison layout (Control vs. Variants).
    *   **Variant Card Structure**:
        *   Header: Name, ID, Allocation %.
        *   Primary KPI: Success Rate / Latency (Big Stat).
        *   Secondary KPI: Misfire Score (Inverted scale).
        *   Cancel Reason List: Top 3 reasons with relative frequency bars.
        *   Guardrails/Status: Badge indicators.

## 3. Design Tokens (Design v2 Alignment)
*   **Colors (Dark Mode Optimized)**
    *   **Surface**: `bg-slate-950` (App), `bg-slate-900` (Cards), `bg-slate-800` (Inputs).
    *   **Borders**: `border-slate-800` (Subtle), `border-indigo-500/50` (Active/Focus).
    *   **Text**: `text-slate-100` (Primary), `text-slate-400` (Labels), `text-slate-500` (Disabled).
    *   **Status**: `emerald-400` (Stable/Good), `amber-400` (Warning/Cap Hit), `rose-500` (Misfire/Error), `cyan-400` (Info).
*   **Typography**
    *   **Headings**: *Inter*, bold, tracking-tight.
    *   **Data/KPIs**: *JetBrains Mono* or system monospace, `tabular-nums` for alignment.
    *   **Labels**: *Inter*, uppercase, text-xs, tracking-wide.
*   **Spacing & Radius**
    *   **Density**: Compact spacing (`gap-2`, `p-3`).
    *   **Radius**: `rounded-md` (Small/Sharp) for controls, `rounded-lg` for containers.
*   **Effects**
    *   **Shadows**: None (Flat) or subtle glow on active elements (`shadow-indigo-500/10`).
    *   **Glass**: Minimal `backdrop-blur-sm` on sticky headers.

## 4. Accessibility Checklist (WCAG 2.1 AA)
*   [ ] **Contrast**: Ensure data values (Cyan/Emerald) on Slate-900 backgrounds meet 4.5:1 ratio.
*   [ ] **Focus State**: Visible `ring-2 ring-indigo-500` outline on all interactive filter buttons.
*   [ ] **Semantic Structure**: Use `<section>` for layout areas and `<ul>/<li>` for card lists.
*   [ ] **Screen Readers**:
    *   `aria-label` on segment filters describing the currently selected state.
    *   `aria-live="polite"` on the Observability Panel to announce data changes when filters update.
*   [ ] **Reduced Motion**: Disable layout animations (framer-motion) if `prefers-reduced-motion: reduce` is detected.

## 5. Edge Cases & States
*   **Empty State**: "No Signal" visualization when a segment has 0 sessions.
*   **Low Sample Warning**: If `n_sessions < 100`, overlay cards with a "Low Confidence" watermark or opacity fade.
*   **Loading**: Skeleton loader for the Variant Grid; Filters remain interactive (disabled state).
*   **Error**: "Data Fetch Failure" toast with a retry button.

---

## Component Implementation

```tsx
import React, { useState } from 'react';
import { 
  Filter, 
  AlertTriangle, 
  Activity, 
  XCircle, 
  CheckCircle2, 
  ChevronDown,
  Smartphone,
  Monitor
} from 'lucide-react';

// --- Types ---

type Platform = 'all' | 'android' | 'ios' | 'desktop';
type Container = 'all' | 'twa' | 'chrome' | 'webview';

interface VariantData {
  id: string;
  name: string;
  isControl: boolean;
  allocation: number;
  kpi: {
    successRate: number;
    latencyMs: number;
  };
  misfireScore: number; // 0-100, lower is better
  cancelReasons: { reason: string; count: number; pct: number }[];
  status: 'active' | 'graduated' | 'monitor';
}

interface ObservabilityMetrics {
  n_sessions: number;
  n_attempts: number;
  sample_rate_used: number; // 0.0 - 1.0
  cap_hit_rate: number; // 0.0 - 1.0
  avg_dropped_count: number;
}

// --- Mock Data ---

const MOCK_METRICS: ObservabilityMetrics = {
  n_sessions: 14502,
  n_attempts: 42390,
  sample_rate_used: 0.15,
  cap_hit_rate: 0.92, // High, should warn
  avg_dropped_count: 450
};

const MOCK_VARIANTS: VariantData[] = [
  {
    id: 'ctrl-v1',
    name: 'Control (Baseline)',
    isControl: true,
    allocation: 50,
    kpi: { successRate: 88.4, latencyMs: 120 },
    misfireScore: 12,
    status: 'active',
    cancelReasons: [
      { reason: 'timeout_no_action', count: 1200, pct: 45 },
      { reason: 'finger_slip_y', count: 400, pct: 15 },
      { reason: 'system_interrupt', count: 200, pct: 8 },
    ]
  },
  {
    id: 'var-a-haptic',
    name: 'Variant A (Haptic)',
    isControl: false,
    allocation: 25,
    kpi: { successRate: 91.2, latencyMs: 115 },
    misfireScore: 8,
    status: 'monitor',
    cancelReasons: [
      { reason: 'timeout_no_action', count: 500, pct: 30 },
      { reason: 'finger_slip_y', count: 350, pct: 22 },
      { reason: 'rapid_trigger', count: 150, pct: 10 },
    ]
  },
  {
    id: 'var-b-visual',
    name: 'Variant B (Visual Cue)',
    isControl: false,
    allocation: 25,
    kpi: { successRate: 89.1, latencyMs: 140 },
    misfireScore: 24,
    status: 'active',
    cancelReasons: [
      { reason: 'visual_distraction', count: 800, pct: 50 },
      { reason: 'timeout_no_action', count: 200, pct: 12 },
      { reason: 'false_positive', count: 100, pct: 6 },
    ]
  }
];

// --- Components ---

const StatBadge = ({ label, value, warn = false, unit = '' }: { label: string, value: string | number, warn?: boolean, unit?: string }) => (
  <div className={`flex flex-col px-4 py-2 border-r border-slate-800 last:border-0 ${warn ? 'bg-amber-950/20' : ''}`}>
    <span className={`text-[10px] uppercase tracking-wider font-semibold ${warn ? 'text-amber-500' : 'text-slate-500'}`}>
      {label}
    </span>
    <span className={`text-sm font-mono font-medium ${warn ? 'text-amber-400' : 'text-slate-200'}`}>
      {value}{unit}
    </span>
  </div>
);

const SegmentFilter = ({ 
  platform, setPlatform, container, setContainer 
}: { 
  platform: Platform, setPlatform: (p: Platform) => void,
  container: Container, setContainer: (c: Container) => void
}) => (
  <div className="flex flex-wrap items-center gap-3 p-4 bg-slate-900 border-b border-slate-800">
    <div className="flex items-center gap-2 text-slate-400 mr-4">
      <Filter size={16} />
      <span className="text-xs font-bold uppercase tracking-widest">Filters</span>
    </div>
    
    {/* Platform Select */}
    <div className="relative group">
      <select 
        value={platform}
        onChange={(e) => setPlatform(e.target.value as Platform)}
        className="appearance-none bg-slate-950 border border-slate-700 text-slate-200 text-sm rounded pl-3 pr-8 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none hover:border-slate-600 transition-colors"
        aria-label="Filter by Platform"
      >
        <option value="all">All Platforms</option>
        <option value="android">Android</option>
        <option value="ios">iOS</option>
        <option value="desktop">Desktop</option>
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" size={14} />
    </div>

    {/* Container Select */}
    <div className="relative group">
      <select 
        value={container}
        onChange={(e) => setContainer(e.target.value as Container)}
        className="appearance-none bg-slate-950 border border-slate-700 text-slate-200 text-sm rounded pl-3 pr-8 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none hover:border-slate-600 transition-colors"
        aria-label="Filter by Container"
      >
        <option value="all">All Containers</option>
        <option value="twa">TWA (Trusted Web Activity)</option>
        <option value="chrome">Chrome Browser</option>
        <option value="webview">Webview</option>
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" size={14} />
    </div>
  </div>
);

const ObservabilityPanel = ({ metrics }: { metrics: ObservabilityMetrics }) => {
  const isCapHitHigh = metrics.cap_hit_rate > 0.9;
  const isSampleLow = metrics.n_sessions < 1000;

  return (
    <div className="bg-slate-950 border-b border-slate-800 flex items-center justify-between overflow-x-auto">
      <div className="flex items-center">
        <div className="px-4 py-3 bg-slate-900 border-r border-slate-800 flex items-center gap-2">
          <Activity size={16} className="text-indigo-400" />
          <span className="text-xs font-bold text-slate-300 uppercase">Observability</span>
        </div>
        <div className="flex">
          <StatBadge label="Total Sessions" value={metrics.n_sessions.toLocaleString()} warn={isSampleLow} />
          <StatBadge label="Attempts" value={metrics.n_attempts.toLocaleString()} />
          <StatBadge label="Sample Rate" value={(metrics.sample_rate_used * 100).toFixed(1)} unit="%" />
          <StatBadge label="Cap Hit Rate" value={(metrics.cap_hit_rate * 100).toFixed(1)} unit="%" warn={isCapHitHigh} />
          <StatBadge label="Avg Dropped" value={metrics.avg_dropped_count} />
        </div>
      </div>
      
      {/* Contextual Warning */}
      {(isCapHitHigh || isSampleLow) && (
        <div className="flex items-center gap-2 px-4 text-amber-500 text-xs font-medium animate-pulse">
          <AlertTriangle size={14} />
          <span>Bias Detected: {isCapHitHigh ? 'Cap Limit Reached' : 'Low Sample Volume'}</span>
        </div>
      )}
    </div>
  );
};

const CancelReasonList = ({ reasons }: { reasons: { reason: string, count: number, pct: number }[] }) => (
  <div className="mt-4 space-y-2">
    <div className="text-[10px] uppercase text-slate-500 font-bold tracking-wider mb-2">Top 3 Cancel Reasons</div>
    {reasons.map((r, i) => (
      <div key={i} className="flex items-center justify-between text-xs group">
        <div className="flex-1">
          <div className="flex justify-between mb-0.5">
            <span className="text-slate-300 font-mono">{r.reason}</span>
            <span className="text-slate-500">{r.pct}%</span>
          </div>
          <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
            <div 
              className="h-full bg-slate-600 group-hover:bg-indigo-500 transition-colors" 
              style={{ width: `${r.pct}%` }} 
            />
          </div>
        </div>
      </div>
    ))}
  </div>
);

const VariantCard = ({ data }: { data: VariantData }) => {
  const isControl = data.isControl;
  
  return (
    <article className={`relative rounded-lg border ${isControl ? 'border-slate-700 bg-slate-900/50' : 'border-slate-800 bg-slate-900'} p-5 flex flex-col h-full hover:border-slate-600 transition-all`}>
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-bold text-white">{data.name}</h3>
            {isControl && <span className="text-[10px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-slate-700">CTRL</span>}
          </div>
          <div className="text-xs text-slate-500 font-mono">{data.id}</div>
        </div>
        <div className="flex items-center gap-2">
           <span className={`text-[10px] font-mono px-2 py-1 rounded-full border ${
             data.status === 'active' ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' : 'border-slate-700 text-slate-400'
           }`}>
             {data.allocation}% TRAFFIC
           </span>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Success Rate</div>
          <div className="text-2xl font-mono text-white mt-0.5">
            {data.kpi.successRate}<span className="text-sm text-slate-500">%</span>
          </div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider">Misfire Score</div>
          <div className={`text-2xl font-mono mt-0.5 ${data.misfireScore > 20 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {data.misfireScore}
          </div>
        </div>
      </div>

      <div className="h-px w-full bg-slate-800 mb-4" />

      {/* Observability Details */}
      <div className="flex-1">
         <CancelReasonList reasons={data.cancelReasons} />
      </div>

      {/* Footer / Guardrails */}
      <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-1">
          <Activity size={12} />
          <span>Lat: {data.kpi.latencyMs}ms</span>
        </div>
        <div className="flex items-center gap-1">
           {data.misfireScore < 15 ? (
             <CheckCircle2 size={12} className="text-emerald-500" />
           ) : (
             <XCircle size={12} className="text-rose-500" />
           )}
           <span>Guardrails</span>
        </div>
      </div>
    </article>
  );
};

// --- Main Layout ---

export default function GestureOpsDashboard() {
  const [platform, setPlatform] = useState<Platform>('all');
  const [container, setContainer] = useState<Container>('all');

  // Logic check for "Do Not Interpret"
  const lowSample = MOCK_METRICS.n_sessions < 500;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-indigo-500/30">
      {/* Header */}
      <header className="px-6 py-4 border-b border-slate-800 bg-slate-950 flex justify-between items-center">
        <div>
           <div className="text-xs text-indigo-400 font-bold uppercase tracking-widest mb-1">Ops / Gestures / v2.1.4</div>
           <h1 className="text-xl font-bold text-white tracking-tight">Swipe_To_Confirm Analysis</h1>
        </div>
        <div className="flex gap-2">
            {/* Context Icons */}
            <div className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-400">
               {platform === 'android' ? <Smartphone size={18}/> : platform === 'desktop' ? <Monitor size={18}/> : <Activity size={18}/>}
            </div>
        </div>
      </header>

      {/* Controls & Observability */}
      <div className="sticky top-0 z-10 backdrop-blur-md bg-slate-950/80 border-b border-slate-800 shadow-xl shadow-black/20">
        <SegmentFilter 
          platform={platform} setPlatform={setPlatform}
          container={container} setContainer={setContainer}
        />
        <ObservabilityPanel metrics={MOCK_METRICS} />
      </div>

      {/* Content Area */}
      <main className="p-6">
        
        {lowSample ? (
           <div className="h-96 flex flex-col items-center justify-center border-2 border-dashed border-slate-800 rounded-xl bg-slate-900/20">
              <Activity size={48} className="text-slate-700 mb-4" />
              <h3 className="text-lg font-bold text-slate-400">Insufficient Sample Data</h3>
              <p className="text-slate-600 mt-2 max-w-md text-center">
                Segment filter results in &lt; 500 sessions. Do not interpret KPIs for this cross-section.
              </p>
           </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {MOCK_VARIANTS.map(variant => (
              <VariantCard key={variant.id} data={variant} />
            ))}
            
            {/* Add Variant Placeholder */}
            <button className="border-2 border-dashed border-slate-800 rounded-lg flex flex-col items-center justify-center text-slate-600 hover:border-slate-600 hover:text-slate-400 transition-all min-h-[300px]">
               <span className="text-4xl mb-2 font-thin">+</span>
               <span className="text-sm font-bold uppercase tracking-widest">Add Variant</span>
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
```

### Integration Note
*   **Icons**: Using `lucide-react`. Ensure you have it installed or swap for your preferred icon set.
*   **Tailwind Config**: Depends on default Tailwind colors (Slate, Indigo, Emerald, Rose, Amber). The design assumes `bg-slate-950` is available (Tailwind v3+).
*   **Fonts**: The design relies on `font-sans` (Inter implied) and `font-mono` (JetBrains/Robo Mono implied). Ensure these are set in your `tailwind.config.js`.
*   **Responsiveness**: The `ObservabilityPanel` has `overflow-x-auto` to handle narrow screens, and the grid collapses to single column on mobile.

## Gemini Provenance (structuredContent)

```json
{
  "requested_start_alias": "ui-design-pro-max",
  "selected_latest_pro_model": "gemini-3-pro-preview",
  "attempted_chain": [
    {
      "alias": "ui-design-pro-max",
      "raw_model": "gemini-3-pro-preview",
      "success": true
    }
  ],
  "actual_models_used": [
    "gemini-3-pro-preview"
  ],
  "thinking_config_applied": {
    "raw_model": "gemini-3-pro-preview",
    "thinkingLevel": "high",
    "includeThoughts": false
  },
  "gemini_cli_version": "0.25.2",
  "note": "모델 목록 조회 실패로 인해 보수적 기본값 사용 | No supported non-interactive model listing method found (GEMINI_API_KEY not set; Gemini CLI does not expose `models list` in headless mode)."
}
```
