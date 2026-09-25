import React, { useEffect, useMemo, useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { ZoomIn, ZoomOut, Maximize2, Search, Crosshair, UserCheck, Clock, X } from 'lucide-react';

// fcose is a much faster force-directed layout than the built-in cose (~0.7 s vs ~22 s on the default view).
cytoscape.use(fcose);

const riskColor = (risk) => {
  if (risk >= 85) return '#dc2626';
  if (risk >= 65) return '#f97316';
  if (risk >= 40) return '#eab308';
  return '#3b82f6';
};

const STYLESHEET = [
  {
    selector: 'node[type="WALLET"]',
    style: {
      shape: 'ellipse',
      'background-color': (ele) => riskColor(ele.data('risk_score') || 0),
      label: 'data(label)', color: '#1e293b', 'font-size': 9, 'font-family': 'monospace',
      width: (ele) => 22 + (ele.data('risk_score') || 0) / 5, height: (ele) => 22 + (ele.data('risk_score') || 0) / 5,
      'border-width': (ele) => (ele.data('is_seed') ? 5 : ele.data('is_center') ? 4 : 1),
      'border-color': (ele) => (ele.data('is_seed') ? '#7f1d1d' : ele.data('is_center') ? '#0f172a' : '#94a3b8'),
      'text-valign': 'bottom', 'text-margin-y': 3,
    },
  },
  {
    selector: 'node[type="TRANSACTION"]',
    style: { shape: 'diamond', 'background-color': '#6366f1', label: 'data(label)', color: '#475569', 'font-size': 8,
      width: 18, height: 18, 'text-valign': 'bottom', 'text-margin-y': 3 },
  },
  {
    selector: 'node[type="IP"]',
    style: {
      shape: 'triangle', label: 'data(label)', color: '#475569', 'font-size': 8, width: 22, height: 22,
      'background-color': (ele) => (['TOR_EXIT', 'BULLETPROOF', 'VPN'].includes(ele.data('isp_type')) ? '#be123c' : '#0ea5e9'),
      'text-valign': 'bottom', 'text-margin-y': 3,
    },
  },
  { selector: 'edge', style: { width: 1.2, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.7,
      'line-color': '#cbd5e1', 'target-arrow-color': '#cbd5e1' } },
  { selector: 'edge[type="INPUT"]', style: { 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8' } },
  { selector: 'edge[type="OUTPUT"]', style: { 'line-color': '#818cf8', 'target-arrow-color': '#818cf8' } },
  { selector: 'edge[type="RELAYED"]', style: { 'line-style': 'dashed', 'line-color': '#38bdf8', 'target-arrow-color': '#38bdf8' } },
  { selector: '.evidence', style: { 'border-width': 5, 'border-color': '#dc2626', 'line-color': '#dc2626',
      'target-arrow-color': '#dc2626', width: 3, 'z-index': 10 } },
  { selector: '.faded', style: { opacity: 0.25 } },
  { selector: ':selected', style: { 'border-width': 5, 'border-color': '#2563eb' } },
];

const LAYOUTS = {
  cose: { name: 'fcose', animate: false, randomize: true, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 30 },
  breadthfirst: { name: 'breadthfirst', directed: true, spacingFactor: 1.1, padding: 30 },
  concentric: { name: 'concentric', concentric: (n) => n.data('risk_score') || 0, levelWidth: () => 20, padding: 30 },
};

export default function LinkGraph({ active = true, graphData, onSelectNode, selectedNode, onLoadGraph, onInspectEntity, onOpenTimeline }) {
  const [layoutName, setLayoutName] = useState('cose');
  const [query, setQuery] = useState('');
  const [hops, setHops] = useState(2);
  const [minRisk, setMinRisk] = useState(0);
  const [showEvidence, setShowEvidence] = useState(true);
  const cyRef = useRef(null);

  // Stable reference: otherwise every re-render (e.g. selecting a node) makes cytoscape re-diff the whole graph.
  const elements = useMemo(() => [...(graphData?.nodes || []), ...(graphData?.edges || [])], [graphData]);
  const summary = graphData?.summary || {};

  // Re-run the layout whenever the data or layout changes. The graph stays mounted while hidden on other
  // tabs, where the canvas has zero size, so defer the layout until it is visible again.
  const laidOut = useRef(null);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !active) return;
    cy.resize();
    if (!elements.length) return;
    if (laidOut.current?.graphData === graphData && laidOut.current?.layoutName === layoutName) return;
    laidOut.current = { graphData, layoutName };
    cy.layout(LAYOUTS[layoutName]).run();
    cy.fit(undefined, 30);
  }, [graphData, layoutName, active]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass('evidence faded');
      const ids = [...(graphData?.highlight?.path_to_seed || []), ...(graphData?.highlight?.txids || [])];
      if (!showEvidence || !ids.length) return;
      const hl = cy.collection(ids.map((id) => cy.getElementById(id)).filter((e) => e.length));
      hl.addClass('evidence');
      hl.edgesWith(hl).addClass('evidence');
    });
  }, [graphData, showEvidence]);

  const load = (center) => onLoadGraph({ center: center ?? (query.trim() || null), hops, minRisk });

  const btn = (active) =>
    `px-2.5 py-1 rounded-md text-xs font-semibold transition-all ${active ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`;

  return (
    <div className="space-y-4">
      <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-3">
        <form className="flex items-center gap-2 flex-1 min-w-[280px]" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-2" />
            <input value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Center on wallet, txid or IP (empty = top alerts)"
              className="w-full pl-8 pr-2 py-1.5 text-xs font-mono border border-slate-200 rounded-md bg-slate-50" />
          </div>
          <label className="text-xs text-slate-500">hops
            <select value={hops} onChange={(e) => setHops(Number(e.target.value))} className="ml-1 border rounded px-1 py-0.5">
              {[1, 2, 3].map((h) => <option key={h}>{h}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-500 flex items-center gap-1">min risk
            <input type="range" min="0" max="90" step="5" value={minRisk} onChange={(e) => setMinRisk(Number(e.target.value))} />
            <span className="w-6 font-semibold text-slate-700">{minRisk}</span>
          </label>
          <button className="px-3 py-1.5 rounded-md bg-blue-600 text-white text-xs font-semibold">Load</button>
        </form>
        <div className="flex items-center gap-1">
          <button onClick={() => setLayoutName('cose')} className={btn(layoutName === 'cose')}>Force</button>
          <button onClick={() => setLayoutName('breadthfirst')} className={btn(layoutName === 'breadthfirst')}>Flow (chains)</button>
          <button onClick={() => setLayoutName('concentric')} className={btn(layoutName === 'concentric')}>By risk</button>
          <button onClick={() => setShowEvidence(!showEvidence)} className={btn(showEvidence)}>Evidence path</button>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200"><ZoomIn className="w-4 h-4" /></button>
          <button onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200"><ZoomOut className="w-4 h-4" /></button>
          <button onClick={() => cyRef.current?.fit(undefined, 30)} className="p-1.5 rounded bg-slate-100 hover:bg-slate-200"><Maximize2 className="w-4 h-4" /></button>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-slate-600 px-1">
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-red-600" /> wallet risk ≥ 85</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-orange-500" /> 65–84</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-yellow-500" /> 40–64</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-blue-500" /> &lt; 40</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full border-4 border-red-900" /> seed wallet</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-indigo-500 rotate-45" /> transaction</span>
        <span className="flex items-center gap-1"><span className="w-0 h-0 border-l-[6px] border-r-[6px] border-b-[10px] border-transparent border-b-sky-500" /> relaying IP (red = Tor/VPN/bulletproof)</span>
        <span className="ml-auto text-slate-500">
          {summary.center ? <>centered on <span className="font-mono">{String(summary.center).slice(0, 18)}…</span> · </> : 'top alerts · '}
          {summary.node_count ?? 0} nodes · {summary.edge_count ?? 0} edges
        </span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm h-[620px] relative overflow-hidden">
        {elements.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
            No graph data. Ingest a dataset first, or search for an entity.
          </div>
        )}
        <CytoscapeComponent
          elements={elements}
          stylesheet={STYLESHEET}
          style={{ width: '100%', height: '100%' }}
          minZoom={0.1}
          maxZoom={3}
          hideEdgesOnViewport
          cy={(cy) => {
            if (cyRef.current === cy) return;
            cyRef.current = cy;
            cy.on('tap', 'node', (evt) => onSelectNode(evt.target.data()));
          }}
        />

        {selectedNode && (
          <div className="absolute top-4 right-4 w-80 p-4 rounded-xl bg-white/95 backdrop-blur border border-slate-200 shadow-xl text-xs space-y-2">
            <div className="flex items-center justify-between font-bold text-slate-900">
              <span>{selectedNode.type}</span>
              <button onClick={() => onSelectNode(null)}><X className="w-4 h-4 text-slate-400" /></button>
            </div>
            <div className="font-mono text-slate-700 break-all">{selectedNode.full_id}</div>
            {selectedNode.type === 'WALLET' && (
              <div className="grid grid-cols-2 gap-1 text-slate-600">
                <span>Risk</span><span className="font-bold" style={{ color: riskColor(selectedNode.risk_score) }}>{(selectedNode.risk_score || 0).toFixed(0)} / 100</span>
                <span>Alert</span><span>{selectedNode.alert_type}</span>
                <span>Cluster</span><span className="font-mono truncate">{selectedNode.cluster_id}</span>
                <span>Seed</span><span>{selectedNode.is_seed ? 'yes (known illicit)' : 'no'}</span>
              </div>
            )}
            {selectedNode.type === 'TRANSACTION' && (
              <div className="grid grid-cols-2 gap-1 text-slate-600">
                <span>Value</span><span>{(selectedNode.value || 0).toFixed(6)} BTC</span>
                <span>Fee</span><span>{(selectedNode.fee || 0).toFixed(6)} BTC</span>
                <span>In / out</span><span>{selectedNode.n_inputs} / {selectedNode.n_outputs}</span>
                <span>Time</span><span>{selectedNode.timestamp}</span>
              </div>
            )}
            {selectedNode.type === 'IP' && (
              <div className="grid grid-cols-2 gap-1 text-slate-600">
                <span>Country</span><span>{selectedNode.country}</span>
                <span>ASN</span><span>{selectedNode.asn}</span>
                <span>Type</span><span>{selectedNode.isp_type}</span>
              </div>
            )}
            <div className="flex flex-wrap gap-1.5 pt-1">
              <button onClick={() => { setQuery(selectedNode.full_id); load(selectedNode.full_id); }}
                className="flex items-center gap-1 px-2 py-1 rounded bg-blue-600 text-white font-semibold">
                <Crosshair className="w-3 h-3" /> Expand here
              </button>
              {selectedNode.type === 'WALLET' && (
                <>
                  <button onClick={() => onInspectEntity(selectedNode.full_id)} className="flex items-center gap-1 px-2 py-1 rounded bg-slate-100 font-semibold">
                    <UserCheck className="w-3 h-3" /> Entity 360
                  </button>
                  <button onClick={() => onOpenTimeline(selectedNode.full_id)} className="flex items-center gap-1 px-2 py-1 rounded bg-slate-100 font-semibold">
                    <Clock className="w-3 h-3" /> Timeline
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
