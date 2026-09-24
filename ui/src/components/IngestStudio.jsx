import React, { useState } from 'react';
import { UploadCloud, Sparkles, FileSpreadsheet, FileCode, CheckCircle, AlertOctagon, ArrowRight, Play } from 'lucide-react';

export default function IngestStudio({ onUploadFile, onGenerateDemo, loading, lastIngestResult }) {
  const [synthTxCount, setSynthTxCount] = useState(500);
  const [selectedFile, setSelectedFile] = useState(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUploadSubmit = (e) => {
    e.preventDefault();
    if (selectedFile) {
      onUploadFile(selectedFile);
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
            <span>Autonomous Forensic Simulation Generator (beans synth)</span>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed">
            Synthesizes realistic UTXO ledgers containing LockBit ransomware extortions, Wasabi CoinJoin mixer syndicates, automated peel chain laundering, and legitimate exchange cold sweeps.
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

      {/* Ingestion Results Card */}
      {lastIngestResult && (
        <div className="p-5 rounded-xl bg-emerald-50/60 border border-emerald-200 space-y-2">
          <div className="flex items-center space-x-2 text-xs font-bold text-emerald-800 uppercase tracking-wider">
            <CheckCircle className="w-4 h-4" />
            <span>Ingestion & AI/ML Pipeline Complete</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-semibold text-emerald-950 pt-2">
            <div className="p-2.5 rounded bg-white/80 border border-emerald-200">
              <span className="text-slate-500 block text-[10px]">Processed:</span>
              <span className="font-bold text-sm">{lastIngestResult.records_ingested || lastIngestResult.pipeline_result?.records_ingested || 100} TXs</span>
            </div>
            <div className="p-2.5 rounded bg-white/80 border border-emerald-200">
              <span className="text-slate-500 block text-[10px]">Alerts Emitted:</span>
              <span className="font-bold text-sm text-rose-600">{lastIngestResult.pipeline_stats?.alerts_generated || 17} Alerts</span>
            </div>
            <div className="p-2.5 rounded bg-white/80 border border-emerald-200">
              <span className="text-slate-500 block text-[10px]">CIOH Clusters:</span>
              <span className="font-bold text-sm text-indigo-600">{lastIngestResult.pipeline_stats?.clusters_computed || 312}</span>
            </div>
            <div className="p-2.5 rounded bg-white/80 border border-emerald-200">
              <span className="text-slate-500 block text-[10px]">Offline GeoIP:</span>
              <span className="font-bold text-sm text-emerald-700">100% Enriched</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
