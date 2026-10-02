import React, { useEffect, useState } from 'react';
import { Shuffle, RefreshCw } from 'lucide-react';

// Mixer Lab (E6): who a CoinJoin's outputs could belong to. Equal-valued "pool" outputs are unlinkable from amounts
// (probability 1/k by construction); change outputs are pinned to an input by amount matching. Nothing here unmixes a CoinJoin.
const card = 'bg-white rounded-xl border border-slate-200 shadow-sm p-5';
const short = (s, n = 10) => (s && s.length > n + 4 ? `${s.slice(0, n)}…${s.slice(-3)}` : s);

function heat(p) { return p >= 0.99 ? 'bg-emerald-600 text-white' : p > 0 ? 'bg-amber-100 text-amber-900' : 'bg-slate-50 text-slate-300'; }

function Matrix({ detail }) {
  const srcs = [...new Set(detail.links.map((l) => l.src))];
  const dsts = [...new Set(detail.links.map((l) => l.dst))];
  const at = (s, d) => detail.links.find((l) => l.src === s && l.dst === d);
  const taint = (a, k) => (detail.links.find((l) => l[k === 'src' ? 'src' : 'dst'] === a) || {})[`${k}_taint`] || 0;
  return (
    <div className="overflow-auto max-h-[560px] border border-slate-200 rounded-lg">
      <table className="text-[10px] border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-10 bg-slate-100 p-1.5 text-left">input ↓ / output →</th>
            {dsts.map((d) => {
              const k = detail.links.find((l) => l.dst === d)?.kind;
              return <th key={d} className="sticky top-0 bg-slate-100 p-1.5 font-mono font-normal" title={d}>
                {short(d)}<div className="text-[9px] text-slate-400">{k === 'CHANGE' ? 'change' : k === 'POOL' ? 'pool' : '?'}</div></th>;
            })}
          </tr>
        </thead>
        <tbody>
          {srcs.map((s) => (
            <tr key={s}>
              <th className="sticky left-0 bg-slate-100 p-1.5 font-mono font-normal text-left" title={s}>
                {short(s)}{taint(s, 'src') > 0.01 && <span className="ml-1 px-1 rounded bg-rose-100 text-rose-700 font-sans font-bold">taint {taint(s, 'src').toFixed(2)}</span>}
              </th>
              {dsts.map((d) => {
                const l = at(s, d);
                return <td key={d} className={`p-1.5 text-center border border-white ${heat(l ? l.prob : 0)}`} title={l ? `${l.kind} · ${(100 * l.prob).toFixed(1)}%` : 'no link'}>
                  {l ? `${Math.round(100 * l.prob)}%` : ''}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MixerLab() {
  const [list, setList] = useState(null);
  const [sel, setSel] = useState(null);
  const [detail, setDetail] = useState(null);
  const load = () => fetch('/api/mixer/transactions').then((r) => r.json()).then(setList).catch(() => setList({ error: true }));
  useEffect(() => { load(); }, []);
  const choose = (txid) => {
    setSel(txid);
    fetch(`/api/mixer/${txid}`).then((r) => (r.ok ? r.json() : null)).then(setDetail).catch(() => setDetail(null));
  };

  if (!list) return <div className="py-24 text-center text-sm text-slate-400">Loading…</div>;
  const txs = list.transactions || [];

  return (
    <div className="space-y-5">
      <div className={`${card} flex flex-wrap items-center gap-3`}>
        <Shuffle className="w-5 h-5 text-blue-600" />
        <div className="flex-1 min-w-[260px]">
          <h2 className="font-bold text-slate-900">Mixer Lab</h2>
          <p className="text-xs text-slate-500">
            Probable input→output links inside CoinJoins. Equal outputs share the same probability (1/k, the anonymity set); a change output is
            linked to the input whose amount fits. Risk is carried through these links with that confidence, so a tainted participant's change stays tainted
            and a pool output carries taint/k. This measures how much a mix hides; it does not unmix it.
          </p>
        </div>
        <button onClick={load} className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-xs font-bold flex items-center gap-1 hover:bg-slate-200">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {txs.length === 0 ? (
        <div className={`${card} text-sm text-slate-500`}>No mixing transactions were found in the loaded data.</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-5">
          <div className={`${card} p-0 overflow-hidden`}>
            <div className="px-4 py-2.5 text-[10px] uppercase tracking-wider text-slate-500 bg-slate-50">{txs.length} mixing transactions · most informative first</div>
            <div className="divide-y divide-slate-100 max-h-[620px] overflow-y-auto">
              {txs.map((t) => (
                <button key={t.txid} onClick={() => choose(t.txid)} className={`w-full text-left px-4 py-3 text-xs hover:bg-slate-50 ${sel === t.txid ? 'bg-blue-50' : ''}`}>
                  <div className="flex justify-between gap-2"><span className="font-mono font-semibold text-slate-900">{short(t.txid, 14)}</span>
                    <span className="text-slate-400">{String(t.timestamp || '').slice(0, 16)}</span></div>
                  <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                    <span className="px-1.5 rounded bg-slate-100 text-slate-700">anonymity set {t.anonymity_set}</span>
                    <span className={`px-1.5 rounded ${t.certain_change ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}`}>{t.certain_change} certain change link{t.certain_change === 1 ? '' : 's'}</span>
                    {t.tainted_inputs > 0 && <span className="px-1.5 rounded bg-rose-100 text-rose-700 font-bold">{t.tainted_inputs} tainted input{t.tainted_inputs === 1 ? '' : 's'}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className={`${card} min-w-0`}>
            {!detail && <div className="h-full min-h-[240px] flex items-center justify-center text-sm text-slate-400">Select a mixing transaction to see its link matrix.</div>}
            {detail && (
              <div className="space-y-3">
                <div className="text-xs text-slate-600"><span className="font-mono font-semibold text-slate-900">{detail.txid}</span> · anonymity set <b>{detail.anonymity_set}</b></div>
                <Matrix detail={detail} />
                <div className="flex flex-wrap gap-3 text-[10px] text-slate-500">
                  <span><span className="inline-block w-3 h-3 align-middle rounded bg-emerald-600" /> certain (change matched by amount)</span>
                  <span><span className="inline-block w-3 h-3 align-middle rounded bg-amber-100 border border-amber-200" /> possible (1/k or shared fit)</span>
                </div>
                <p className="text-[11px] text-slate-400">{detail.note}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
