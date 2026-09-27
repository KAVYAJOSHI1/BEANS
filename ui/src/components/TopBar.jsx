import React from 'react';
import { Search, RefreshCw, Moon, Sun, LogOut, UserRound } from 'lucide-react';
import { logout, useSession } from '../session';
import { toggleTheme, useTheme } from '../theme';
import { PAGE_TITLES } from './Sidebar';

const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

export default function TopBar({ activeTab, stats, loading, onRefresh, onOpenSearch }) {
  const page = PAGE_TITLES[activeTab] || { label: '', group: '' };
  const k = stats?.kpis;
  const theme = useTheme();
  const { user, authEnabled } = useSession();

  return (
    <header className="h-16 glass border-b border-slate-200 flex items-center gap-6 px-6 sticky top-0 z-40">
      <div className="min-w-0">
        <div className="text-[11px] text-slate-400 uppercase tracking-wider">{page.group}</div>
        <h1 className="text-base font-bold text-slate-900 leading-tight">{page.label}</h1>
      </div>

      <button type="button" onClick={() => onOpenSearch('')}
        className="flex-1 max-w-xl flex items-center gap-2 pl-3 pr-2 py-2 text-sm rounded-lg border border-slate-200 bg-slate-50 hover:bg-white text-slate-400 text-left">
        <Search className="w-4 h-4" />
        <span className="flex-1">Search wallet, transaction, IP, alert, cluster or case…</span>
        <kbd className="text-[10px] border border-slate-200 rounded px-1.5 py-0.5 bg-white">{MAC ? '⌘' : 'Ctrl'} K</kbd>
      </button>

      <div className="ml-auto flex items-center gap-4 text-xs text-slate-500">
        {k && (
          <div className="hidden lg:flex items-center gap-4">
            <span><b className="text-slate-800">{k.total_transactions.toLocaleString()}</b> tx</span>
            <span><b className="text-slate-800">{k.total_wallets.toLocaleString()}</b> wallets</span>
            <span><b className="text-rose-600">{k.open_alerts ?? k.total_alerts}</b> open alerts</span>
          </div>
        )}
        {authEnabled && user && (
          <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
            <UserRound className="w-4 h-4 text-slate-400" />
            <div className="leading-tight">
              <div className="font-semibold text-slate-800">{user.display_name || user.username}</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-400">{user.role}</div>
            </div>
            <button onClick={logout} title="Sign out" className="p-2 rounded-lg border border-slate-200 hover:bg-slate-100"><LogOut className="w-4 h-4" /></button>
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
