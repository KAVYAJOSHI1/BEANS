import React, { useState } from 'react';
import { Lock, Loader2 } from 'lucide-react';
import coffeeBean from '../coffee-bean.svg';
import { login } from '../session';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="themed min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-2xl border border-slate-200 shadow-xl p-7 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center"><img src={coffeeBean} alt="" className="w-8 h-8" /></div>
          <div>
            <div className="font-bold text-slate-900 text-lg leading-tight">BEANS</div>
            <div className="text-xs text-slate-500">Bitcoin forensics · sign in</div>
          </div>
        </div>
        <label className="block text-xs">
          <span className="font-semibold text-slate-700">Username</span>
          <input autoFocus value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
            className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" />
        </label>
        <label className="block text-xs">
          <span className="font-semibold text-slate-700">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
            className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm" />
        </label>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700">{error}</div>}
        <button disabled={busy || !username || !password}
          className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />} Sign in
        </button>
        <p className="text-[11px] text-slate-400">Accounts are created by an administrator (<span className="font-mono">beans user add</span>). All actions are recorded in the audit trail under your name.</p>
      </form>
    </div>
  );
}
