import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Wallet, Hash, Globe, AlertTriangle, Boxes, Briefcase, CornerDownLeft } from 'lucide-react';

// Ctrl+K / ⌘K: one box for wallets, transactions, IPs, alerts, clusters and cases (GET /api/search).
const GROUPS = [
  ['wallets', 'Wallets', Wallet], ['alerts', 'Alerts', AlertTriangle], ['transactions', 'Transactions', Hash],
  ['ips', 'IP addresses', Globe], ['clusters', 'Entity clusters', Boxes], ['cases', 'Cases', Briefcase],
];
const short = (s, n = 22) => (s && String(s).length > n + 6 ? `${String(s).slice(0, n)}…${String(s).slice(-4)}` : s);

function detail(group, r) {
  switch (group) {
    case 'wallets': return `risk ${r.risk}${r.alert_id ? ' · alerted' : ''} · ${r.cluster_id || ''}`;
    case 'alerts': return `${r.alert_type} · risk ${r.risk_score} · ${short(r.entity_id, 12)}`;
    case 'transactions': return `${String(r.timestamp).slice(0, 19)} · ${Number(r.total_output).toFixed(4)} BTC`;
    case 'ips': return `${r.country || '??'} · ${r.asn_type || 'unknown'} · ${r.observations} relays`;
    case 'clusters': return `${r.wallets} wallets · max risk ${r.max_risk}`;
    case 'cases': return `${r.status} · ${r.priority}`;
    default: return '';
  }
}

export default function CommandPalette({ open, onClose, initial = '', onOpenWallet, onOpenGraph, onOpenAlert, onOpenCase }) {
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState({});
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  useEffect(() => { if (open) { setQ(initial); setSel(0); setTimeout(() => input.current?.focus(), 0); } }, [open, initial]);

  useEffect(() => {
    const v = q.trim();
    if (!open || v.length < 2) { setRes({}); return undefined; }
    setBusy(true);
    const ctl = new AbortController();
    const t = setTimeout(() => {
      fetch(`/api/search?q=${encodeURIComponent(v)}`, { signal: ctl.signal })
        .then((r) => (r.ok ? r.json() : {})).then((j) => { setRes(j); setSel(0); })
        .catch(() => {}).finally(() => setBusy(false));
    }, 180);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [q, open]);

  const flat = useMemo(() => GROUPS.flatMap(([g]) => (res[g] || []).map((r) => ({ g, r }))), [res]);

  const choose = ({ g, r }) => {
    onClose();
    if (g === 'wallets') onOpenWallet(r.id);
    else if (g === 'alerts') onOpenAlert(r.id);
    else if (g === 'transactions' || g === 'ips') onOpenGraph(r.id);
    else if (g === 'clusters') onOpenGraph(r.top_wallet);
    else if (g === 'cases') onOpenCase(r.id);
  };

  const onKey = (e) => {
    if (e.key === 'Escape') onClose();
    else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, flat.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (flat[sel]) choose(flat[sel]);
      else if (q.trim()) { onClose(); onOpenWallet(q.trim()); }   // nothing matched: try it as a wallet
    }
  };

  if (!open) return null;
  let i = -1;
  return (
    <div className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-start justify-center pt-[12vh] px-4" onMouseDown={onClose}>
      <div className="w-full max-w-2xl bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-4 border-b border-slate-200">
          <Search className="w-4 h-4 text-slate-400" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Wallet, transaction ID, IP, alert, cluster or case…"
            className="flex-1 py-3.5 text-sm bg-transparent focus:outline-none font-mono placeholder:font-sans text-slate-900" />
          <kbd className="text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">Esc</kbd>
        </div>
        <div className="max-h-[60vh] overflow-y-auto py-1">
          {q.trim().length < 2 && <div className="px-4 py-6 text-center text-xs text-slate-400">Type at least 2 characters. Prefixes work: <span className="font-mono">bc1q8…</span>, <span className="font-mono">185.220</span>, <span className="font-mono">C-4F</span>.</div>}
          {q.trim().length >= 2 && !busy && flat.length === 0 && (
            <div className="px-4 py-6 text-center text-xs text-slate-400">Nothing found. Enter opens it as a wallet anyway.</div>
          )}
          {GROUPS.filter(([g]) => res[g]?.length).map(([g, label, Icon]) => (
            <div key={g} className="py-1">
              <div className="px-4 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
              {res[g].map((r) => {
                i += 1;
                const idx = i;
                return (
                  <button key={`${g}-${r.id}`} onMouseEnter={() => setSel(idx)} onClick={() => choose({ g, r })}
                    className={`w-full text-left px-4 py-2 flex items-center gap-3 text-xs ${sel === idx ? 'bg-blue-50' : ''}`}>
                    <Icon className="w-4 h-4 text-slate-400 shrink-0" />
                    <span className="font-mono text-slate-900 truncate">{g === 'cases' ? `#${r.id} ${r.case_name}` : short(r.id, 30)}</span>
                    <span className="ml-auto text-slate-500 truncate">{detail(g, r)}</span>
                    {sel === idx && <CornerDownLeft className="w-3.5 h-3.5 text-blue-500 shrink-0" />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
