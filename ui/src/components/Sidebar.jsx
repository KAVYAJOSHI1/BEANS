import React from 'react';
import {
  Shield, Activity, AlertTriangle, Network, Clock, Globe, UserCheck, Briefcase, Cpu, UploadCloud,
} from 'lucide-react';

export const NAV_GROUPS = [
  { title: 'Monitor', items: [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'alerts', label: 'Alert Triage', icon: AlertTriangle, badge: 'alerts' },
  ] },
  { title: 'Investigate', items: [
    { id: 'graph', label: 'Link Graph', icon: Network },
    { id: 'entity', label: 'Entity 360', icon: UserCheck },
    { id: 'timeline', label: 'Timeline', icon: Clock },
    { id: 'geomap', label: 'Geo Map', icon: Globe },
  ] },
  { title: 'Report', items: [
    { id: 'cases', label: 'Cases & Evidence', icon: Briefcase, badge: 'cases' },
    { id: 'modelcard', label: 'Model Card', icon: Cpu },
  ] },
  { title: 'Data', items: [
    { id: 'ingest', label: 'Ingest & Seeds', icon: UploadCloud },
  ] },
];

export const PAGE_TITLES = Object.fromEntries(
  NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.id, { label: i.label, group: g.title }])),
);

export default function Sidebar({ activeTab, setActiveTab, counts = {} }) {
  return (
    <aside className="w-60 shrink-0 bg-slate-900 text-slate-300 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 flex items-center gap-3 border-b border-slate-800">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white">
          <Shield className="w-5 h-5" />
        </div>
        <div className="leading-tight">
          <div className="font-bold text-white tracking-tight">BEANS</div>
          <div className="text-[10px] text-slate-400">Bitcoin Encryption, Analysis<br />&amp; Network Security</div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.title}>
            <div className="px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{group.title}</div>
            <div className="space-y-0.5">
              {group.items.map(({ id, label, icon: Icon, badge }) => {
                const active = activeTab === id;
                const n = badge ? counts[badge] : null;
                return (
                  <button
                    key={id}
                    onClick={() => setActiveTab(id)}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors ${
                      active ? 'bg-blue-600 text-white' : 'hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="flex-1 text-left">{label}</span>
                    {n > 0 && (
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${active ? 'bg-white/20' : 'bg-slate-700 text-slate-200'}`}>{n}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-slate-800 text-[11px] space-y-1">
        <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Offline mode
        </div>
        <div className="text-slate-500">SIH PS 26146 · NTRO</div>
      </div>
    </aside>
  );
}
