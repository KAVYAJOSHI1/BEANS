import React from 'react';
import { Eye, ArrowRightLeft, Building2, Check, X, Clock, Radio } from 'lucide-react';

const API = '/api';
const short = (s, n = 14) => (s && s.length > n + 4 ? `${s.slice(0, n)}…` : s);

export default function Watchlist({ events, watchlist, alerts, onChanged, onSelectAlert, onInspectEntity }) {
  const open = events.filter((e) => e.status === 'OPEN');
  const done = events.filter((e) => e.status !== 'OPEN');
  const alertFor = (address) => alerts.find((a) => a.entity_id === address);

  const call = async (path, opts) => {
    await fetch(`${API}${path}`, opts);
    onChanged();
  };
  const ack = (id) => call(`/watch-events/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'ACKNOWLEDGED' }),
  });
  const unwatch = (address) => call(`/watchlist/${encodeURIComponent(address)}`, { method: 'DELETE' });

  const EventCard = ({ e }) => {
    const alert = alertFor(e.address);
    return (
      <div className={`rounded-xl border p-4 text-xs space-y-2 ${e.status === 'OPEN' ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            {e.status === 'OPEN' && <span className="w-2 h-2 rounded-full bg-red-500 pulse-dot" />}
            <ArrowRightLeft className="w-4 h-4 text-red-600" />
            <span className="font-bold text-slate-900 text-sm">{Number(e.amount_btc).toFixed(8)} BTC moved</span>
            <span className="text-slate-500">from</span>
            <button onClick={() => onInspectEntity(e.address)} className="font-mono text-blue-700 hover:underline">{short(e.address, 18)}</button>
          </div>
          <span className="text-slate-500 whitespace-nowrap flex items-center gap-1"><Clock className="w-3 h-3" /> {String(e.ts).slice(0, 19)} UTC</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <span className="text-slate-500">Destination: </span>
            {e.vasp ? (
              <span className="font-bold text-red-700 inline-flex items-center gap-1">
                <Building2 className="w-3 h-3" /> {e.vasp} {e.vasp_in_jurisdiction ? '(India, §94 BNSS)' : '(outside India)'}
              </span>
            ) : <span className="text-slate-700">no known exchange within 4 hops yet</span>}
          </div>
          <div><span className="text-slate-500">First relay: </span><span className="font-mono">{e.first_spy_ip || 'unknown'}</span> <span className="text-slate-500">{e.first_spy_asn_type} {e.first_spy_country}</span></div>
          <div><span className="text-slate-500">Moved </span><b>{e.minutes_since_move} min</b><span className="text-slate-500"> before the latest data · tx </span><span className="font-mono">{short(e.txid, 12)}</span></div>
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-slate-500">Watched because: {e.watch_reason === 'AUTO_TAINT_WATCH' ? 'taint-watch directive' : e.watch_reason === 'CASE' ? `suspect in case #${e.case_id}` : 'analyst'}</span>
          <span className="flex-1" />
          {alert && (
            <button onClick={() => onSelectAlert(alert)} className={`px-3 py-1.5 rounded-lg font-bold ${e.vasp ? 'bg-red-600 text-white hover:bg-red-700' : 'bg-slate-900 text-white'}`}>
              {e.vasp ? 'Open alert → draft freeze request' : 'Open alert'}
            </button>
          )}
          {e.status === 'OPEN' && (
            <button onClick={() => ack(e.event_id)} className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 font-bold text-slate-700 flex items-center gap-1 hover:bg-slate-50">
              <Check className="w-3.5 h-3.5" /> Acknowledge
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Radio className="w-4 h-4 text-red-600" /> Movements of watched funds</h2>
            <p className="text-xs text-slate-500 mt-1 max-w-3xl">
              Every new file (upload, watch folder, re-score) is checked against the watchlist. A spend by a watched wallet is
              raised once, traced to known exchanges and pushed to the SIEM webhooks as CRITICAL. Funds that just reached an
              exchange can still be frozen there.
            </p>
          </div>
          <span className="text-xs font-bold px-2 py-1 rounded-lg bg-red-50 text-red-700 border border-red-200">{open.length} open</span>
        </div>
        {events.length === 0 && <div className="text-xs text-slate-400 py-6 text-center">No watched wallet has moved funds yet.</div>}
        <div className="space-y-2">{open.map((e) => <EventCard key={e.event_id} e={e} />)}</div>
        {done.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer font-semibold text-slate-600">Acknowledged ({done.length})</summary>
            <div className="space-y-2 mt-2">{done.map((e) => <EventCard key={e.event_id} e={e} />)}</div>
          </details>
        )}
      </section>

      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
        <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Eye className="w-4 h-4 text-blue-600" /> Watched wallets ({watchlist.length})</h2>
        <div className="overflow-x-auto border border-slate-200 rounded-lg">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500 uppercase text-[10px] tracking-wider">
              <tr><th className="text-left p-2">Wallet</th><th className="text-left p-2">Reason</th><th className="text-left p-2">Watched from (data time)</th>
                <th className="text-left p-2">Balance then (BTC)</th><th className="text-left p-2">Movements</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {watchlist.length === 0 && <tr><td colSpan={6} className="p-4 text-center text-slate-400">Nothing is being watched. Taint-watch alerts are added automatically; you can also watch any alert or case.</td></tr>}
              {watchlist.map((w) => (
                <tr key={w.address}>
                  <td className="p-2"><button onClick={() => onInspectEntity(w.address)} className="font-mono text-blue-700 hover:underline">{short(w.address, 22)}</button></td>
                  <td className="p-2">{w.reason === 'AUTO_TAINT_WATCH' ? 'taint-watch directive' : w.reason === 'CASE' ? `case #${w.case_id}` : 'analyst'}</td>
                  <td className="p-2 text-slate-600">{String(w.watched_from).slice(0, 19)}</td>
                  <td className="p-2 font-mono">{w.balance_at_watch != null ? Number(w.balance_at_watch).toFixed(6) : '—'}</td>
                  <td className="p-2">{w.movements > 0 ? <b className="text-red-600">{w.movements}</b> : <span className="text-slate-400">0</span>}</td>
                  <td className="p-2 text-right">
                    <button onClick={() => unwatch(w.address)} title="Stop watching" className="p-1 rounded hover:bg-slate-100 text-slate-500"><X className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
