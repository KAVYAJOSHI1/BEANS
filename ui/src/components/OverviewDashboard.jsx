import React from 'react';
import { AlertOctagon, TrendingUp, ShieldAlert, Cpu, ArrowUpRight, Network, Radio } from 'lucide-react';
import ReactECharts from 'echarts-for-react';

export default function OverviewDashboard({ stats, alerts, onSelectAlert, setActiveTab }) {
  const kpis = stats?.kpis || {
    total_transactions: 0,
    total_volume_btc: 0,
    total_wallets: 0,
    total_alerts: 0,
    critical_alerts: 0,
    high_alerts: 0,
    active_seeds: 0,
  };

  const typologyData = stats?.typology_distribution || [
    { name: 'Ransomware', value: 35 },
    { name: 'Peel Chain', value: 45 },
    { name: 'CoinJoin', value: 20 },
  ];

  const donutOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: '0%', left: 'center' },
    color: ['#ef4444', '#f97316', '#3b82f6', '#10b981', '#8b5cf6'],
    series: [
      {
        name: 'Threat Typologies',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: typologyData,
      },
    ],
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-slate-900 rounded-2xl p-6 text-white shadow-lg shadow-blue-500/10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-1 rounded-md bg-white/20 text-xs font-semibold backdrop-blur-md">
              OFFLINE FORENSIC SENTINEL
            </span>
            <span className="text-xs text-blue-200">SIH PS 26146 · NTRO</span>
          </div>
          <h1 className="text-2xl font-bold mt-2">Forensic Intelligence & Traffic Monitoring</h1>
          <p className="text-blue-100 text-sm mt-1 max-w-2xl">
            Offline correlation of Bitcoin P2P network telemetry (SIGINT) with blockchain ledger flows and calibrated AI/ML threat detection engines.
          </p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab('ingest')}
            className="px-4 py-2.5 rounded-xl bg-white text-blue-700 font-semibold text-sm shadow-md hover:bg-blue-50 transition-all flex items-center space-x-2"
          >
            <span>Ingest & Simulate</span>
            <ArrowUpRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Analyzed Ledger Volume</span>
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
              <TrendingUp className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-900">{kpis.total_volume_btc.toLocaleString()}</span>
            <span className="text-xs font-semibold text-slate-500 ml-1">BTC</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">{kpis.total_transactions.toLocaleString()} total transactions evaluated</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Critical Risk Flags</span>
            <div className="p-2 rounded-lg bg-rose-50 text-rose-600">
              <AlertOctagon className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-rose-600">{kpis.critical_alerts}</span>
            <span className="text-xs font-semibold text-slate-500 ml-1">/ {kpis.total_alerts} Total Alerts</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">{kpis.high_alerts} High-Severity escalations</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Entity Clusters</span>
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Network className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-slate-900">{kpis.total_wallets.toLocaleString()}</span>
            <span className="text-xs font-semibold text-slate-500 ml-1">Wallets</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">CIOH Disjoint-Set Clusters indexed</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Seed Taint Propagation</span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <Radio className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold text-emerald-600">{kpis.active_seeds}</span>
            <span className="text-xs font-semibold text-slate-500 ml-1">Active Illicit Seeds</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">PPR + Decayed Taint propagated</p>
        </div>
      </div>

      {/* Main Grid: Threat Typology + Priority Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 1 Col: Donut Chart */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Threat Typology Breakdown</h2>
          <p className="text-xs text-slate-500 mt-0.5">Machine-classified illicit transaction patterns (E3)</p>
          <div className="mt-4 h-64">
            <ReactECharts option={donutOption} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>

        {/* Right 2 Cols: High Priority Alerts */}
        <div className="lg:col-span-2 bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">High-Priority Alert Stream</h2>
                <p className="text-xs text-slate-500">Ranked by calibrated composite risk score</p>
              </div>
              <button
                onClick={() => setActiveTab('alerts')}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors"
              >
                View All Alerts &rarr;
              </button>
            </div>

            <div className="divide-y divide-slate-100">
              {alerts.slice(0, 5).map((a) => (
                <div
                  key={a.alert_id}
                  onClick={() => onSelectAlert(a)}
                  className="py-3 px-2 rounded-lg hover:bg-slate-50 cursor-pointer transition-all flex items-center justify-between"
                >
                  <div className="flex items-center space-x-3">
                    <div
                      className={`w-2.5 h-2.5 rounded-full ${
                        a.severity === 'CRITICAL' ? 'bg-red-500 animate-pulse' : 'bg-orange-500'
                      }`}
                    />
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-xs font-semibold text-slate-900">
                          {a.entity_id.substring(0, 16)}...
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                          {a.alert_type.replace('_PATTERN', '')}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                        {a.reasons?.[0] || 'Correlated high-risk anomaly detected'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <div className="text-right">
                      <div className="text-sm font-bold text-slate-900">{a.risk_score.toFixed(0)}</div>
                      <div className="text-[10px] text-slate-500">{(a.calibrated_confidence * 100).toFixed(0)}% Conf</div>
                    </div>
                    <span
                      className={`text-xs px-2.5 py-1 rounded-md font-bold ${
                        a.severity === 'CRITICAL'
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : 'bg-orange-50 text-orange-700 border border-orange-200'
                      }`}
                    >
                      {a.severity}
                    </span>
                  </div>
                </div>
              ))}

              {alerts.length === 0 && (
                <div className="py-12 text-center text-slate-400 text-sm">
                  No alerts detected yet. Run ingestion in Ingest Studio to process data.
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Engines: E1 clustering · E2 anomaly · E3 peel/mix · E4 seed risk propagation</span>
            <span>Runs fully offline</span>
          </div>
        </div>
      </div>
    </div>
  );
}
