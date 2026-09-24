import React, { useState, useEffect, useRef } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import { ZoomIn, ZoomOut, Maximize2, Filter, Layers, Network, Info, ShieldAlert } from 'lucide-react';

export default function LinkGraph({ graphData, onSelectNode, selectedNode }) {
  const [layoutName, setLayoutName] = useState('cose');
  const [filterType, setFilterType] = useState('ALL');
  const cyRef = useRef(null);

  const elements = [
    ...(graphData?.nodes || []),
    ...(graphData?.edges || [])
  ];

  const cytoscapeStylesheet = [
    {
      selector: 'node[type="WALLET"]',
      style: {
        'shape': 'ellipse',
        'background-color': (ele) => {
          const risk = ele.data('risk_score') || 0;
          if (risk >= 85) return '#ef4444';
          if (risk >= 65) return '#f97316';
          if (risk >= 40) return '#eab308';
          return '#3b82f6';
        },
        'label': 'data(label)',
        'color': '#1e293b',
        'font-size': '10px',
        'font-family': 'SFMono-Regular, monospace',
        'border-width': (ele) => (ele.data('is_seed') ? 4 : 1),
        'border-color': (ele) => (ele.data('is_seed') ? '#dc2626' : '#94a3b8'),
        'width': 36,
        'height': 36,
        'text-valign': 'bottom',
        'text-margin-y': 4
      }
    },
    {
      selector: 'node[type="TRANSACTION"]',
      style: {
        'shape': 'diamond',
        'background-color': '#6366f1',
        'label': 'data(label)',
        'color': '#475569',
        'font-size': '9px',
        'width': 28,
        'height': 28,
        'text-valign': 'bottom',
        'text-margin-y': 4
      }
    },
    {
      selector: 'node[type="IP"]',
      style: {
        'shape': 'triangle',
        'background-color': (ele) => (ele.data('isp_type') === 'BULLETPROOF' ? '#dc2626' : '#0ea5e9'),
        'label': 'data(label)',
        'color': '#475569',
        'font-size': '9px',
        'width': 26,
        'height': 26,
        'text-valign': 'bottom',
        'text-margin-y': 4
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 1.5,
        'line-color': '#cbd5e1',
        'target-arrow-color': '#cbd5e1',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'arrow-scale': 0.8
      }
    },
    {
      selector: 'edge[type="SPENDS"]',
      style: {
        'line-color': '#94a3b8',
        'target-arrow-color': '#94a3b8'
      }
    },
    {
      selector: 'edge[type="PAYS"]',
      style: {
        'line-color': '#6366f1',
        'target-arrow-color': '#6366f1'
      }
    },
    {
      selector: ':selected',
      style: {
        'border-width': 4,
        'border-color': '#2563eb',
        'line-color': '#2563eb',
        'target-arrow-color': '#2563eb'
      }
    }
  ];

  const handleFit = () => {
    if (cyRef.current) {
      cyRef.current.fit();
    }
  };

  const handleZoomIn = () => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() * 1.25);
    }
  };

  const handleZoomOut = () => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() * 0.8);
    }
  };

  return (
    <div className="space-y-4">
      {/* Graph Toolbar */}
      <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Layout:</span>
          <button
            onClick={() => setLayoutName('cose')}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
              layoutName === 'cose' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Force Directed (Cose)
          </button>
          <button
            onClick={() => setLayoutName('grid')}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
              layoutName === 'grid' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Grid Matrix
          </button>
          <button
            onClick={() => setLayoutName('concentric')}
            className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
              layoutName === 'concentric' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            Concentric Risk
          </button>
        </div>

        {/* Legend */}
        <div className="flex items-center space-x-3 text-xs text-slate-600">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-red-500 border border-red-700"></span> Critical Wallet
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-full bg-blue-500"></span> Normal Wallet
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-indigo-500 rotate-45"></span> Transaction
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-sky-500"></span> Relaying IP
          </span>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center space-x-1">
          <button onClick={handleZoomIn} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700">
            <ZoomIn className="w-4 h-4" />
          </button>
          <button onClick={handleZoomOut} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700">
            <ZoomOut className="w-4 h-4" />
          </button>
          <button onClick={handleFit} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700">
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Canvas Area */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm h-[600px] relative overflow-hidden">
        <CytoscapeComponent
          elements={elements}
          stylesheet={cytoscapeStylesheet}
          style={{ width: '100%', height: '100%' }}
          layout={{ name: layoutName, animate: true }}
          cy={(cy) => {
            cyRef.current = cy;
            cy.on('tap', 'node', (evt) => {
              const nodeData = evt.target.data();
              onSelectNode(nodeData);
            });
          }}
        />

        {/* Node Inspector Floating Badge */}
        {selectedNode && (
          <div className="absolute bottom-4 left-4 p-4 rounded-xl bg-white/95 backdrop-blur-md border border-slate-200 shadow-xl max-w-sm text-xs space-y-1.5">
            <div className="flex items-center justify-between font-bold text-slate-900 border-b border-slate-100 pb-1.5">
              <span>{selectedNode.type} NODE DETAILS</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">{selectedNode.label}</span>
            </div>
            <div className="font-mono text-slate-700 break-all">{selectedNode.full_id || selectedNode.id}</div>
            {selectedNode.risk_score !== undefined && (
              <div className="flex justify-between font-semibold pt-1">
                <span className="text-slate-500">Risk Score:</span>
                <span className="text-rose-600 font-bold">{selectedNode.risk_score.toFixed(0)} / 100</span>
              </div>
            )}
            {selectedNode.country && (
              <div className="flex justify-between">
                <span className="text-slate-500">Location & ASN:</span>
                <span className="font-semibold">{selectedNode.country} · {selectedNode.asn}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
