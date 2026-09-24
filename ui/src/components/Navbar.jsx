import React from 'react';
import { Shield, Activity, AlertTriangle, Network, Clock, Globe, UserCheck, Briefcase, Cpu, UploadCloud, RefreshCw } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'alerts', label: 'Alert Triage', icon: AlertTriangle },
  { id: 'graph', label: 'Link Graph', icon: Network },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'geomap', label: 'Geo Map', icon: Globe },
  { id: 'entity', label: 'Entity 360', icon: UserCheck },
  { id: 'cases', label: 'Cases & LE Report', icon: Briefcase },
  { id: 'modelcard', label: 'Model Card', icon: Cpu },
  { id: 'ingest', label: 'Ingest Studio', icon: UploadCloud },
];

export default function Navbar({ activeTab, setActiveTab, onRefresh, loading }) {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-slate-900 tracking-tight">BEANS</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
                  SIH PS 26146
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  OFFLINE NATIVE
                </span>
              </div>
              <p className="text-xs text-slate-500">Bitcoin Forensic Intelligence Pipeline · NTRO</p>
            </div>
          </div>

          {/* Nav Links */}
          <nav className="hidden md:flex space-x-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 shadow-sm border border-blue-100'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Quick Refresh */}
          <div className="flex items-center space-x-3">
            <button
              onClick={onRefresh}
              disabled={loading}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 transition-all flex items-center space-x-1"
              title="Refresh Pipeline Telemetry"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-600' : ''}`} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
