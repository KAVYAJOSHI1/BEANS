import React, { useEffect, useRef, useState } from 'react';
import { Satellite, FolderInput, Activity, AlertTriangle, CircleDot, FileText, Terminal } from 'lucide-react';
import Chart from './Chart';
import { SEVERITY_COLOR } from '../risk';

// Live monitoring: the P2P collector and `beans watch` run as their own processes and write status files into the
// inbox; this page polls /api/live/status every 5 s and refreshes the rest of the dashboard when new data lands.
const card = 'bg-white rounded-xl border border-slate-200 shadow-sm p-5';
const ago = (s) => (s == null ? '—' : s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${(s / 3600).toFixed(1)} h ago`);
const short = (s, n = 14) => (s && s.length > n + 4 ? `${s.slice(0, n)}…` : s);

function State({ alive, stopped, label }) {
  const cls = alive ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : stopped ? 'bg-slate-100 text-slate-600 border-slate-200' : 'bg-amber-50 text-amber-700 border-amber-200';
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-bold px-2 py-0.5 rounded-md border ${cls}`}>
      <CircleDot className={`w-3 h-3 ${alive ? 'pulse-dot' : ''}`} /> {label}
    </span>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-lg font-bold text-slate-900 tabular-nums">{value ?? '—'}</div>
    </div>
  );
}

export default function LiveMonitor({ onSelectAlert, onDataChanged }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  const lastTx = useRef(null);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const r = await fetch('/api/live/status');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const j = await r.json();
        if (stop) return;
        setS(j); setErr(null);
        if (lastTx.current != null && j.transactions !== lastTx.current) onDataChanged?.();   // new data: refresh counts
        lastTx.current = j.transactions;
      } catch (e) {
        if (!stop) setErr(String(e.message || e));
      }
    };
    tick();
    const t = setInterval(tick, 5000);
    return () => { stop = true; clearInterval(t); };
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!s) return <div className="py-24 text-center text-sm text-slate-400">{err ? `Live status unavailable: ${err}` : 'Loading…'}</div>;
  const c = s.collector, w = s.watcher;
  const rate = s.tx_per_minute || [];

  return (
    <div className="space-y-6">
      {!c && !w && (
        <section className={`${card} text-xs space-y-2`}>
          <div className="font-bold text-slate-900 flex items-center gap-2 text-sm"><Terminal className="w-4 h-4 text-blue-600" /> Start live monitoring</div>
          <p className="text-slate-500">Neither the collector nor the ingest worker has reported from <span className="font-mono">{s.folder}</span>. Start the server with <span className="font-mono">--watch</span> and the collector:</p>
          <pre className="bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto">{`beans serve --watch ${s.folder}                  # dashboard + ingest worker (one process)
beans collect --dns-seed --out ${s.folder}      # live mainnet (needs internet)
# or, in one command: beans live`}</pre>
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className={`${card} space-y-4`}>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Satellite className="w-4 h-4 text-blue-600" /> P2P collector</h2>
            {c ? <State alive={c.alive} stopped={c.running === false} label={c.alive ? 'Collecting' : c.running === false ? 'Stopped' : 'No heartbeat'} />
              : <State label="Not running" stopped />}
          </div>
          {c ? (
            <>
              <div className="grid grid-cols-3 gap-4">
                <Stat label="Peers" value={c.peers} />
                <Stat label="Transactions" value={c.tx?.toLocaleString()} />
                <Stat label="Announcements" value={c.inv?.toLocaleString()} />
                <Stat label="Rows pending" value={c.pending_rows?.toLocaleString()} />
                <Stat label="Files written" value={c.files} />
                <Stat label="Inputs resolved" value={c.resolver ? c.resolved_prevouts?.toLocaleString() : 'no resolver'} />
              </div>
              <div className="text-[11px] text-slate-500">
                Heartbeat {ago(c.age_s)} · file every {c.rotate_s} s · started {new Date(c.started_at * 1000).toLocaleTimeString()}
                {c.resolver_errors > 0 && <span className="text-amber-600"> · {c.resolver_errors} resolver errors</span>}
              </div>
              <p className="text-[11px] text-slate-400">The IP on a live row is the peer that relayed the transaction to the collector, not its sender.</p>
            </>
          ) : <p className="text-xs text-slate-400">No <span className="font-mono">collector.status</span> in the folder.</p>}
        </section>

        <section className={`${card} space-y-4`}>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><FolderInput className="w-4 h-4 text-blue-600" /> Ingest worker</h2>
            {w ? <State alive={w.alive} stopped={w.running === false}
              label={w.running === false ? 'Stopped' : !w.alive ? 'No heartbeat' : w.scoring ? 'Scoring…' : 'Watching'} />
              : <State label="Not running" stopped />}
          </div>
          <div className="grid grid-cols-3 gap-4">
            <Stat label="Files scored" value={w?.files_done} />
            <Stat label="Waiting" value={s.files_waiting.length} />
            <Stat label="Failed" value={w?.files_failed} />
            {w?.scoring_runs != null && <Stat label="Scoring runs" value={w.scoring_runs} />}
            {w?.unscored_rows != null && <Stat label="Rows awaiting scoring" value={w.unscored_rows?.toLocaleString()} />}
            {w?.last_score_s != null && <Stat label="Last scoring" value={`${w.last_score_s} s`} />}
          </div>
          {w && (
            <div className="text-[11px] text-slate-500 space-y-1">
              <div>Heartbeat {ago(w.age_s)} · scans every {w.interval_s} s{w.score_every_s ? `, scores at most every ${w.score_every_s} s` : ''}{w.mode === 'in-process' ? ' · runs inside the server' : ' · separate process: the dashboard may error while it scores'} · <span className="font-mono">{s.folder}</span></div>
              {w.last_file && <div>Last: <span className="font-mono">{w.last_file}</span> · {w.last_rows?.toLocaleString()} rows · {w.last_alerts} alerts after scoring</div>}
              {w.last_error && <div className="text-red-600">Error: {w.last_error}</div>}
            </div>
          )}
          {s.files_waiting.length > 0 && (
            <div className="text-[11px] text-slate-500">Next: {s.files_waiting.slice(0, 4).map((f) => <span key={f} className="font-mono mr-2">{f}</span>)}{s.files_waiting.length > 4 && `+${s.files_waiting.length - 4} more`}</div>
          )}
        </section>
      </div>

      <section className={card}>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Activity className="w-4 h-4 text-blue-600" /> Transactions stored per minute (last 30 min)</h2>
          <div className="text-[11px] text-slate-500">{s.transactions?.toLocaleString()} in the database · newest {String(s.newest_transaction || '—').slice(0, 19)} UTC</div>
        </div>
        {rate.length ? (
          <Chart style={{ height: 180 }} option={{
            grid: { left: 40, right: 12, top: 10, bottom: 24 }, tooltip: { trigger: 'axis' },
            xAxis: { type: 'category', data: rate.map((r) => r.minute) }, yAxis: { type: 'value', minInterval: 1 },
            series: [{ type: 'bar', data: rate.map((r) => r.n), itemStyle: { color: '#2563eb', borderRadius: [3, 3, 0, 0] } }],
          }} />
        ) : <p className="text-xs text-slate-400 py-8 text-center">Nothing ingested in the last 30 minutes.</p>}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className={card}>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4 text-rose-600" /> Newest alerts</h2>
          <div className="divide-y divide-slate-100 text-xs">
            {s.recent_alerts.map((a) => (
              <button key={a.alert_id} onClick={() => onSelectAlert(a.alert_id)} className="w-full text-left py-2 flex items-center gap-3 hover:bg-slate-50">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: SEVERITY_COLOR[a.severity] || '#94a3b8' }} />
                <span className="font-mono text-slate-900">{short(a.entity_id, 18)}</span>
                <span className="text-slate-500 truncate">{a.alert_type}</span>
                <span className="ml-auto font-bold tabular-nums">{a.risk_score}</span>
              </button>
            ))}
            {!s.recent_alerts.length && <p className="py-6 text-center text-slate-400">No alerts. On ordinary live traffic with no seeds that is the expected result.</p>}
          </div>
          {s.open_movement_events > 0 && <p className="mt-3 text-xs font-bold text-red-600">{s.open_movement_events} watched wallet(s) moved funds: see Watchlist.</p>}
        </section>
        <section className={card}>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2 mb-3"><FileText className="w-4 h-4 text-blue-600" /> Recently ingested files</h2>
          <div className="divide-y divide-slate-100 text-xs">
            {s.recent_files.map((f) => (
              <div key={`${f.file}-${f.ingested_at}`} className="py-2 flex items-center gap-3">
                <span className="font-mono text-slate-800 truncate">{f.file}</span>
                <span className="text-slate-500">{Number(f.records).toLocaleString()} rows</span>
                <span className="ml-auto text-slate-400">{String(f.ingested_at).slice(11, 19)}</span>
              </div>
            ))}
            {!s.recent_files.length && <p className="py-6 text-center text-slate-400">No files ingested yet.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
