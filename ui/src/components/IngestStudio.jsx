import React, { useState } from 'react';
import { UploadCloud, Sparkles, FileSpreadsheet, FileCode, CheckCircle, AlertOctagon, ArrowRight, Play } from 'lucide-react';

export default function IngestStudio({ onUploadFile, onGenerateDemo, onUploadSeeds, loading, lastIngestResult }) {
  const [seedFile, setSeedFile] = useState(null);
  const [synthTxCount, setSynthTxCount] = useState(500);
  const [selectedFile, setSelectedFile] = useState(null);
  const [mappingFile, setMappingFile] = useState(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUploadSubmit = (e) => {
    e.preventDefault();
    if (selectedFile) {
      onUploadFile(selectedFile, mappingFile);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Ingestion & Forensic Simulation Studio</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Ingest real-world Bitcoin transaction logs (CSV, JSON, XML) or synthesize realistic forensic datasets.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Col: 1-Click Synthetic Generator */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 text-xs font-bold text-blue-600 uppercase tracking-wider">
            <Sparkles className="w-4 h-4" />
            <span>Synthetic dataset generator (beans synth)</span>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed">
            Generates a labelled synthetic dataset (legitimate users and exchanges plus ransomware, peel-chain, CoinJoin and other laundering patterns) and runs the full pipeline on it. This replaces the current data.
          </p>

          <div className="space-y-2 pt-2">
            <div className="flex justify-between text-xs font-semibold text-slate-700">
              <span>Transaction Count to Generate:</span>
              <span className="font-bold text-blue-600 font-mono">{synthTxCount} transactions</span>
            </div>
            <input
              type="range"
              min="50"
              max="5000"
              step="50"
              value={synthTxCount}
              onChange={(e) => setSynthTxCount(Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer"
            />
          </div>

          <button
            onClick={() => onGenerateDemo(synthTxCount)}
            disabled={loading}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold text-sm shadow-md hover:from-blue-700 hover:to-indigo-700 transition-all flex items-center justify-center space-x-2"
          >
            <Play className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Synthesizing & Scoring...' : 'Run Simulation & Pipeline'}</span>
          </button>
        </div>

        {/* Right Col: Custom File Uploader */}
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 text-xs font-bold text-slate-700 uppercase tracking-wider">
            <UploadCloud className="w-4 h-4 text-blue-600" />
            <span>Upload Multi-Format File (CSV / JSON / XML)</span>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed">
            Streaming parsers with automatic column mapping (<code className="bg-slate-100 px-1 py-0.5 rounded font-mono">--mapping</code>) and quarantine routing for corrupted records.
          </p>

          <form onSubmit={handleUploadSubmit} className="space-y-3 pt-2">
            <input
              type="file"
              accept=".csv,.json,.ndjson,.jsonl,.xml"
              onChange={handleFileChange}
              className="w-full p-2.5 rounded-lg border border-slate-200 bg-slate-50 text-xs file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            <label className="block text-[11px] text-slate-500">
              Optional column mapping (YAML) for files with other column names (see docs/DATA_FORMATS.md):
              <input type="file" accept=".yaml,.yml" onChange={(e) => setMappingFile(e.target.files?.[0] || null)} className="block mt-1 text-xs" />
            </label>

            <button
              type="submit"
              disabled={!selectedFile || loading}
              className="w-full py-3 rounded-xl bg-slate-900 text-white font-bold text-sm shadow-md hover:bg-slate-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Ingesting...' : 'Ingest & Run Forensic Pipeline'}
            </button>
          </form>
        </div>
      </div>

      {/* Seed wallets (roadmap S8) */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <div className="text-xs font-bold text-rose-600 uppercase tracking-wider">Known-illicit seed wallets → risk propagation</div>
        <p className="text-xs text-slate-600">
          Upload a CSV with an <span className="font-mono">address</span> column (optional <span className="font-mono">label</span>,
          <span className="font-mono"> confidence</span>). Engine E4 re-propagates risk from these seeds across the whole graph and the
          alert list is rebuilt. Analyst verdicts are kept.
        </p>
        <form className="flex items-center gap-3" onSubmit={(e) => { e.preventDefault(); if (seedFile) onUploadSeeds(seedFile); }}>
          <input type="file" accept=".csv" onChange={(e) => setSeedFile(e.target.files?.[0] || null)} className="text-xs" />
          <button disabled={!seedFile || loading} className="px-4 py-2 rounded-lg bg-rose-600 text-white text-xs font-semibold disabled:opacity-50">
            {loading ? 'Re-scoring…' : 'Load seeds & re-propagate'}
          </button>
        </form>
      </div>

      {/* Ingestion Results Card */}
      {lastIngestResult && (() => {
        const r = lastIngestResult.pipeline_result || lastIngestResult;
        const stats = r.rescore?.pipeline_stats || r.pipeline_stats || {};
        const cells = [
          ['Records', r.records_ingested ?? r.rescore?.records_rescored],
          ['Quarantined rows', r.rows_quarantined],
          ['Alerts', stats.alerts_generated],
          ['Clusters (CIOH)', stats.clusters_computed],
          ['Seeds used', stats.seeds_propagated ?? r.seeds_loaded],
        ];
        return (
          <div className="p-5 rounded-xl bg-emerald-50/60 border border-emerald-200 space-y-2">
            <div className="flex items-center space-x-2 text-xs font-bold text-emerald-800 uppercase tracking-wider">
              <CheckCircle className="w-4 h-4" />
              <span>Pipeline run complete</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs font-semibold text-emerald-950 pt-2">
              {cells.map(([label, v]) => (
                <div key={label} className="p-2.5 rounded bg-white/80 border border-emerald-200">
                  <span className="text-slate-500 block text-[10px]">{label}</span>
                  <span className="font-bold text-sm">{v ?? '—'}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
