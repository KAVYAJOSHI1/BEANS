import React, { useEffect, useState } from 'react';
import { Play, Pause, RotateCcw, Building2, Scissors, ArrowDown, Flag } from 'lucide-react';

const API = '/api';
const fmt = (v) => Number(v || 0).toFixed(4);

// Follow the money: hop-by-hop replay of a peel chain (change followed, peels listed), from /api/timeline/trace.
export default function MoneyTrail({ entity }) {
  const [trace, setTrace] = useState(null);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let live = true;
    setTrace(null);
    setStep(0);
    setPlaying(false);
    fetch(`${API}/timeline/trace${entity ? `?entity=${encodeURIComponent(entity)}` : ''}`)
      .then((r) => r.json()).then((t) => { if (live) setTrace(t); }).catch(() => {});
    return () => { live = false; };
  }, [entity]);

  const hops = trace?.hops || [];
  useEffect(() => {
    if (!playing) return undefined;
    if (step >= hops.length - 1) { setPlaying(false); return undefined; }
    const t = setTimeout(() => setStep((s) => s + 1), 900);
    return () => clearTimeout(t);
  }, [playing, step, hops.length]);

  if (!trace) return <div className="text-xs text-slate-400 p-6">Tracing…</div>;
  if (!hops.length) return <div className="text-xs text-slate-500 p-6">This wallet never spends: nothing to follow ({trace.stop_reason}).</div>;

  const start = trace.summary.start_amount || 1;
  const shown = hops.slice(0, step + 1);
  const cur = hops[step];
  const done = step === hops.length - 1;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
        {[
          ['Hops', trace.summary.hops],
          ['Started with', `${fmt(trace.summary.start_amount)} BTC`],
          ['Peeled off', `${fmt(trace.summary.peeled_total)} BTC`],
          ['Duration', `${trace.summary.duration_h} h`],
          ['Ends', trace.stop_reason],
        ].map(([k, v]) => (
          <div key={k} className="p-3 rounded-lg bg-white border border-slate-200">
            <div className="text-slate-500">{k}</div>
            <div className="font-bold text-slate-900 mt-0.5 truncate" title={String(v)}>{v}</div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
        <div className="flex items-center gap-2">
          <button onClick={() => { if (done) setStep(0); setPlaying(!playing); }}
            className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center gap-1">
            {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />} {playing ? 'Pause' : done ? 'Replay' : 'Play'}
          </button>
          <button onClick={() => { setPlaying(false); setStep(0); }} className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200"><RotateCcw className="w-3.5 h-3.5" /></button>
          <input type="range" min="0" max={hops.length - 1} value={step} onChange={(e) => { setPlaying(false); setStep(Number(e.target.value)); }}
            className="flex-1 accent-blue-600" />
          <span className="text-xs text-slate-600 w-28 text-right">hop {step + 1} / {hops.length}</span>
        </div>

        <div className="space-y-1 max-h-[520px] overflow-y-auto pr-1">
          {shown.map((h, i) => {
            const active = i === step;
            const pct = Math.max(2, (100 * h.change_amount) / start);
            return (
              <div key={h.txid}>
                {i > 0 && (
                  <div className="flex items-center gap-2 pl-4 text-[10px] text-slate-400 h-4">
                    <ArrowDown className="w-3 h-3" /> {h.minutes_since_previous} min later
                  </div>
                )}
                <div className={`rounded-lg border p-3 text-xs transition-all ${active ? 'border-blue-300 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white'}`}>
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-slate-900 text-white font-bold flex items-center justify-center text-[10px]">{h.hop}</span>
                    <span className="font-mono text-slate-700">{h.from.slice(0, 14)}…</span>
                    <span className="text-slate-500">spends {fmt(h.amount_in)} BTC</span>
                    <span className="text-slate-400">· {String(h.timestamp).slice(0, 16)} · relay {h.src_ip} {h.asn_type} {h.geo_country}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-[1fr_1fr] gap-2">
                    <div>
                      {h.peels.length === 0 && <span className="text-slate-400">no peel</span>}
                      {h.peels.slice(0, 4).map((p) => (
                        <div key={p.address} className="flex items-center gap-1.5">
                          <Scissors className="w-3 h-3 text-rose-500" />
                          <span className="font-mono">{fmt(p.amount)}</span>
                          <span className="text-slate-500">→</span>
                          {p.exchange ? (
                            <span className="font-bold text-red-700 flex items-center gap-1"><Building2 className="w-3 h-3" /> {p.exchange}</span>
                          ) : <span className="font-mono text-slate-500">{p.address.slice(0, 14)}…</span>}
                        </div>
                      ))}
                      {h.peels.length > 4 && <span className="text-slate-400">+{h.peels.length - 4} more outputs</span>}
                    </div>
                    <div>
                      <div className="flex justify-between text-slate-600">
                        <span>remaining (change)</span>
                        <span className="font-mono font-bold">{fmt(h.change_amount)} BTC{h.change_exchange ? ` → ${h.change_exchange}` : ''}</span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded mt-1">
                        <div className="h-2 rounded bg-indigo-500 transition-all duration-700" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          {done && (
            <div className="flex items-center gap-2 text-xs font-bold text-slate-700 p-2">
              <Flag className="w-3.5 h-3.5 text-red-600" /> {trace.stop_reason}
              {trace.summary.exchanges_reached.length > 0 && <span className="font-normal text-slate-500">· exchanges reached: {trace.summary.exchanges_reached.join(', ')}</span>}
            </div>
          )}
        </div>
        {cur && <p className="text-[10px] text-slate-400">The largest output of each spend is treated as the change and followed; the rest are peels. Exchanges are marked from the attribution list.</p>}
      </div>
    </div>
  );
}
