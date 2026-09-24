import React, { useState } from 'react';
import { Briefcase, Download, Plus, FileText, CheckCircle2, Shield, Hash, ArrowDownToLine } from 'lucide-react';

export default function CaseManager({ cases, onCreateCase, onExportDossier, exportResult }) {
  const [caseName, setCaseName] = useState('');
  const [incidentType, setIncidentType] = useState('RANSOMWARE');
  const [notes, setNotes] = useState('');
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  const handleCreate = (e) => {
    e.preventDefault();
    if (caseName.trim()) {
      onCreateCase({
        case_name: caseName,
        incident_type: incidentType,
        notes: notes,
        suspect_entities: []
      });
      setCaseName('');
      setNotes('');
    }
  };

  const downloadReportFile = (content, filename) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Law Enforcement Case Files & Evidence Dossiers</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Group suspect clusters, track chain of custody, and export court-admissible forensic packages with dataset SHA-256 hashes.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Col: Create Case Form */}
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
            <Plus className="w-4 h-4 text-blue-600" />
            <span>Open New Forensic Case</span>
          </div>

          <form onSubmit={handleCreate} className="space-y-3 text-xs">
            <div>
              <label className="font-semibold text-slate-700 block mb-1">Case Operation Title:</label>
              <input
                type="text"
                placeholder="e.g., Operation LockBit Eclipse"
                value={caseName}
                onChange={(e) => setCaseName(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 text-xs"
                required
              />
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Incident Typology:</label>
              <select
                value={incidentType}
                onChange={(e) => setIncidentType(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white text-xs"
              >
                <option value="RANSOMWARE">Ransomware Extortion</option>
                <option value="THEFT_HACK">Exchange Hack / Theft</option>
                <option value="MIXING_TUMBLER">Illicit Mixing Syndicate</option>
                <option value="DARKNET_MARKET">Darknet Marketplace</option>
              </select>
            </div>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">Investigator Briefing & Notes:</label>
              <textarea
                rows={3}
                placeholder="Synopsis of suspect wallet movements and network indicators..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white text-xs"
              />
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-xs shadow-md hover:bg-blue-700 transition-all"
            >
              Create Case File
            </button>
          </form>
        </div>

        {/* Right 2 Cols: Active Cases Table */}
        <div className="lg:col-span-2 bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block">
            Active Forensic Cases ({cases.length})
          </span>

          <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
            {cases.map((c) => (
              <div key={c.id} className="p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 hover:bg-slate-50 transition-colors">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-bold text-slate-400 font-mono">#{c.id}</span>
                    <span className="font-bold text-slate-900 text-sm">{c.case_name}</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-100">
                      {c.incident_type}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 line-clamp-1">{c.notes || 'Forensic investigation case active.'}</p>
                </div>

                <div className="flex items-center space-x-2 w-full sm:w-auto">
                  <button
                    onClick={() => onExportDossier(c.id)}
                    className="w-full sm:w-auto px-3.5 py-1.5 rounded-lg bg-slate-900 text-white font-semibold text-xs shadow-sm hover:bg-slate-800 transition-all flex items-center justify-center space-x-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Export Dossier</span>
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Dossier Preview if generated */}
          {exportResult && (
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3 mt-4">
              <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <span className="text-xs font-bold text-slate-900 uppercase">LE Dossier Generated: {exportResult.case_name}</span>
                </div>
                <button
                  onClick={() => downloadReportFile(exportResult.markdown, `BEANS_LE_DOSSIER_${exportResult.case_id}.md`)}
                  className="px-3 py-1 rounded bg-blue-600 text-white text-xs font-bold shadow-sm hover:bg-blue-700 flex items-center space-x-1"
                >
                  <ArrowDownToLine className="w-3.5 h-3.5" />
                  <span>Download (.md)</span>
                </button>
              </div>
              <pre className="text-[11px] font-mono bg-white p-3 rounded-lg border border-slate-200 max-h-60 overflow-y-auto text-slate-700 whitespace-pre-wrap">
                {exportResult.markdown}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
