import React, { useState } from 'react';
import { Gavel, Snowflake, FileText, Eye, ShieldCheck, HelpCircle, Download, X, Stamp, Loader2, ScrollText } from 'lucide-react';

const API_BASE = '/api';

export const ACTION_META = {
  IMMEDIATE_FREEZE_DRAFT: { short: 'Freeze draft', icon: Snowflake, cls: 'bg-red-50 text-red-700 border-red-200', dot: 'bg-red-500' },
  DRAFT_SECTION_94_BNSS: { short: '§94 BNSS', icon: Gavel, cls: 'bg-orange-50 text-orange-700 border-orange-200', dot: 'bg-orange-500' },
  FIU_REFERRAL_PACK: { short: 'FIU referral', icon: FileText, cls: 'bg-violet-50 text-violet-700 border-violet-100', dot: 'bg-violet-500' },
  PASSIVE_TAINT_MONITOR: { short: 'Taint watch', icon: Eye, cls: 'bg-sky-50 text-sky-700 border-sky-100', dot: 'bg-sky-500' },
  REVIEW_LIKELY_BENIGN: { short: 'Likely benign', icon: ShieldCheck, cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500' },
  ANALYST_REVIEW: { short: 'Review', icon: HelpCircle, cls: 'bg-slate-100 text-slate-700 border-slate-200', dot: 'bg-slate-400' },
};

export function ActionBadge({ action, pulse = false }) {
  const m = ACTION_META[action] || ACTION_META.ANALYST_REVIEW;
  const Icon = m.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md border whitespace-nowrap ${m.cls}`}>
      {pulse && action === 'IMMEDIATE_FREEZE_DRAFT'
        ? <span className="w-1.5 h-1.5 rounded-full bg-red-500 pulse-dot" />
        : <Icon className="w-3 h-3" />}
      {m.short}
    </span>
  );
}

const FACT_LABELS = {
  vasp: 'Exchange', country: 'Country', deposit_address: 'Deposit address', txid: 'Deposit tx', hops: 'Hops',
  amount_btc: 'Amount (BTC)', deposit_ts: 'Deposited (UTC)', minutes_after_receipt: 'Minutes after receipt',
  minutes_before_latest_data: 'Minutes before latest data',
  check: 'Rule check', jurisdiction_note: 'Jurisdiction', vasps_reached: 'Exchanges reached', deposits_found: 'Deposits found',
  btc_moved: 'BTC moved', risky_broadcast_share: 'Risky broadcast share', first_relay_asn_type: 'First relay ASN',
  layering: 'Layering', offshore_vasps: 'Offshore exchanges', measured_over: 'Measured over', unspent_btc: 'Unspent (BTC)',
  dormant_h: 'Dormant (h)', taint: 'Taint', hops_to_nearest_seed: 'Hops to seed', known_entity: 'Known entity',
  entity_type: 'Entity type', why: 'Why', funded_by: 'Funded by', risk: 'Risk',
};
const HIDDEN = new Set(['path', 'in_jurisdiction']);

const fmtVal = (v) => {
  if (v == null || v === '') return '—';
  if (Array.isArray(v)) return v.join(', ') || '—';
  if (typeof v === 'object') return Object.entries(v).map(([k, x]) => `${k} ${x}`).join(' · ');
  return String(v);
};

export function ActionCard({ alert, onUpdateStatus, onOpenDoc, isWatched = false, onWatch }) {
  const ra = alert.recommended_action || {};
  if (!ra.action) return null;
  const facts = Object.entries(ra.facts || {}).filter(([k, v]) => !HIDDEN.has(k) && v != null);
  const hasIndian = (ra.vasp_exposure || []).some((h) => h.in_jurisdiction);
  const hasExposure = (ra.vasp_exposure || []).length > 0;
  const btn = 'px-3 py-2 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all';

  return (
    <div className="rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Recommended action</div>
          <div className="text-sm font-bold text-slate-900 mt-0.5">{ra.title}</div>
        </div>
        <ActionBadge action={ra.action} pulse />
      </div>
      <div className="p-4 space-y-3 text-xs">
        <div>
          <span className="font-semibold text-slate-500">Rule: </span>
          <span className="text-slate-800">{ra.rule}</span>
        </div>
        {facts.length > 0 && (
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 bg-slate-50 border border-slate-200 rounded-lg p-2.5">
            {facts.map(([k, v]) => (
              <React.Fragment key={k}>
                <span className="text-slate-500">{FACT_LABELS[k] || k}</span>
                <span className={`text-slate-900 break-all ${/address|txid/.test(k) ? 'font-mono text-[11px]' : 'font-semibold'}`}>{fmtVal(v)}</span>
              </React.Fragment>
            ))}
          </div>
        )}
        <div><span className="font-semibold text-slate-500">Legal basis: </span><span className="text-slate-700">{ra.legal_basis}</span></div>
        {ra.shap_support?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-slate-500">Model support:</span>
            {ra.shap_support.map((s) => (
              <span key={s.feature} className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                {s.feature} +{Number(s.impact).toFixed(2)}
              </span>
            ))}
          </div>
        )}
        {ra.also_matched?.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-slate-500">Also matched:</span>
            {ra.also_matched.map((a) => <ActionBadge key={a} action={a} />)}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          {ra.action === 'IMMEDIATE_FREEZE_DRAFT' && (
            <button onClick={() => onOpenDoc({ kind: 'freeze', alert })} className={`${btn} bg-red-600 text-white hover:bg-red-700`}>
              <Snowflake className="w-3.5 h-3.5" /> Draft freeze request
            </button>
          )}
          {hasIndian && (
            <button onClick={() => onOpenDoc({ kind: 'section94', alert })}
              className={`${btn} ${ra.action === 'DRAFT_SECTION_94_BNSS' ? 'bg-orange-600 text-white hover:bg-orange-700' : 'bg-slate-100 text-slate-800 hover:bg-slate-200'}`}>
              <Gavel className="w-3.5 h-3.5" /> Draft Section 94 BNSS notice
            </button>
          )}
          {!hasIndian && hasExposure && ra.action !== 'IMMEDIATE_FREEZE_DRAFT' && (
            <button onClick={() => onOpenDoc({ kind: 'freeze', alert })} className={`${btn} bg-slate-100 text-slate-800 hover:bg-slate-200`}>
              <Snowflake className="w-3.5 h-3.5" /> Draft hold request (offshore)
            </button>
          )}
          <button onClick={() => onOpenDoc({ kind: 'referral', alert })}
            className={`${btn} ${ra.action === 'FIU_REFERRAL_PACK' ? 'bg-violet-600 text-white hover:bg-violet-700' : 'bg-slate-100 text-slate-800 hover:bg-slate-200'}`}>
            <FileText className="w-3.5 h-3.5" /> Export referral pack
          </button>
          {isWatched ? (
            <span className={`${btn} bg-sky-50 text-sky-700 border border-sky-100`}><Eye className="w-3.5 h-3.5" /> On watchlist</span>
          ) : (
            <button onClick={() => { onWatch?.(alert.entity_id, alert.alert_id); if (ra.action === 'PASSIVE_TAINT_MONITOR') onUpdateStatus(alert.alert_id, 'INVESTIGATING'); }}
              className={`${btn} ${ra.action === 'PASSIVE_TAINT_MONITOR' ? 'bg-sky-600 text-white hover:bg-sky-700' : 'bg-slate-100 text-slate-800 hover:bg-slate-200'}`}>
              <Eye className="w-3.5 h-3.5" /> {ra.action === 'PASSIVE_TAINT_MONITOR' ? 'Start taint watch' : 'Watch wallet'}
            </button>
          )}
          {ra.action === 'REVIEW_LIKELY_BENIGN' && (
            <button onClick={() => onUpdateStatus(alert.alert_id, 'FALSE_POSITIVE')} className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`}>
              <ShieldCheck className="w-3.5 h-3.5" /> Confirm false positive
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- document modal
const IO_FIELDS = [
  ['fir_no', 'FIR / case no.'], ['fir_date', 'FIR date'], ['offences', 'Offences (sections)'], ['io_name', 'IO name'],
  ['io_rank', 'IO rank'], ['police_station', 'Police station'], ['district_state', 'District, State'],
  ['reply_days', 'Reply within (days)'], ['vasp_address_line', "Exchange's nodal-officer address"],
];
const IO_KEY = 'beans-io-details';
const loadIO = () => { try { return JSON.parse(localStorage.getItem(IO_KEY)) || {}; } catch { return {}; } };
const saveIO = (v) => { try { localStorage.setItem(IO_KEY, JSON.stringify(v)); } catch { /* storage blocked */ } };

const TITLES = { section94: 'Section 94 BNSS notice (draft)', freeze: 'Freeze / hold request (draft)', referral: 'FIU-IND referral pack' };

const save = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

export function DocModal({ doc, onClose }) {
  const { kind, alert } = doc;
  const legal = kind !== 'referral';
  const [io, setIO] = useState(loadIO);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // generating a legal draft files an approval request; downloads then read that stored request (never re-file it)
  const call = (fmt) => {
    if (!legal) return fetch(`${API_BASE}/alerts/${alert.alert_id}/referral?fmt=${fmt}`);
    if (fmt !== 'json' && result?.request) return fetch(`${API_BASE}/legal-requests/${result.request.id}?fmt=${fmt}`);
    return fetch(`${API_BASE}/alerts/${alert.alert_id}/legal/${kind}?fmt=${fmt}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(io) });
  };

  const generate = async () => {
    setBusy(true);
    setError(null);
    saveIO(io);
    try {
      const r = await call('json');
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || `HTTP ${r.status}`);
      setResult(body);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  React.useEffect(() => { if (!legal) generate(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const download = async (fmt) => {
    const stem = legal ? `BEANS_${kind}_${alert.alert_id}` : `BEANS_referral_${alert.alert_id}`;
    if (fmt === 'json') {
      save(new Blob([JSON.stringify({ ...result, html: undefined }, null, 2)], { type: 'application/json' }), `${stem}.json`);
      return;
    }
    setBusy(true);
    try {
      const r = await call(fmt);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
      save(await r.blob(), `${stem}.${fmt}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const ts = result?.timestamp;
  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ScrollText className="w-4 h-4 text-blue-600" />
            <span className="font-bold text-slate-900">{TITLES[kind]}</span>
            <span className="text-xs text-slate-500 font-mono">{alert.alert_id} · {alert.entity_id.slice(0, 18)}…</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"><X className="w-4 h-4" /></button>
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[300px_1fr]">
          <div className="p-4 border-r border-slate-200 overflow-y-auto space-y-3 text-xs">
            {legal ? (
              <>
                <p className="text-slate-500">BEANS fills in the blockchain facts. Fields left empty stay as visible blanks for the
                  Investigating Officer. IO details are remembered in this browser only.</p>
                {IO_FIELDS.map(([k, label]) => (
                  <label key={k} className="block">
                    <span className="font-semibold text-slate-700">{label}</span>
                    <input value={io[k] || ''} onChange={(e) => setIO({ ...io, [k]: e.target.value })}
                      className="mt-0.5 w-full px-2 py-1.5 rounded-md border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </label>
                ))}
                <button onClick={generate} disabled={busy}
                  className="w-full py-2 rounded-lg bg-blue-600 text-white font-bold hover:bg-blue-700 disabled:opacity-60 flex items-center justify-center gap-1.5">
                  {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Gavel className="w-3.5 h-3.5" />} {result ? 'Redraft (files a new request)' : 'Generate draft'}
                </button>
              </>
            ) : (
              <p className="text-slate-500">A sealed dossier for the IO / FIU-IND liaison officer: subject, assessment, money trail,
                exchange exposure and network evidence. Reporting entities file STRs; this is an intelligence referral.</p>
            )}

            {error && <div className="p-2 rounded-lg bg-red-50 border border-red-200 text-red-700">{error}</div>}

            {result && (
              <div className="space-y-2 pt-1">
                <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-slate-800"><Stamp className="w-3.5 h-3.5 text-emerald-600" /> Evidence seal</div>
                  <div className="text-slate-500">SHA-256</div>
                  <div className="font-mono text-[10px] break-all text-slate-800">{result.evidence_sha256}</div>
                  {ts?.status === 'stamped' ? (
                    <div className="text-slate-600">RFC 3161 · {ts.gen_time} · serial {ts.serial}</div>
                  ) : (
                    <div className="text-amber-700">Not timestamped: {ts?.reason}</div>
                  )}
                </div>
                {result.request && (
                  <div className="p-2.5 rounded-lg bg-orange-50 border border-orange-200 text-orange-800">
                    Filed as request <b>#{result.request.id}</b>: pending supervisor approval (Legal Approvals page).
                    Downloads are marked as drafts until a different supervisor approves.
                  </div>
                )}
                {result.missing_fields?.length > 0 && (
                  <div className="text-amber-700">Blank for the IO: {result.missing_fields.join(', ')}</div>
                )}
                <div className="grid grid-cols-3 gap-1.5">
                  {['pdf', 'html', 'json'].map((f) => (
                    <button key={f} onClick={() => download(f)} disabled={busy}
                      className="py-1.5 rounded-md bg-slate-900 text-white font-bold flex items-center justify-center gap-1 hover:bg-slate-800 disabled:opacity-60">
                      <Download className="w-3 h-3" /> {f.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="bg-slate-100 p-3 min-h-[420px] overflow-hidden">
            {result ? (
              <iframe title="document preview" srcDoc={result.html} sandbox=""
                className="doc-preview w-full h-full min-h-[420px] rounded-lg border border-slate-200 bg-white" />
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">
                {busy ? 'Generating…' : 'Fill in what you know and generate the draft.'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
