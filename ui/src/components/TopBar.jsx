import React, { useState } from 'react';
import { Search, RefreshCw, Moon, Sun } from 'lucide-react';
import { toggleTheme, useTheme } from '../theme';
import { PAGE_TITLES } from './Sidebar';

const TXID = /^[0-9a-fA-F]{64}$/;
const IP = /^(\d{1,3}\.){3}\d{1,3}$|^[0-9a-fA-F:]+:[0-9a-fA-F:]*$/;

export default function TopBar({ activeTab, stats, loading, onRefresh, onSearchWallet, onSearchGraph }) {
  const [q, setQ] = useState('');
  const page = PAGE_TITLES[activeTab] || { label: '', group: '' };
  const k = stats?.kpis;
  const theme = useTheme();

  const submit = (e) => {
    e.preventDefault();
    const v = q.trim();
    if (!v) return;
    if (TXID.test(v) || IP.test(v)) onSearchGraph(v); // transactions and IPs open in the link graph
    else onSearchWallet(v);                          // anything else is treated as a wallet address
  };

  return (
    <header className="h-16 glass border-b border-slate-200 flex items-center gap-6 px-6 sticky top-0 z-40">
      <div className="min-w-0">
        <div className="text-[11px] text-slate-400 uppercase tracking-wider">{page.group}</div>
        <h1 className="text-base font-bold text-slate-900 leading-tight">{page.label}</h1>
      </div>

      <form onSubmit={submit} className="flex-1 max-w-xl relative">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search wallet address, transaction ID or IP…"
          className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono placeholder:font-sans"
        />
      </form>

      <div className="ml-auto flex items-center gap-4 text-xs text-slate-500">
        {k && (
          <div className="hidden lg:flex items-center gap-4">
            <span><b className="text-slate-800">{k.total_transactions.toLocaleString()}</b> tx</span>
            <span><b className="text-slate-800">{k.total_wallets.toLocaleString()}</b> wallets</span>
            <span><b className="text-rose-600">{k.open_alerts ?? k.total_alerts}</b> open alerts</span>
          </div>
        )}
        <button onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle dark mode" className="p-2 rounded-lg border border-slate-200 hover:bg-slate-100">
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
        <button onClick={onRefresh} disabled={loading} title="Reload data"
          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </header>
  );
}
