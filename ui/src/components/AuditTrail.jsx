import React, { useEffect, useState } from 'react';
import { ScrollText, ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react';

const API = '/api';
const input = 'px-2.5 py-1.5 rounded-md border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs';

// Who did what, when. Every row is hash-chained to the one before it (beans/api/db.py), so "Verify chain"
// shows whether anything in the trail was edited or deleted after the fact.
export default function AuditTrail() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ investigator: '', action: '' });
  const [check, setCheck] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    const q = new URLSearchParams({ limit: '500' });
    if (filter.investigator) q.set('investigator', filter.investigator);
    if (filter.action) q.set('action', filter.action);
    const r = await fetch(`${API}/audit?${q}`).catch(() => null);
    if (!r || !r.ok) { setError(r ? (await r.json().catch(() => ({}))).detail : 'API unreachable'); return; }
    setError(null);
    setRows(await r.json());
  };
  const verify = async () => setCheck(await fetch(`${API}/audit/verify`).then((r) => r.json()).catch(() => null));
  useEffect(() => { load(); verify(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const actions = [...new Set(rows.map((r) => r.action))].sort();
  const people = [...new Set(rows.map((r) => r.investigator))].sort();

  return (
    <div className="space-y-6">
      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><ScrollText className="w-4 h-4 text-blue-600" /> Audit trail</h2>
            <p className="text-xs text-slate-500 mt-1 max-w-3xl">
              Every login, triage decision, legal draft, approval, export and refused request, under the user's name.
              Each row carries a SHA-256 of the previous row, so editing or deleting an entry breaks the chain.
            </p>
          </div>
          <button onClick={verify} className="px-3 py-1.5 rounded-md border border-slate-200 text-xs font-bold text-slate-700 hover:bg-slate-50 flex items-center gap-1">
            <RefreshCw className="w-3.5 h-3.5" /> Verify chain
          </button>
        </div>

        {check && (
          <div className={`text-xs px-3 py-2 rounded-lg border flex items-center gap-2 ${check.intact ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
            {check.intact ? <ShieldCheck className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
            {check.intact
              ? <span>Chain intact: {check.checked} entries verified{check.legacy_unchained ? ` (${check.legacy_unchained} older entries predate the chain)` : ''}. Head <span className="font-mono">{(check.head || '').slice(0, 16)}…</span></span>
              : <span>Chain broken at entry #{check.first_bad_id}: {check.reason}. The trail was changed outside BEANS.</span>}
          </div>
        )}
        {error && <div className="text-xs px-3 py-2 rounded-lg border bg-red-50 border-red-200 text-red-700">{error}</div>}

        <form className="flex flex-wrap gap-2 items-end text-xs" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label className="flex flex-col"><span className="font-semibold text-slate-600">User</span>
            <select className={input} value={filter.investigator} onChange={(e) => setFilter({ ...filter, investigator: e.target.value })}>
              <option value="">all</option>{people.map((p) => <option key={p}>{p}</option>)}
            </select></label>
          <label className="flex flex-col"><span className="font-semibold text-slate-600">Action</span>
            <select className={input} value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })}>
              <option value="">all</option>{actions.map((a) => <option key={a}>{a}</option>)}
            </select></label>
          <button className="px-3 py-1.5 rounded-md bg-blue-600 text-white font-bold">Filter</button>
        </form>

        <div className="border border-slate-200 rounded-lg overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr><th className="p-2">#</th><th className="p-2">When (UTC)</th><th className="p-2">User</th><th className="p-2">Action</th><th className="p-2">Target</th><th className="p-2">Details</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.id} className={r.action === 'ACCESS_DENIED' || r.action === 'LOGIN_FAILED' ? 'bg-red-50/60' : ''}>
                  <td className="p-2 text-slate-400 font-mono">{r.id}</td>
                  <td className="p-2 whitespace-nowrap font-mono">{String(r.created_at).slice(0, 19)}</td>
                  <td className="p-2 font-bold text-slate-800">{r.investigator}</td>
                  <td className="p-2"><span className="px-1.5 py-0.5 rounded bg-slate-100 font-semibold">{r.action}</span></td>
                  <td className="p-2 font-mono truncate max-w-[16rem]" title={r.entity_id}>{r.entity_type}: {r.entity_id}</td>
                  <td className="p-2 font-mono text-slate-500 truncate max-w-[24rem]" title={JSON.stringify(r.details)}>
                    {r.details && Object.keys(r.details).length ? JSON.stringify(r.details) : ''}
                  </td>
                </tr>
              ))}
              {!rows.length && !error && <tr><td colSpan={6} className="p-4 text-center text-slate-400">No entries.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
