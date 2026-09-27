import React, { useEffect, useState } from 'react';
import { BookOpen, Loader2, RefreshCw, Cpu, AlertCircle } from 'lucide-react';
import { hasRole, useSession } from '../session';

// Case narrative (beans/explain/narrative.py): a paragraph written by a local model from the alert's fact sheet.
// Every sentence carries the facts it was checked against; hover a citation to read the fact.
export default function NarrativePanel({ alertId }) {
  const { user } = useSession();
  const canWrite = hasRole(user, 'ANALYST');
  const [n, setN] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showFacts, setShowFacts] = useState(false);

  useEffect(() => {
    setN(null); setShowFacts(false);
    fetch(`/api/alerts/${alertId}/narrative`).then((r) => r.json()).then(setN).catch(() => setN({ cached: false }));
  }, [alertId]);

  const write = async (engine = 'auto') => {
    setBusy(true);
    try {
      const r = await fetch(`/api/alerts/${alertId}/narrative?engine=${engine}`, { method: 'POST' });
      setN(await r.json());
    } finally {
      setBusy(false);
    }
  };

  const factText = (i) => n?.facts?.[i - 1]?.text || '';
  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-3">
        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5"><BookOpen className="w-3.5 h-3.5" /> Case summary</div>
        {n?.cached && canWrite && (
          <button onClick={() => write()} disabled={busy} className="text-[11px] font-semibold text-blue-600 hover:underline flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Rewrite</button>
        )}
      </div>
      <div className="p-4 text-xs space-y-3">
        {busy && <div className="flex items-center gap-2 text-slate-500"><Loader2 className="w-4 h-4 animate-spin" /> Writing with the local model and checking every sentence against the facts (15-40 s on a CPU)…</div>}
        {!busy && n && !n.cached && (
          <div className="space-y-2">
            <p className="text-slate-500">{n.stale ? 'The alert changed since the last summary.' : 'No summary yet.'} A local model writes a short paragraph from BEANS's own findings; sentences that cite the wrong fact, add a number or speculate are removed.</p>
            {canWrite ? (
              <div className="flex gap-2">
                <button onClick={() => write('auto')} className="px-3 py-1.5 rounded-lg bg-blue-600 text-white font-bold flex items-center gap-1.5"><Cpu className="w-3.5 h-3.5" /> Write summary</button>
                <button onClick={() => write('template')} className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-800 font-bold">Facts only (instant)</button>
              </div>
            ) : <p className="text-slate-400">An analyst has to write it first.</p>}
          </div>
        )}
        {!busy && n?.cached && (
          <>
            <p className="leading-relaxed text-slate-800">
              {n.sentences.map((s, k) => (
                <span key={k}>
                  {s.text}{' '}
                  {s.facts.map((f) => (
                    <sup key={f} title={factText(f)} className="text-[9px] font-bold text-blue-600 cursor-help mr-0.5">F{f}</sup>
                  ))}{' '}
                </span>
              ))}
            </p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-400">
              <span>Written by <b className="text-slate-500">{n.engine}</b>{n.created_by ? ` for ${n.created_by}` : ''} · {n.generated_at}</span>
              {n.dropped_sentences > 0 && <span className="text-amber-600">{n.dropped_sentences} sentence(s) failed the fact check and were removed</span>}
              <button onClick={() => setShowFacts((v) => !v)} className="text-blue-600 hover:underline">{showFacts ? 'Hide' : 'Show'} the {n.facts.length} facts</button>
            </div>
            {n.note && <div className="flex items-start gap-1.5 text-[11px] text-amber-700"><AlertCircle className="w-3.5 h-3.5 mt-px" /> {n.note}</div>}
            {showFacts && (
              <ol className="list-none space-y-1 bg-slate-50 border border-slate-200 rounded-lg p-2.5">
                {n.facts.map((f) => <li key={f.id}><b className="text-blue-600 mr-1">{f.id}</b>{f.text}</li>)}
              </ol>
            )}
            <p className="text-[10px] text-slate-400">A reading aid. The evidence pack, the facts and the rules remain the record.</p>
          </>
        )}
      </div>
    </div>
  );
}
