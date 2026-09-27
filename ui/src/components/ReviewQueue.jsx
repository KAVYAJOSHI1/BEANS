import React, { useEffect, useState } from 'react';
import { ListChecks, ThumbsUp, ThumbsDown, Search, RefreshCw, Loader2, HelpCircle } from 'lucide-react';
import { hasRole, useSession } from '../session';
import { ActionBadge } from './ActionPanel';

// Active learning: the alerts the model is least sure about, and the wallets that just missed the alert threshold.
// A verdict here is stored as training feedback; "Retrain now" re-runs the engines so the model learns from it.
const card = 'bg-white rounded-xl border border-slate-200 shadow-sm p-5';
const short = (s, n = 18) => (s && s.length > n + 4 ? `${s.slice(0, n)}…${s.slice(-4)}` : s);

function Meter({ value }) {
  return (
    <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden" title={`uncertainty ${value}`}>
      <div className="h-full bg-amber-500" style={{ width: `${Math.round(100 * value)}%` }} />
    </div>
  );
}

export default function ReviewQueue({ onSelectAlert, onInspectEntity, onDataChanged }) {
  const { user } = useSession();
  const canJudge = hasRole(user, 'ANALYST');
  const [q, setQ] = useState(null);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = () => fetch('/api/review/queue?limit=25').then((r) => r.json()).then(setQ).catch(() => setQ({ error: true }));
  useEffect(() => { load(); }, []);

  const judge = async (entity, label) => {
    setBusy(entity);
    const r = await fetch('/api/review/verdict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entity_id: entity, label }),
    });
    const body = await r.json().catch(() => ({}));
    setBusy(null);
    setMsg(r.ok ? { ok: true, text: `Recorded: ${short(entity)} is ${label === 'TRUE_POSITIVE' ? 'illicit' : 'legitimate'}.` } : { ok: false, text: body.detail });
    load();
  };
  const retrain = async () => {
    setBusy('retrain');
    const r = await fetch('/api/seeds/repropagate', { method: 'POST' });
    setBusy(null);
    setMsg(r.ok ? { ok: true, text: 'Re-scored with your verdicts. The queue shows what the model is unsure about now.' } : { ok: false, text: 'Retraining failed.' });
    load();
    onDataChanged?.();
  };

  if (!q) return <div className="py-24 text-center text-sm text-slate-400">Loading…</div>;
  if (q.error) return <div className="py-24 text-center text-sm text-red-500">Review queue unavailable.</div>;

  const Verdict = ({ entity }) => (canJudge ? (
    <div className="flex gap-1.5 shrink-0">
      <button disabled={busy === entity} onClick={() => judge(entity, 'TRUE_POSITIVE')}
        className="px-2 py-1 rounded-md text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 flex items-center gap-1">
        <ThumbsUp className="w-3 h-3" /> Illicit</button>
      <button disabled={busy === entity} onClick={() => judge(entity, 'FALSE_POSITIVE')}
        className="px-2 py-1 rounded-md text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 flex items-center gap-1">
        <ThumbsDown className="w-3 h-3" /> Legitimate</button>
    </div>
  ) : null);

  return (
    <div className="space-y-6">
      <section className={`${card} flex flex-wrap items-start justify-between gap-4`}>
        <div className="max-w-3xl">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><ListChecks className="w-4 h-4 text-blue-600" /> Where your verdict teaches the model most</h2>
          <p className="text-xs text-slate-500 mt-1">
            Alerts the model is least sure about come first, then wallets that scored just under the alert threshold
            ({q.near_miss_min.toFixed(2)} to {q.alert_threshold.toFixed(2)}), where a missed criminal would hide. Each verdict is
            stored as training feedback. <b>{q.verdicts_so_far}</b> wallet(s) judged so far.
          </p>
        </div>
        {canJudge && (
          <button onClick={retrain} disabled={busy === 'retrain'}
            className="px-3 py-2 rounded-lg text-xs font-bold bg-blue-600 text-white hover:bg-blue-700 flex items-center gap-1.5">
            {busy === 'retrain' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />} Retrain now
          </button>
        )}
      </section>
      {msg && <div className={`text-xs px-3 py-2 rounded-lg border ${msg.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>{msg.text}</div>}

      <section className={card}>
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><HelpCircle className="w-4 h-4 text-amber-500" /> Uncertain alerts ({q.uncertain_alerts.length})</h3>
        <div className="divide-y divide-slate-100">
          {q.uncertain_alerts.map((a) => (
            <div key={a.alert_id} className="py-3 flex flex-wrap items-center gap-3 text-xs">
              <Meter value={a.uncertainty} />
              <button onClick={() => onSelectAlert(a.alert_id)} className="font-mono text-blue-700 hover:underline">{short(a.entity_id)}</button>
              <span className="text-slate-500">{a.alert_type}</span>
              <span className="font-bold tabular-nums">risk {a.risk_score}</span>
              {a.action && <ActionBadge action={a.action} />}
              <span className="text-slate-500 flex-1 min-w-[12rem]">{a.why_review.join(' · ')}</span>
              <Verdict entity={a.entity_id} />
            </div>
          ))}
          {!q.uncertain_alerts.length && <p className="py-6 text-center text-xs text-slate-400">Every open alert has a verdict.</p>}
        </div>
      </section>

      <section className={card}>
        <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2"><Search className="w-4 h-4 text-blue-600" /> Near misses: not alerted, just under the threshold ({q.near_misses.length})</h3>
        <div className="divide-y divide-slate-100">
          {q.near_misses.map((w) => (
            <div key={w.address} className="py-3 flex flex-wrap items-center gap-3 text-xs">
              <span className="w-20 font-bold tabular-nums text-slate-700">P {Number(w.p).toFixed(2)}</span>
              <button onClick={() => onInspectEntity(w.address)} className="font-mono text-blue-700 hover:underline">{short(w.address)}</button>
              <span className="text-slate-500">looks like {w.typology_pred}</span>
              <span className="text-slate-500 flex-1 min-w-[12rem]">{w.why_review.join(' · ')}</span>
              <Verdict entity={w.address} />
            </div>
          ))}
          {!q.near_misses.length && <p className="py-6 text-center text-xs text-slate-400">No wallets just under the threshold.</p>}
        </div>
      </section>
    </div>
  );
}
