import React, { useEffect, useState } from 'react';
import { Stamp, Check, X, Download, RefreshCw } from 'lucide-react';
import { hasRole, useSession } from '../session';

const API = '/api';
const STATUS_CLS = {
  PENDING_APPROVAL: 'bg-orange-50 text-orange-700 border-orange-200',
  APPROVED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  REJECTED: 'bg-red-50 text-red-700 border-red-200',
};
const KIND = { section94: 'Section 94 BNSS notice', freeze: 'Freeze / hold request' };

export default function Approvals({ onChanged }) {
  const { user, authEnabled } = useSession();
  const [filter, setFilter] = useState('PENDING_APPROVAL');
  const [rows, setRows] = useState([]);
  const [sel, setSel] = useState(null);
  const [doc, setDoc] = useState(null);
  const [comment, setComment] = useState('');
  const [msg, setMsg] = useState(null);

  const load = async () => {
    const r = await fetch(`${API}/legal-requests?status=${filter}`);
    setRows(r.ok ? await r.json() : []);
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = async (row) => {
    setSel(row);
    setMsg(null);
    setComment('');
    const r = await fetch(`${API}/legal-requests/${row.id}`);
    setDoc(r.ok ? await r.json() : null);
  };

  const decide = async (decision) => {
    const r = await fetch(`${API}/legal-requests/${sel.id}/decision`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, comment }),
    });
    const body = await r.json().catch(() => ({}));
    if (r.ok) { await load(); await open({ ...sel, ...body }); onChanged?.(); }   // open() clears the message, so set it afterwards
    setMsg(r.ok ? { ok: true, text: `Request #${sel.id} ${body.status.toLowerCase()}` } : { ok: false, text: body.detail });
  };

  const canDecide = sel && doc?.status === 'PENDING_APPROVAL' && hasRole(user, 'SUPERVISOR')
    && (!authEnabled || doc.created_by !== user?.username);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3 self-start">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Stamp className="w-4 h-4 text-blue-600" /> Legal drafts</h2>
          <button onClick={load} className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
        <p className="text-xs text-slate-500">Section 94 and freeze drafts need a supervisor's approval, by someone other than the drafter, before a final copy can be issued.</p>
        <div className="flex gap-1 text-xs">
          {['PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'ALL'].map((s) => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-2.5 py-1 rounded-lg font-bold ${filter === s ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>
              {s === 'PENDING_APPROVAL' ? 'Pending' : s[0] + s.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
        <div className="divide-y divide-slate-100 border border-slate-200 rounded-lg max-h-[620px] overflow-y-auto">
          {rows.length === 0 && <div className="p-4 text-xs text-center text-slate-400">Nothing here.</div>}
          {rows.map((r) => (
            <button key={r.id} onClick={() => open(r)}
              className={`w-full text-left p-3 text-xs hover:bg-slate-50 ${sel?.id === r.id ? 'bg-blue-50' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-slate-900">#{r.id} · {KIND[r.kind] || r.kind}</span>
                <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${STATUS_CLS[r.status]}`}>{r.status.replace('_', ' ')}</span>
              </div>
              <div className="text-slate-500 mt-1">{r.vasp} · wallet <span className="font-mono">{r.entity_id?.slice(0, 14)}…</span></div>
              <div className="text-slate-400 mt-0.5">drafted by {r.created_by} · {String(r.created_at).slice(0, 16)}{r.decided_by ? ` · ${r.status.toLowerCase()} by ${r.decided_by}` : ''}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3 min-h-[500px]">
        {!sel && <div className="h-full flex items-center justify-center text-sm text-slate-400">Select a draft to review it.</div>}
        {sel && doc && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-bold text-slate-900 text-sm">Request #{doc.id} · {KIND[doc.kind]}</span>
              <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${STATUS_CLS[doc.status]}`}>{doc.status.replace('_', ' ')}</span>
              <span className="text-slate-500">evidence SHA-256 <span className="font-mono">{doc.evidence_sha256.slice(0, 16)}…</span></span>
              <span className="flex-1" />
              <a href={`${API}/legal-requests/${doc.id}?fmt=pdf`} className="px-2.5 py-1.5 rounded-lg bg-slate-900 text-white font-bold flex items-center gap-1">
                <Download className="w-3.5 h-3.5" /> {doc.status === 'APPROVED' ? 'Approved PDF' : 'Draft PDF'}
              </a>
            </div>
            {msg && <div className={`text-xs px-3 py-2 rounded-lg border ${msg.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`}>{msg.text}</div>}
            {doc.status === 'PENDING_APPROVAL' && (
              canDecide ? (
                <div className="flex flex-wrap items-center gap-2 text-xs p-3 rounded-lg bg-slate-50 border border-slate-200">
                  <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (required to reject)"
                    className="flex-1 min-w-[220px] px-2.5 py-1.5 rounded-md border border-slate-200 bg-white" />
                  <button onClick={() => decide('APPROVE')} className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white font-bold flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Approve for issue</button>
                  <button onClick={() => decide('REJECT')} className="px-3 py-1.5 rounded-lg bg-red-600 text-white font-bold flex items-center gap-1"><X className="w-3.5 h-3.5" /> Reject</button>
                </div>
              ) : (
                <div className="text-xs text-slate-500 p-3 rounded-lg bg-slate-50 border border-slate-200">
                  {hasRole(user, 'SUPERVISOR') ? 'You drafted this request: another supervisor has to approve it.' : 'Waiting for a supervisor to approve.'}
                </div>
              )
            )}
            <iframe title="legal draft" srcDoc={doc.html} sandbox="" className="doc-preview w-full h-[640px] rounded-lg border border-slate-200 bg-white" />
          </>
        )}
      </section>
    </div>
  );
}
