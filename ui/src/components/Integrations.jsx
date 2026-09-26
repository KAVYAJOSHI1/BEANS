import React, { useEffect, useState } from 'react';
import { Webhook, Send, Trash2, Plus, Building2, UploadCloud, Stamp, Download, ListChecks, RefreshCw, CheckCircle2, XCircle, Users as UsersIcon } from 'lucide-react';
import { ActionBadge } from './ActionPanel';
import { hasRole, useSession } from '../session';

const API = '/api';
const FORMATS = [
  ['json', 'Generic JSON (Wazuh, custom)'], ['splunk_hec', 'Splunk HEC'], ['elastic', 'Elasticsearch _bulk'], ['stix', 'STIX 2.1 (MISP, OpenCTI)'],
];
const card = 'bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4';
const input = 'w-full px-2.5 py-1.5 rounded-md border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs';
const getJson = (p) => fetch(`${API}${p}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);

function Section({ icon: Icon, title, subtitle, right, children }) {
  return (
    <section className={card}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Icon className="w-4 h-4 text-blue-600" /> {title}</h2>
          {subtitle && <p className="text-xs text-slate-500 mt-1 max-w-3xl">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

function Webhooks() {
  const [hooks, setHooks] = useState([]);
  const [log, setLog] = useState([]);
  const [form, setForm] = useState({ name: '', url: '', fmt: 'json', min_severity: 'CRITICAL', token: '' });
  const [msg, setMsg] = useState(null);

  const refresh = async () => {
    setHooks((await getJson('/webhooks')) || []);
    setLog((await getJson('/webhooks/log?limit=25')) || []);
  };
  useEffect(() => { refresh(); }, []);

  const call = async (path, opts, done) => {
    const r = await fetch(`${API}${path}`, opts);
    const body = await r.json().catch(() => ({}));
    setMsg(r.ok ? done(body) : { ok: false, text: body.detail || `HTTP ${r.status}` });
    refresh();
    return r.ok;
  };
  const add = async (e) => {
    e.preventDefault();
    const ok = await call('/webhooks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) },
      (b) => ({ ok: true, text: `Added “${b.name}”` }));
    if (ok) setForm({ ...form, name: '', url: '', token: '' });
  };

  return (
    <Section icon={Webhook} title="SIEM & threat-intel webhooks"
      subtitle="After every scoring run, new alerts at or above each hook's severity are pushed once (never twice), with 3 attempts. Point these at SIEMs on your own network; BEANS itself stays offline."
      right={<button onClick={() => call('/webhooks/dispatch', { method: 'POST' }, (b) => ({ ok: true, text: `Dispatched: ${b.results.map((r) => `#${r.webhook_id} ${r.sent} sent`).join(', ') || 'no hooks'}` }))}
        className="px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-bold flex items-center gap-1.5"><Send className="w-3.5 h-3.5" /> Send pending now</button>}>
      {msg && <div className={`text-xs px-3 py-2 rounded-lg border ${msg.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>{msg.text}</div>}

      <div className="overflow-x-auto border border-slate-200 rounded-lg">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-slate-500 uppercase text-[10px] tracking-wider">
            <tr><th className="text-left p-2">Name</th><th className="text-left p-2">URL</th><th className="text-left p-2">Format</th>
              <th className="text-left p-2">Min severity</th><th className="text-left p-2">Delivered</th><th className="text-left p-2">Enabled</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {hooks.length === 0 && <tr><td colSpan={7} className="p-4 text-center text-slate-400">No webhooks configured.</td></tr>}
            {hooks.map((h) => (
              <tr key={h.id}>
                <td className="p-2 font-semibold text-slate-900">{h.name}{h.token_set && <span className="ml-1 text-[10px] text-slate-400">(token)</span>}</td>
                <td className="p-2 font-mono text-slate-600 max-w-[260px] truncate">{h.url}</td>
                <td className="p-2">{h.fmt}</td>
                <td className="p-2">
                  <select value={h.min_severity} className="border border-slate-200 bg-white rounded px-1 py-0.5"
                    onChange={(e) => call(`/webhooks/${h.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ min_severity: e.target.value }) }, () => ({ ok: true, text: 'Updated' }))}>
                    {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => <option key={s}>{s}</option>)}
                  </select>
                </td>
                <td className="p-2"><span className="text-emerald-700 font-bold">{h.sent}</span>{h.failed > 0 && <span className="text-red-600 font-bold"> · {h.failed} failed</span>}</td>
                <td className="p-2">
                  <input type="checkbox" checked={h.enabled}
                    onChange={(e) => call(`/webhooks/${h.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: e.target.checked }) }, () => ({ ok: true, text: 'Updated' }))} />
                </td>
                <td className="p-2 text-right whitespace-nowrap">
                  <button onClick={() => call(`/webhooks/${h.id}/test`, { method: 'POST' }, (b) => ({ ok: b.ok, text: b.ok ? `Test delivered (HTTP ${b.http_status})` : `Test failed: ${b.error}` }))}
                    className="px-2 py-1 rounded bg-slate-100 font-semibold mr-1">Test</button>
                  <button onClick={() => call(`/webhooks/${h.id}`, { method: 'DELETE' }, () => ({ ok: true, text: 'Deleted' }))}
                    className="p-1 rounded hover:bg-red-50 text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form onSubmit={add} className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end text-xs">
        <label className="md:col-span-1"><span className="font-semibold text-slate-600">Name</span>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="SOC Splunk" /></label>
        <label className="md:col-span-2"><span className="font-semibold text-slate-600">URL</span>
          <input className={`${input} font-mono`} required value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://splunk.local:8088/services/collector" /></label>
        <label><span className="font-semibold text-slate-600">Format</span>
          <select className={input} value={form.fmt} onChange={(e) => setForm({ ...form, fmt: e.target.value })}>
            {FORMATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></label>
        <label><span className="font-semibold text-slate-600">Token (optional)</span>
          <input className={input} type="password" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} /></label>
        <div className="flex gap-2">
          <select className={input} value={form.min_severity} onChange={(e) => setForm({ ...form, min_severity: e.target.value })}>
            {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => <option key={s}>{s}</option>)}
          </select>
          <button className="px-3 py-1.5 rounded-md bg-blue-600 text-white font-bold flex items-center gap-1 shrink-0"><Plus className="w-3.5 h-3.5" /> Add</button>
        </div>
      </form>

      {log.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer font-semibold text-slate-600">Delivery log (last {log.length})</summary>
          <div className="mt-2 max-h-48 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
            {log.map((l, i) => (
              <div key={i} className="px-2 py-1 flex items-center gap-2">
                {l.status === 'FAILED' ? <XCircle className="w-3.5 h-3.5 text-red-500" /> : <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
                <span className="text-slate-400">{String(l.sent_at).slice(0, 19)}</span>
                <span className="font-semibold">{l.name || `#${l.webhook_id}`}</span>
                <span className="font-mono">{l.alert_id}</span>
                <span className="text-slate-500">{l.status}{l.http_status ? ` · HTTP ${l.http_status}` : ''}</span>
                {l.error && <span className="text-red-600 truncate">{l.error}</span>}
              </div>
            ))}
          </div>
        </details>
      )}
    </Section>
  );
}

function Attribution({ onChanged }) {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const refresh = async () => setRows((await getJson('/known-entities')) || []);
  useEffect(() => { refresh(); }, []);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API}/known-entities/upload`, { method: 'POST', body: fd });
    const body = await r.json().catch(() => ({}));
    setMsg(r.ok ? { ok: true, text: `${body.added} addresses added; alerts re-scored` } : { ok: false, text: body.detail });
    setBusy(false);
    refresh();
    if (r.ok) onChanged?.();
  };

  return (
    <Section icon={Building2} title="Attribution list (exchanges & mining pools)"
      subtitle="Addresses known to belong to exchanges (VASPs) and mining pools. The action rules use it to find exchange deposits (freeze / Section 94 drafts) and obvious false positives. It is never a model feature."
      right={<label className={`px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer ${busy ? 'opacity-60' : ''}`}>
        <UploadCloud className="w-3.5 h-3.5" /> {busy ? 'Loading…' : 'Upload CSV'}
        <input type="file" accept=".csv" className="hidden" disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
      </label>}>
      {msg && <div className={`text-xs px-3 py-2 rounded-lg border ${msg.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>{msg.text}</div>}
      <p className="text-[11px] text-slate-500 font-mono">CSV columns: address, entity_name, entity_type (VASP | MINING_POOL), country, in_jurisdiction (true/false), source</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {rows.length === 0 && <div className="text-xs text-slate-400">No attribution loaded. Synthetic datasets ship one; for real data upload your exchange address list.</div>}
        {rows.map((r) => (
          <div key={`${r.entity_name}-${r.entity_type}`} className="p-3 rounded-lg border border-slate-200 bg-slate-50 text-xs">
            <div className="font-bold text-slate-900">{r.entity_name}</div>
            <div className="text-slate-500 mt-0.5">{r.entity_type} · {r.country} · {r.in_jurisdiction ? 'operates in India (§94 BNSS)' : 'outside India'}</div>
            <div className="mt-1 font-semibold text-slate-700">{r.addresses.toLocaleString()} addresses</div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Timestamping() {
  const [tsa, setTsa] = useState(null);
  const [v, setV] = useState({ sha256: '', token_der_b64: '' });
  const [result, setResult] = useState(null);
  useEffect(() => { getJson('/tsa').then(setTsa); }, []);
  const verify = async (e) => {
    e.preventDefault();
    const r = await fetch(`${API}/tsa/verify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(v) });
    setResult(r.ok ? (await r.json()).valid : false);
  };
  return (
    <Section icon={Stamp} title="Evidence timestamping (RFC 3161)"
      subtitle="Case packs, legal drafts and referral packs are sealed with SHA-256 and a timestamp token from a local, offline Time-Stamping Authority. Record the CA fingerprint in the case diary; anyone can re-verify a token with OpenSSL.">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
          <div className="font-bold text-slate-800">Status</div>
          <div>OpenSSL: {tsa?.openssl ? <b className="text-emerald-700">available</b> : <b className="text-red-600">missing</b>}</div>
          <div>TSA: {tsa?.initialised ? <b className="text-emerald-700">initialised</b> : 'created on first timestamp'}</div>
          {tsa?.initialised && (
            <div className="flex gap-2 pt-1">
              <a href={`${API}/tsa/tsa_ca.pem`} download="tsa_ca.pem" className="px-2 py-1 rounded bg-slate-900 text-white font-bold flex items-center gap-1"><Download className="w-3 h-3" /> CA cert</a>
              <a href={`${API}/tsa/tsa.pem`} download="tsa.pem" className="px-2 py-1 rounded bg-slate-100 font-bold flex items-center gap-1"><Download className="w-3 h-3" /> TSA cert</a>
            </div>
          )}
        </div>
        <div className="md:col-span-2 p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
          <div className="font-bold text-slate-800">CA SHA-256 fingerprint</div>
          <div className="font-mono text-[11px] break-all text-slate-700">{tsa?.ca_sha256_fingerprint || '—'}</div>
          <div className="font-bold text-slate-800 pt-2">Verify with OpenSSL</div>
          <code className="block font-mono text-[11px] text-slate-700 break-all">openssl ts -verify -digest &lt;sha256&gt; -in token.tsr -CAfile tsa_ca.pem -untrusted tsa.pem</code>
        </div>
      </div>
      <form onSubmit={verify} className="grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-2 items-end text-xs">
        <label><span className="font-semibold text-slate-600">Evidence SHA-256</span>
          <input className={`${input} font-mono`} value={v.sha256} onChange={(e) => setV({ ...v, sha256: e.target.value.trim() })} /></label>
        <label><span className="font-semibold text-slate-600">Token (token_der_b64 from the JSON export)</span>
          <input className={`${input} font-mono`} value={v.token_der_b64} onChange={(e) => setV({ ...v, token_der_b64: e.target.value.trim() })} /></label>
        <button className="px-3 py-1.5 rounded-md bg-blue-600 text-white font-bold">Verify</button>
      </form>
      {result !== null && (
        <div className={`text-xs font-bold ${result ? 'text-emerald-700' : 'text-red-600'}`}>
          {result ? 'Valid: this token was issued by this TSA for exactly this hash.' : 'Not valid for this hash / TSA.'}
        </div>
      )}
    </Section>
  );
}

function Rulebook() {
  const [data, setData] = useState(null);
  useEffect(() => { getJson('/actions/summary').then(setData); }, []);
  return (
    <Section icon={ListChecks} title="Action directive rulebook"
      subtitle="Every alert gets one recommended action from these fixed rules, checked in this order. Rules decide; the model's SHAP reasons are shown as support. Legal steps are drafts for the Investigating Officer."
      right={<button onClick={() => getJson('/actions/summary').then(setData)} className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100"><RefreshCw className="w-3.5 h-3.5" /></button>}>
      <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg">
        {(data?.actions || []).map((a) => (
          <div key={a.action} className="p-3 grid grid-cols-1 md:grid-cols-[150px_1fr_70px] gap-3 items-start text-xs">
            <ActionBadge action={a.action} />
            <div>
              <div className="font-bold text-slate-900">{a.title}</div>
              <div className="text-slate-600 mt-0.5">{a.rule}</div>
              <div className="text-slate-400 mt-0.5">{a.legal_basis}</div>
            </div>
            <div className="text-right font-bold text-slate-900 text-base">{a.count}</div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Users() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ username: '', display_name: '', role: 'ANALYST', password: '' });
  const [msg, setMsg] = useState(null);
  const refresh = async () => setRows((await getJson('/users')) || []);
  useEffect(() => { refresh(); }, []);
  const call = async (path, opts, ok) => {
    const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
    const body = await r.json().catch(() => ({}));
    setMsg(r.ok ? { ok: true, text: ok } : { ok: false, text: body.detail });
    refresh();
    return r.ok;
  };
  const add = async (e) => {
    e.preventDefault();
    if (await call('/users', { method: 'POST', body: JSON.stringify(form) }, `Created ${form.username}`)) {
      setForm({ username: '', display_name: '', role: 'ANALYST', password: '' });
    }
  };
  return (
    <Section icon={UsersIcon} title="Users & roles"
      subtitle="VIEWER reads only · ANALYST triages, builds cases and drafts legal requests · SUPERVISOR approves drafts (not their own) and configures webhooks and attribution · ADMIN manages users. Every action is audited under the user's name.">
      {msg && <div className={`text-xs px-3 py-2 rounded-lg border ${msg.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>{msg.text}</div>}
      <div className="border border-slate-200 rounded-lg divide-y divide-slate-100 text-xs">
        {rows.map((u) => (
          <div key={u.username} className="p-2 flex items-center gap-3">
            <span className="font-bold text-slate-900 w-32 truncate">{u.username}</span>
            <span className="text-slate-500 flex-1 truncate">{u.display_name}</span>
            <select value={u.role} className="border border-slate-200 bg-white rounded px-1 py-0.5"
              onChange={(e) => call(`/users/${u.username}`, { method: 'PATCH', body: JSON.stringify({ role: e.target.value }) }, 'Role updated')}>
              {['VIEWER', 'ANALYST', 'SUPERVISOR', 'ADMIN'].map((r) => <option key={r}>{r}</option>)}
            </select>
            <label className="flex items-center gap-1 text-slate-600">
              <input type="checkbox" checked={u.active}
                onChange={(e) => call(`/users/${u.username}`, { method: 'PATCH', body: JSON.stringify({ active: e.target.checked }) }, 'Updated')} /> active
            </label>
          </div>
        ))}
      </div>
      <form onSubmit={add} className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end text-xs">
        <label><span className="font-semibold text-slate-600">Username</span><input className={input} required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
        <label><span className="font-semibold text-slate-600">Full name</span><input className={input} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
        <label><span className="font-semibold text-slate-600">Role</span>
          <select className={input} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {['VIEWER', 'ANALYST', 'SUPERVISOR', 'ADMIN'].map((r) => <option key={r}>{r}</option>)}
          </select></label>
        <label><span className="font-semibold text-slate-600">Password (≥ 10 chars)</span><input className={input} type="password" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        <button className="px-3 py-1.5 rounded-md bg-blue-600 text-white font-bold flex items-center justify-center gap-1"><Plus className="w-3.5 h-3.5" /> Add user</button>
      </form>
    </Section>
  );
}

export default function Integrations({ onDataChanged }) {
  const { user, authEnabled } = useSession();
  return (
    <div className="space-y-6">
      {authEnabled && hasRole(user, 'ADMIN') && <Users />}
      <Rulebook />
      <Webhooks />
      <Attribution onChanged={onDataChanged} />
      <Timestamping />
    </div>
  );
}
