import React from 'react';
import ReactECharts from 'echarts-for-react';
import { ArrowRight, Database, Wallet, Server, Boxes, AlertTriangle, Crosshair, UploadCloud } from 'lucide-react';

const SEV = [
  ['CRITICAL', 'critical_alerts', '#dc2626'],
  ['HIGH', 'high_alerts', '#ea580c'],
  ['MEDIUM', 'medium_alerts', '#ca8a04'],
  ['LOW', 'low_alerts', '#16a34a'],
];
const SEV_BADGE = {
  CRITICAL: 'bg-red-50 text-red-700 border-red-200', HIGH: 'bg-orange-50 text-orange-700 border-orange-200',
  MEDIUM: 'bg-yellow-50 text-yellow-800 border-yellow-200', LOW: 'bg-green-50 text-green-700 border-green-200',
};
const RISKY = new Set(['TOR_EXIT', 'BULLETPROOF', 'VPN']);

function Kpi({ icon: Icon, label, value, sub, tone = 'text-slate-900' }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between text-xs text-slate-500 font-medium">
        {label}<Icon className="w-4 h-4 text-slate-400" />
      </div>
      <div className={`text-2xl font-bold mt-1.5 ${tone}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function Card({ title, sub, children, action }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
          {sub && <p className="text-[11px] text-slate-500">{sub}</p>}
        </div>
        {action}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

const Empty = ({ text }) => <div className="h-full min-h-[160px] flex items-center justify-center text-xs text-slate-400">{text}</div>;

export default function OverviewDashboard({ stats, alerts, onSelectAlert, setActiveTab }) {
  if (!stats) return <div className="text-sm text-slate-500">Loading…</div>;
  const k = stats.kpis;

  if (!k.total_transactions) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-10 text-center space-y-3">
        <UploadCloud className="w-10 h-10 text-blue-500 mx-auto" />
        <h2 className="text-lg font-bold text-slate-900">No data loaded yet</h2>
        <p className="text-sm text-slate-600">Upload a CSV / JSON / XML file or generate a labelled synthetic dataset to start.</p>
        <button onClick={() => setActiveTab('ingest')} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold">
          Go to Ingest
        </button>
      </div>
    );
  }

  const top = [...(alerts || [])].sort((a, b) => b.risk_score - a.risk_score).slice(0, 6);
  const typology = stats.typology_distribution || [];
  const activity = stats.activity || [];
  const asn = stats.asn_types || [];
  const countries = stats.top_countries || [];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <Kpi icon={Database} label="Transactions" value={k.total_transactions.toLocaleString()} sub={`${k.total_observations?.toLocaleString() ?? '—'} network observations`} />
        <Kpi icon={Boxes} label="Volume" value={`${k.total_volume_btc.toLocaleString()} ₿`} sub="total output value" />
        <Kpi icon={Wallet} label="Wallets" value={k.total_wallets.toLocaleString()} sub={`${k.total_clusters?.toLocaleString() ?? '—'} clusters (CIOH)`} />
        <Kpi icon={Server} label="Relaying IPs" value={k.total_ips?.toLocaleString() ?? '—'} sub="first-seen broadcasters" />
        <Kpi icon={AlertTriangle} label="Alerts" value={k.total_alerts} tone="text-rose-600" sub={`${k.open_alerts ?? 0} open · ${k.critical_alerts} critical`} />
        <Kpi icon={Crosshair} label="Seed wallets" value={k.active_seeds} tone={k.active_seeds ? 'text-slate-900' : 'text-amber-600'}
          sub={k.active_seeds ? 'risk propagated from these' : 'none loaded: add seeds'} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2">
          <Card title="Highest-risk alerts" sub="Ranked by fused risk score"
            action={<button onClick={() => setActiveTab('alerts')} className="text-xs font-semibold text-blue-600 flex items-center gap-1">All alerts <ArrowRight className="w-3.5 h-3.5" /></button>}>
            {top.length === 0 ? <Empty text="No alerts" /> : (
              <div className="divide-y divide-slate-100">
                {top.map((a) => (
                  <button key={a.alert_id} onClick={() => onSelectAlert(a)} className="w-full text-left py-2.5 flex items-center gap-3 hover:bg-slate-50 px-1 rounded">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${SEV_BADGE[a.severity] || ''}`}>{a.severity}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-semibold text-slate-800 truncate">{a.entity_id}</span>
                        <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 rounded">{a.alert_type.replace('_PATTERN', '')}</span>
                      </div>
                      <div className="text-[11px] text-slate-500 truncate">{a.reasons?.[0] || '—'}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-sm font-bold text-slate-900">{a.risk_score.toFixed(0)}</div>
                      <div className="text-[10px] text-slate-500">{(a.calibrated_confidence * 100).toFixed(0)}% conf</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </div>

        <Card title="Alerts by severity & type">
          {k.total_alerts === 0 ? <Empty text="No alerts" /> : (
            <ReactECharts style={{ height: 290 }} option={{
              tooltip: { trigger: 'item' },
              legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 10 } },
              series: [
                { type: 'pie', radius: ['0%', '32%'], center: ['50%', '42%'], label: { show: false },
                  data: SEV.map(([n, key, color]) => ({ name: n, value: k[key], itemStyle: { color } })).filter((d) => d.value) },
                { type: 'pie', radius: ['45%', '62%'], center: ['50%', '42%'], label: { show: false },
                  itemStyle: { borderColor: '#fff', borderWidth: 2 },
                  color: ['#6366f1', '#0ea5e9', '#a855f7', '#14b8a6', '#f43f5e', '#84cc16'], data: typology },
              ],
            }} />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Card title="Transaction activity" sub="Transactions per hour (bars) and BTC volume (line)">
          {activity.length === 0 ? <Empty text="No activity" /> : (
            <ReactECharts style={{ height: 230 }} option={{
              tooltip: { trigger: 'axis' }, grid: { left: 40, right: 45, top: 15, bottom: 30 },
              xAxis: { type: 'category', data: activity.map((a) => a.hour.slice(5)), axisLabel: { fontSize: 9 } },
              yAxis: [{ type: 'value', axisLabel: { fontSize: 9 } }, { type: 'value', axisLabel: { fontSize: 9 }, splitLine: { show: false } }],
              series: [
                { type: 'bar', data: activity.map((a) => a.transactions), itemStyle: { color: '#93c5fd' } },
                { type: 'line', yAxisIndex: 1, smooth: true, symbol: 'none', data: activity.map((a) => a.volume_btc), itemStyle: { color: '#1d4ed8' } },
              ],
            }} />
          )}
        </Card>
        <Card title="Relay infrastructure" sub="Network observations by ASN type">
          {asn.length === 0 ? <Empty text="No network data" /> : (
            <ReactECharts style={{ height: 230 }} option={{
              tooltip: {}, grid: { left: 90, right: 20, top: 10, bottom: 20 },
              xAxis: { type: 'value', axisLabel: { fontSize: 9 } },
              yAxis: { type: 'category', inverse: true, data: asn.map((a) => a.asn_type), axisLabel: { fontSize: 10 } },
              series: [{ type: 'bar', data: asn.map((a) => ({ value: a.count, itemStyle: { color: RISKY.has(a.asn_type) ? '#dc2626' : '#64748b' } })) }],
            }} />
          )}
        </Card>
        <Card title="Top relay countries" sub="Network observations by source country">
          {countries.length === 0 ? <Empty text="No network data" /> : (
            <ReactECharts style={{ height: 230 }} option={{
              tooltip: {}, grid: { left: 40, right: 20, top: 10, bottom: 20 },
              xAxis: { type: 'value', axisLabel: { fontSize: 9 } },
              yAxis: { type: 'category', inverse: true, data: countries.map((c) => c.country), axisLabel: { fontSize: 10 } },
              series: [{ type: 'bar', data: countries.map((c) => c.count), itemStyle: { color: '#0ea5e9' } }],
            }} />
          )}
        </Card>
      </div>
    </div>
  );
}
