import React, { useState } from 'react';
import {
  Activity, AlertTriangle, Network, Clock, Globe, UserCheck, Briefcase, Cpu, UploadCloud, Plug, Radio, Stamp, ScrollText,
  Satellite, ListChecks, Timer, Shuffle, ChevronDown, ChevronsLeft, ChevronsRight,
} from 'lucide-react';
import coffeeBean from '../coffee-bean.svg';
import { hasRole, useSession } from '../session';

export const NAV_GROUPS = [
  { title: 'Monitor', items: [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'alerts', label: 'Alert Triage', icon: AlertTriangle, badge: 'alerts' },
    { id: 'watchlist', label: 'Watchlist', icon: Radio, badge: 'movements', urgent: true },
    { id: 'live', label: 'Live Monitor', icon: Satellite },
    { id: 'review', label: 'Review Queue', icon: ListChecks },
  ] },
  { title: 'Investigate', items: [
    { id: 'graph', label: 'Link Graph', icon: Network },
    { id: 'entity', label: 'Entity 360', icon: UserCheck },
    { id: 'timeline', label: 'Timeline', icon: Clock },
    { id: 'geomap', label: 'Geo Map', icon: Globe },
  ] },
  { title: 'Intelligence', items: [
    { id: 'forecast', label: 'Cash-Out Forecast', icon: Timer },
    { id: 'mixer', label: 'Mixer Lab', icon: Shuffle },
  ] },
  { title: 'Legal & Evidence', items: [
    { id: 'cases', label: 'Cases & Evidence', icon: Briefcase, badge: 'cases' },
    { id: 'approvals', label: 'Legal Approvals', icon: Stamp, badge: 'approvals' },
    { id: 'modelcard', label: 'Model Card', icon: Cpu },
    { id: 'audit', label: 'Audit Trail', icon: ScrollText, minRole: 'SUPERVISOR' },
  ] },
  { title: 'Data', items: [
    { id: 'ingest', label: 'Ingest & Seeds', icon: UploadCloud },
    { id: 'integrations', label: 'Rules & Integrations', icon: Plug },
  ] },
];

export const PAGE_TITLES = Object.fromEntries(
  NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.id, { label: i.label, group: g.title }])),
);

// Remembered per browser; storage can be blocked, so every access is guarded and the sidebar works without it.
const COLLAPSED_KEY = 'beans_sidebar_collapsed';
const CLOSED_KEY = 'beans_sidebar_closed_groups';
const read = (key, fallback) => {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
};
const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage blocked */ } };

export default function Sidebar({ activeTab, setActiveTab, counts = {} }) {
  const { user } = useSession();
  const [compact, setCompact] = useState(() => read(COLLAPSED_KEY, false) === true);
  const [closed, setClosed] = useState(() => read(CLOSED_KEY, {}));

  const toggleCompact = () => { const v = !compact; setCompact(v); write(COLLAPSED_KEY, v); };
  const toggleGroup = (title) => { const v = { ...closed, [title]: !closed[title] }; setClosed(v); write(CLOSED_KEY, v); };

  return (
    <aside className={`${compact ? 'w-16' : 'w-60'} shrink-0 bg-slate-900 text-slate-300 flex flex-col h-screen sticky top-0 transition-[width] duration-200`}
      aria-label="Main navigation">
      <div className={`py-5 flex items-center gap-3 border-b border-slate-800 ${compact ? 'justify-center px-2' : 'px-5'}`}>
        <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center shrink-0">
          <img src={coffeeBean} alt="" className="w-7 h-7" />
        </div>
        {!compact && (
          <div className="leading-tight">
            <div className="font-bold text-white tracking-tight">BEANS</div>
            <div className="text-[10px] text-slate-400">Bitcoin Encryption, Analysis<br />&amp; Network Security</div>
          </div>
        )}
      </div>

      <nav className={`flex-1 overflow-y-auto py-4 space-y-4 ${compact ? 'px-2' : 'px-3'}`}>
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((i) => !i.minRole || hasRole(user, i.minRole));
          if (!items.length) return null;
          const isClosed = !compact && closed[group.title];
          const hidden = isClosed ? items.reduce((n, i) => n + (i.badge ? (counts[i.badge] || 0) : 0), 0) : 0;
          return (
            <div key={group.title}>
              {compact ? (
                <div className="mx-2 mb-1.5 border-t border-slate-800" role="separator" />
              ) : (
                <button onClick={() => toggleGroup(group.title)} aria-expanded={!isClosed}
                  className="w-full px-2 mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded">
                  <span>{group.title}</span>
                  <span className="flex items-center gap-1">
                    {hidden > 0 && <span className="text-[10px] font-bold px-1.5 rounded bg-slate-700 text-slate-200">{hidden}</span>}
                    <ChevronDown className={`w-3 h-3 transition-transform ${isClosed ? '-rotate-90' : ''}`} />
                  </span>
                </button>
              )}
              {!isClosed && (
                <div className="space-y-0.5">
                  {items.map(({ id, label, icon: Icon, badge, urgent }) => {
                    const active = activeTab === id;
                    const n = badge ? counts[badge] : null;
                    return (
                      <button
                        key={id}
                        onClick={() => setActiveTab(id)}
                        title={compact ? label : undefined}
                        aria-label={label}
                        aria-current={active ? 'page' : undefined}
                        className={`relative w-full flex items-center rounded-lg text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                          compact ? 'justify-center py-2.5' : 'gap-2.5 px-2.5 py-2'} ${
                          active ? 'bg-blue-600 text-white' : 'hover:bg-slate-800 hover:text-white'}`}
                      >
                        <Icon className="w-4 h-4 shrink-0" />
                        {!compact && <span className="flex-1 text-left">{label}</span>}
                        {n > 0 && (
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                            compact ? 'absolute -top-0.5 -right-0.5 min-w-[16px] text-center' : ''} ${
                            active ? 'bg-white/20' : urgent ? 'bg-red-600 text-white pulse-dot' : 'bg-slate-700 text-slate-200'}`}>{n}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className={`border-t border-slate-800 text-[11px] space-y-2 ${compact ? 'px-2 py-3' : 'px-5 py-4'}`}>
        {!compact && (
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Offline mode
            </div>
            <div className="text-slate-500">SIH PS 26146 · NTRO</div>
          </div>
        )}
        {compact && <div className="flex justify-center" title="Offline mode"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /></div>}
        <button onClick={toggleCompact} aria-pressed={compact} aria-label={compact ? 'Expand sidebar' : 'Collapse sidebar'}
          title={compact ? 'Expand sidebar' : 'Collapse sidebar'}
          className={`w-full flex items-center gap-2 rounded-lg py-1.5 text-slate-400 hover:bg-slate-800 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${compact ? 'justify-center' : 'px-2'}`}>
          {compact ? <ChevronsRight className="w-4 h-4" /> : <><ChevronsLeft className="w-4 h-4" /> <span>Collapse</span></>}
        </button>
      </div>
    </aside>
  );
}
