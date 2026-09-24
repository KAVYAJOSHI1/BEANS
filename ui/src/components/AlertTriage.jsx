import React, { useState } from 'react';
import { Search, Filter, AlertCircle, CheckCircle, ExternalLink, X, ShieldAlert, Sparkles, Network, ArrowRight } from 'lucide-react';

export default function AlertTriage({ alerts, onSelectAlert, selectedAlert, onCloseDrawer, onUpdateStatus, setActiveTab, onInspectEntity }) {
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAlerts = alerts.filter((a) => {
    if (severityFilter !== 'ALL' && a.severity !== severityFilter) return false;
    if (statusFilter !== 'ALL' && a.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchesEntity = a.entity_id.toLowerCase().includes(q);
      const matchesType = a.alert_type.toLowerCase().includes(q);
      const matchesReason = a.reasons?.some((r) => r.toLowerCase().includes(q));
      if (!matchesEntity && !matchesType && !matchesReason) return false;
    }
    return true;
  });

  const getSeverityBadge = (sev) => {
    switch (sev) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'HIGH':
        return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Search */}
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search wallet, IP, typology, reason..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-slate-200 text-sm bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
          />
        </div>

        {/* Severity Filters */}
        <div className="flex items-center space-x-1.5 overflow-x-auto w-full md:w-auto">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                severityFilter === s
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Alert Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                <th className="py-3 px-4">Rank</th>
                <th className="py-3 px-4">Suspect Entity</th>
                <th className="py-3 px-4">Threat Typology</th>
                <th className="py-3 px-4">Risk Score</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4">Primary Diagnostic Trigger</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {filteredAlerts.map((a, idx) => (
                <tr
                  key={a.alert_id}
                  onClick={() => onSelectAlert(a)}
                  className="hover:bg-blue-50/40 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4 font-mono text-xs text-slate-400 font-semibold">#{idx + 1}</td>
                  <td className="py-3 px-4 font-mono text-xs font-semibold text-slate-900">
                    {a.entity_id.substring(0, 16)}...
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">
                      {a.alert_type.replace('_PATTERN', '')}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`text-xs px-2.5 py-1 rounded-md font-bold border ${getSeverityBadge(a.severity)}`}
                    >
                      {a.risk_score.toFixed(0)} / 100
                    </span>
                  </td>
                  <td className="py-3 px-4 text-xs font-semibold text-slate-600">
                    {(a.calibrated_confidence * 100).toFixed(0)}%
                  </td>
                  <td className="py-3 px-4 text-xs text-slate-600 max-w-xs truncate">
                    {a.reasons?.[0] || 'High risk correlation'}
                  </td>
                  <td className="py-3 px-4">
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                      {a.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectAlert(a);
                      }}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 px-2.5 py-1 rounded-md border border-blue-100 hover:bg-blue-100 transition-all"
                    >
                      Investigate
                    </button>
                  </td>
                </tr>
              ))}

              {filteredAlerts.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-400 text-sm">
                    No alerts match the selected filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Investigation Details Drawer */}
      {selectedAlert && (
        <div className="fixed inset-y-0 right-0 w-full max-w-xl bg-white shadow-2xl border-l border-slate-200 z-50 p-6 overflow-y-auto space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 pb-4">
            <div>
              <div className="flex items-center space-x-2">
                <span className={`text-xs px-2 py-0.5 rounded-md font-bold border ${getSeverityBadge(selectedAlert.severity)}`}>
                  {selectedAlert.severity} SEVERITY
                </span>
                <span className="text-xs font-bold text-slate-500">{selectedAlert.alert_id}</span>
              </div>
              <h2 className="text-lg font-bold text-slate-900 mt-1 font-mono">{selectedAlert.entity_id}</h2>
            </div>
            <button
              onClick={onCloseDrawer}
              className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Quick Stats Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-xs text-slate-500 font-semibold uppercase">Calibrated Risk</span>
              <div className="text-2xl font-bold text-slate-900 mt-0.5">{selectedAlert.risk_score.toFixed(1)} / 100</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
              <span className="text-xs text-slate-500 font-semibold uppercase">Confidence Level</span>
              <div className="text-2xl font-bold text-slate-900 mt-0.5">{(selectedAlert.calibrated_confidence * 100).toFixed(0)}%</div>
            </div>
          </div>

          {/* Plain-English Reasons (XAI) */}
          <div>
            <div className="flex items-center space-x-2 text-sm font-bold text-slate-900 uppercase tracking-wider mb-2">
              <Sparkles className="w-4 h-4 text-blue-600" />
              <span>Diagnostic Reason Attribution</span>
            </div>
            <ul className="space-y-2">
              {selectedAlert.reasons?.map((r, i) => (
                <li key={i} className="text-xs text-slate-700 bg-blue-50/60 p-2.5 rounded-lg border border-blue-100/60 flex items-start space-x-2">
                  <span className="text-blue-600 font-bold mt-0.5">&bull;</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* SHAP Feature Impacts */}
          {selectedAlert.shap_top_features?.length > 0 && (
            <div>
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block mb-2">
                SHAP Feature Attribution Waterfall
              </span>
              <div className="space-y-1.5">
                {selectedAlert.shap_top_features.map((sf, idx) => (
                  <div key={idx} className="flex items-center justify-between p-2 rounded bg-slate-50 border border-slate-200 text-xs">
                    <span className="font-mono text-slate-700">{sf.feature}</span>
                    <span className="font-bold text-rose-600">{sf.impact}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Engine Sub-Scores */}
          <div>
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block mb-2">
              4-Engine Multi-Factor Breakdown
            </span>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">E2 Anomaly:</span>
                <span className="font-bold text-slate-900 ml-1">
                  {selectedAlert.engine_scores?.e2_anomaly_score || 0} pts
                </span>
              </div>
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">E3 Typology:</span>
                <span className="font-bold text-slate-900 ml-1">
                  {selectedAlert.engine_scores?.e3_typology_score || 0} pts
                </span>
              </div>
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">E4 Seed Proximity:</span>
                <span className="font-bold text-slate-900 ml-1">
                  {selectedAlert.engine_scores?.e4_seed_proximity_score || 0} pts
                </span>
              </div>
              <div className="p-2.5 rounded bg-slate-50 border border-slate-200">
                <span className="text-slate-500">Network SIGINT:</span>
                <span className="font-bold text-slate-900 ml-1">
                  {selectedAlert.engine_scores?.network_sigint_score || 0} pts
                </span>
              </div>
            </div>
          </div>

          {/* Status Updater */}
          <div className="border-t border-slate-200 pt-4">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block mb-2">
              Investigator Triage Action
            </span>
            <div className="grid grid-cols-2 gap-2">
              {['INVESTIGATING', 'RESOLVED', 'FALSE_POSITIVE'].map((st) => (
                <button
                  key={st}
                  onClick={() => onUpdateStatus(selectedAlert.alert_id, st)}
                  className={`py-2 px-3 rounded-lg text-xs font-bold border transition-all ${
                    selectedAlert.status === st
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  Mark {st.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Direct Navigation */}
          <div className="pt-2 flex space-x-2">
            <button
              onClick={() => {
                onInspectEntity(selectedAlert.entity_id);
                setActiveTab('entity');
              }}
              className="w-full py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-xs shadow-md hover:bg-blue-700 transition-all flex items-center justify-center space-x-2"
            >
              <span>Inspect in Entity 360</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
