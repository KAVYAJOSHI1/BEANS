import React from 'react';
import ReactECharts from 'echarts-for-react';
import { Cpu, AlertCircle } from 'lucide-react';

const KNOWN = new Set(['status', 'source', 'message', 'model_overview', 'engine_metrics', 'confusion_matrix', 'feature_importances']);

function Value({ v }) {
  if (v === null || v === undefined) return <span className="text-slate-400">—</span>;
  if (typeof v === 'number') return <span className="font-mono">{Number.isInteger(v) ? v : v.toFixed(4)}</span>;
  if (typeof v !== 'object') return <span>{String(v)}</span>;
  if (Array.isArray(v) && v.every((x) => typeof x !== 'object')) return <span className="font-mono">{v.join(', ')}</span>;
  return <pre className="text-[11px] bg-slate-50 p-2 rounded overflow-x-auto">{JSON.stringify(v, null, 2)}</pre>;
}

export default function ModelCard({ modelCard }) {
  if (!modelCard) return <div className="text-sm text-slate-500">Loading model card…</div>;

  if (modelCard.status !== 'evaluated') {
    return (
      <div className="bg-white rounded-xl border border-amber-200 p-8 text-center space-y-3">
        <AlertCircle className="w-8 h-8 text-amber-500 mx-auto" />
        <h2 className="text-lg font-bold text-slate-900">Model card not generated yet</h2>
        <p className="text-sm text-slate-600 max-w-xl mx-auto">
          {modelCard.message || 'Run the evaluation step to measure the engines on held-out labelled data.'} This page only
          shows measured metrics. Nothing on it is hard-coded.
        </p>
      </div>
    );
  }

  const cm = modelCard.confusion_matrix;
  const extras = Object.entries(modelCard).filter(([k]) => !KNOWN.has(k));

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-start gap-3">
        <Cpu className="w-6 h-6 text-blue-600 mt-0.5" />
        <div>
          <h2 className="text-lg font-bold text-slate-900">{modelCard.model_overview?.name || 'Model card'}</h2>
          <p className="text-xs text-slate-500">
            Measured on held-out synthetic data with ground-truth labels · source: {modelCard.source}
          </p>
          {modelCard.model_overview && (
            <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
              {Object.entries(modelCard.model_overview).filter(([k]) => k !== 'name').map(([k, v]) => (
                <div key={k}><span className="text-slate-500">{k.replace(/_/g, ' ')}: </span><Value v={v} /></div>
              ))}
            </div>
          )}
        </div>
      </div>

      {modelCard.engine_metrics?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase">
              <tr><th className="text-left p-3">Engine</th><th className="text-left p-3">Metric</th><th className="text-right p-3">Score</th><th className="text-right p-3">Target</th></tr>
            </thead>
            <tbody>
              {modelCard.engine_metrics.map((m, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="p-3 font-semibold text-slate-800">{m.engine}</td>
                  <td className="p-3 text-slate-600">{m.metric}</td>
                  <td className="p-3 text-right font-mono font-bold">{typeof m.score === 'number' ? m.score.toFixed(3) : m.score}</td>
                  <td className="p-3 text-right text-slate-500">{m.target ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-5">
        {cm?.labels?.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Confusion matrix (rows = true, columns = predicted)</h3>
            <ReactECharts style={{ height: 340 }} option={{
              tooltip: { position: 'top' },
              grid: { left: 110, bottom: 90, top: 10, right: 10 },
              xAxis: { type: 'category', data: cm.labels, axisLabel: { rotate: 40, fontSize: 10 } },
              yAxis: { type: 'category', data: cm.labels, inverse: true, axisLabel: { fontSize: 10 } },
              visualMap: { min: 0, max: Math.max(...cm.matrix.flat(), 1), show: false, inRange: { color: ['#f8fafc', '#1d4ed8'] } },
              series: [{ type: 'heatmap', label: { show: true, fontSize: 10 },
                data: cm.matrix.flatMap((row, i) => row.map((v, j) => [j, i, v])) }],
            }} />
          </div>
        )}
        {modelCard.feature_importances?.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="text-sm font-bold text-slate-800 mb-2">Global feature importance</h3>
            <ReactECharts style={{ height: 340 }} option={{
              grid: { left: 180, right: 20, top: 10, bottom: 20 },
              xAxis: { type: 'value' },
              yAxis: { type: 'category', inverse: true, axisLabel: { fontSize: 10 },
                data: modelCard.feature_importances.map((f) => f.feature) },
              series: [{ type: 'bar', itemStyle: { color: '#2563eb' }, data: modelCard.feature_importances.map((f) => f.importance) }],
            }} />
          </div>
        )}
      </div>

      {extras.map(([k, v]) => (
        <div key={k} className="bg-white rounded-xl border border-slate-200 p-4">
          <h3 className="text-sm font-bold text-slate-800 mb-2">{k.replace(/_/g, ' ')}</h3>
          {v && typeof v === 'object' && !Array.isArray(v) ? (
            <div className="grid md:grid-cols-2 gap-x-6 gap-y-1 text-xs">
              {Object.entries(v).map(([kk, vv]) => (
                <div key={kk} className="flex justify-between gap-3 border-b border-slate-50 py-1">
                  <span className="text-slate-500">{kk.replace(/_/g, ' ')}</span><Value v={vv} />
                </div>
              ))}
            </div>
          ) : <Value v={v} />}
        </div>
      ))}
    </div>
  );
}
