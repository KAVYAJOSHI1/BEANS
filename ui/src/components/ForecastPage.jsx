import React, { useEffect, useState } from 'react';
import { Timer, RefreshCw, Building2 } from 'lucide-react';

// Interdiction queue (E7): wallets that still hold coins, ordered by how soon they are expected to reach an exchange.
// The window is empirical (delays of cash-outs already seen for the same typology), not a prediction of a moment.
const card = 'bg-white rounded-xl border border-slate-200 shadow-sm p-5';
const short = (s, n = 16) => (s && s.length > n + 4 ? `${s.slice(0, n)}…${s.slice(-4)}` : s);
const STATE = {
  IN_WINDOW: ['In window now', 'bg-rose-50 text-rose-700 border-rose-200'],
  OVERDUE: ['Overdue', 'bg-amber-50 text-amber-700 border-amber-200'],
  EXPECTED_LATER: ['Expected later', 'bg-slate-50 text-slate-600 border-slate-200'],
};
const fmtMin = (m) => {
  const a = Math.abs(m);
  const t = a >= 1440 ? `${(a / 1440).toFixed(1)} d` : a >= 60 ? `${(a / 60).toFixed(1)} h` : `${Math.round(a)} min`;
  return m < 0 ? `${t} ago` : `in ${t}`;
};

export default function ForecastPage({ onSelectAlert, onInspectEntity }) {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('ALL');
  const load = () => fetch('/api/forecast').then((r) => r.json()).then(setData).catch(() => setData({ error: true }));
  useEffect(() => { load(); }, []);

  if (!data) return <div className="py-24 text-center text-sm text-slate-400">Loading…</div>;
  if (data.error) return <div className={card}>The forecast could not be loaded.</div>;
  const rows = (data.pending || []).filter((p) => filter === 'ALL' || p.window.state === filter);
  const n = (s) => (data.pending || []).filter((p) => p.window.state === s).length;

  return (
    <div className="space-y-5">
      <div className={`${card} flex flex-wrap items-center gap-3`}>
        <Timer className="w-5 h-5 text-blue-600" />
        <div className="flex-1 min-w-[260px]">
          <h2 className="font-bold text-slate-900">Cash-out forecast</h2>
          <p className="text-xs text-slate-500">
            Wallets that still hold coins, with the window in which similar actors cashed out and the exchange they most often used.
            Use it to prepare a freeze or Section 94 request before the deposit. The window is the 25th-75th percentile of observed delays
            from the wallet's last receipt; destination odds come from the same typology and the actor's own history.
          </p>
        </div>
        <button onClick={load} className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-bold flex items-center gap-1 hover:bg-slate-200">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        {[['ALL', `All (${(data.pending || []).length})`], ...Object.entries(STATE).map(([k, [l]]) => [k, `${l} (${n(k)})`])].map(([k, l]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`px-3 py-1.5 rounded-lg font-bold border ${filter === k ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}>{l}</button>
        ))}
      </div>

      <div className={`${card} p-0 overflow-hidden`}>
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-[10px]">
            <tr>
              <th className="text-left px-4 py-2.5">Wallet</th><th className="text-left px-3 py-2.5">Typology</th>
              <th className="text-right px-3 py-2.5">Risk</th><th className="text-right px-3 py-2.5">Holds (BTC)</th>
              <th className="text-left px-3 py-2.5">Window</th><th className="text-left px-3 py-2.5">Likely exchange</th>
              <th className="text-left px-3 py-2.5">State</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">No wallets in this state.</td></tr>}
            {rows.map((p) => {
              const [label, cls] = STATE[p.window.state] || [p.window.state, ''];
              const top = (p.destinations || [])[0];
              return (
                <tr key={p.alert_id} onClick={() => onSelectAlert(p.alert_id)} className="hover:bg-blue-50/40 cursor-pointer">
                  <td className="px-4 py-3 font-mono font-semibold text-slate-900">
                    {short(p.entity_id)}
                    <button onClick={(e) => { e.stopPropagation(); onInspectEntity(p.entity_id); }} className="ml-2 text-[10px] font-sans font-bold text-blue-600 hover:underline">Entity 360</button>
                  </td>
                  <td className="px-3 py-3 text-slate-700">{(p.typology || '').replace(/_/g, ' ')}</td>
                  <td className="px-3 py-3 text-right font-mono">{Math.round(p.risk_score)}</td>
                  <td className="px-3 py-3 text-right font-mono">{p.balance_btc?.toFixed(4)}</td>
                  <td className="px-3 py-3 text-slate-600">
                    <div className="font-mono">{p.window.from.slice(5, 16)} → {p.window.to.slice(5, 16)}</div>
                    <div className="text-[10px] text-slate-400">starts {fmtMin(p.window.minutes_to_window_start)} · median {Math.round(p.delay_minutes.p50)} min · n={p.samples}</div>
                  </td>
                  <td className="px-3 py-3 text-slate-700">
                    {top ? (<><span className="flex items-center gap-1"><Building2 className="w-3 h-3 text-slate-400" /> {top.vasp}</span>
                      <span className="text-[10px] text-slate-400">{Math.round(100 * top.probability)}%{p.in_jurisdiction ? ' · India (§94 BNSS)' : ''}</span></>) : '—'}
                  </td>
                  <td className="px-3 py-3"><span className={`px-2 py-0.5 rounded border text-[10px] font-bold ${cls}`}>{label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-400">
        Destination odds are near chance on synthetic data (actors there pick exchanges at random); they only carry information where real actors reuse exchanges.
        See the Model Card for the backtest.
      </p>
    </div>
  );
}
