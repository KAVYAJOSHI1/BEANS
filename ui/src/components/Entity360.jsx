import React, { useState } from 'react';
import { Search, ShieldAlert, Activity, ArrowDownLeft, ArrowUpRight, Network, UserCheck } from 'lucide-react';
import ReactECharts from './Chart';

export default function Entity360({ entityData, onSearch, loading }) {
  const [inputAddress, setInputAddress] = useState('');

  const profile = entityData?.profile || {};
  const transactions = entityData?.transactions || [];
  const alert = entityData?.alert;

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (inputAddress.trim()) {
      onSearch(inputAddress.trim());
    }
  };

  // Radar straight from the alert's engine scores; no values are filled in when there is no alert.
  const engineEntries = Object.entries(alert?.engine_scores || {}).filter(
    ([k, v]) => typeof v === 'number' && !k.startsWith('total'));
  const radarMax = Math.max(...engineEntries.map(([, v]) => v), 1);
  const radarOption = engineEntries.length >= 3 ? {
    radar: { indicator: engineEntries.map(([k]) => ({ name: k.replace(/_score$/, '').replace(/_/g, ' '), max: radarMax })), radius: '62%' },
    series: [{ type: 'radar', data: [{ value: engineEntries.map(([, v]) => v), name: 'Engine scores',
      areaStyle: { color: 'rgba(37, 99, 235, 0.2)' }, lineStyle: { color: '#2563eb', width: 2 }, itemStyle: { color: '#2563eb' } }] }],
  } : null;
  const ips = profile.associated_ips || [];

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row items-center gap-3">
          <div className="relative w-full">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
            <input
              type="text"
              placeholder="Enter Bitcoin wallet address or transaction ID for 360° deep-dive inspection..."
              value={inputAddress}
              onChange={(e) => setInputAddress(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-sm shadow-md hover:bg-blue-700 transition-all flex items-center justify-center space-x-2"
          >
            <span>Inspect</span>
          </button>
        </form>
      </div>

      {entityData?.error && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 text-sm text-slate-600">{entityData.error}</div>
      )}
      {!entityData && <div className="text-sm text-slate-500">Search a wallet address, or open one from an alert or the graph.</div>}

      {/* Profile Overview */}
      {profile.address && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 2 Cols: Profile Cards */}
          <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-6">
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div>
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Target Wallet 360 Dossier</span>
                <h2 className="text-base font-bold font-mono text-slate-900 mt-1 break-all">{profile.address}</h2>
              </div>
              <span className="px-3 py-1 rounded-md bg-red-50 text-red-700 font-bold border border-red-200 text-xs">
                {profile.is_seed ? 'SEED (known illicit)' : profile.threat_classification || 'UNSCORED'}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-500 font-semibold">Composite Risk</span>
                <div className="text-xl font-bold text-rose-600 mt-0.5">{(profile.risk_score || 0).toFixed(0)} / 100</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-500 font-semibold">Sent (observed)</span>
                <div className="text-xl font-bold text-slate-900 mt-0.5">{(profile.total_sent || 0).toFixed(4)} BTC</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-500 font-semibold">Total Received</span>
                <div className="text-xl font-bold text-slate-900 mt-0.5">{(profile.total_received || 0).toFixed(4)} BTC</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-500 font-semibold">Associated Cluster</span>
                <div className="text-sm font-bold text-indigo-600 font-mono mt-1 truncate" title={profile.cluster_id}>{profile.cluster_id || 'SOLO'}</div>
                <div className="text-[11px] text-slate-500">{profile.cluster_size || 1} address(es)</div>
              </div>
            </div>

            {/* Transaction Ledger */}
            <div>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                Correlated On-Chain Transactions ({transactions.length})
              </h3>
              <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
                {transactions.map((tx, idx) => (
                  <div key={idx} className="p-3 flex items-center justify-between text-xs hover:bg-slate-50">
                    <div className="flex items-center space-x-2.5">
                      <div
                        className={`p-1.5 rounded-md ${
                          tx.role === 'SENDER' ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'
                        }`}
                      >
                        {tx.role === 'SENDER' ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownLeft className="w-4 h-4" />}
                      </div>
                      <div>
                        <span className="font-mono font-bold text-slate-800">{tx.txid.substring(0, 16)}...</span>
                        <div className="text-[11px] text-slate-400">{tx.timestamp}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-slate-900">{tx.amount.toFixed(4)} BTC</div>
                      <div className="text-[11px] text-slate-500">{tx.geo_country} · {tx.asn}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 1 Col: engine scores + network attribution */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
            <div>
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Engine score breakdown</h3>
              {radarOption ? (
                <div className="h-60"><ReactECharts option={radarOption} style={{ height: '100%', width: '100%' }} /></div>
              ) : (
                <p className="text-xs text-slate-400 py-6">No alert was raised for this wallet, so there are no engine scores to show.</p>
              )}
            </div>
            <div className="p-3 rounded-lg bg-blue-50 border border-blue-100 text-xs text-blue-900 space-y-1.5">
              <span className="font-bold block">First-relaying IPs for this wallet's spends</span>
              {ips.length === 0 && <p className="text-blue-800/70">No network observations linked to this wallet's spends.</p>}
              {ips.map((ip) => (
                <div key={ip.ip} className="flex justify-between gap-2">
                  <span className="font-mono font-bold">{ip.ip}</span>
                  <span>{ip.country} · {ip.asn} · <b>{ip.asn_type}</b> · {ip.tx_count} tx</span>
                </div>
              ))}
            </div>
            {entityData?.cluster_members?.length > 0 && (
              <div className="text-xs">
                <span className="font-bold text-slate-500 uppercase tracking-wider block mb-1">Same cluster (CIOH)</span>
                <div className="max-h-40 overflow-y-auto space-y-0.5">
                  {entityData.cluster_members.map((m) => (
                    <button key={m} onClick={() => onSearch(m)} className="block font-mono text-blue-700 hover:underline truncate w-full text-left">{m}</button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
