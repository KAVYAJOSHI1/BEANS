import React, { useEffect, useMemo, useRef, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import cola from 'cytoscape-cola';
import {
  ZoomIn, ZoomOut, Maximize2, Search, Crosshair, UserCheck, Clock, X, Sparkles, Orbit, Lasso, Briefcase,
} from 'lucide-react';
import { canvasColors, useTheme } from '../theme';

// fcose is a much faster force-directed layout than the built-in cose (~0.7 s vs ~22 s on the default view).
cytoscape.use(fcose);
cytoscape.use(cola);   // continuous physics for the optional "Live physics" mode

const MOTION_NODE_CAP = 300;          // above this, only flows touching high-risk wallets animate (keeps the canvas smooth)
const LARGE_FLOW_EDGE_CAP = 150;
const RISKY_IP = ['TOR_EXIT', 'BULLETPROOF', 'VPN'];
const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

const riskColor = (risk) => {
  if (risk >= 85) return '#dc2626';
  if (risk >= 65) return '#f97316';
  if (risk >= 40) return '#eab308';
  return '#3b82f6';
};

const stylesheet = (c) => [
  {
    selector: 'node[type="WALLET"]',
    style: {
      shape: 'ellipse',
      'background-color': (ele) => riskColor(ele.data('risk_score') || 0),
      label: 'data(label)', color: c.label, 'font-size': 9, 'font-family': 'JetBrains Mono Variable, monospace',
      width: (ele) => 22 + (ele.data('risk_score') || 0) / 5, height: (ele) => 22 + (ele.data('risk_score') || 0) / 5,
      'border-width': (ele) => (ele.data('is_seed') ? 5 : ele.data('is_center') ? 4 : 1),
      'border-color': (ele) => (ele.data('is_seed') ? '#7f1d1d' : ele.data('is_center') ? c.text : '#94a3b8'),
      'text-valign': 'bottom', 'text-margin-y': 3,
      'underlay-color': '#ef4444', 'underlay-opacity': 0, 'underlay-padding': 0, 'underlay-shape': 'ellipse',
    },
  },
  {
    selector: 'node[type="TRANSACTION"]',
    style: { shape: 'diamond', 'background-color': '#6366f1', label: 'data(label)', color: c.muted, 'font-size': 8,
      width: 18, height: 18, 'text-valign': 'bottom', 'text-margin-y': 3, 'underlay-color': '#818cf8', 'underlay-opacity': 0 },
  },
  {
    selector: 'node[type="IP"]',
    style: {
      shape: 'triangle', label: 'data(label)', color: c.muted, 'font-size': 8, width: 22, height: 22,
      'background-color': (ele) => (RISKY_IP.includes(ele.data('isp_type')) ? '#be123c' : '#0ea5e9'),
      'text-valign': 'bottom', 'text-margin-y': 3, 'underlay-color': '#f43f5e', 'underlay-opacity': 0, 'underlay-shape': 'ellipse',
    },
  },
  { selector: 'edge', style: { width: 1.2, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.7,
      'line-color': c.edge, 'target-arrow-color': c.edge } },
  { selector: 'edge[type="INPUT"]', style: { 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8' } },
  { selector: 'edge[type="OUTPUT"]', style: { 'line-color': '#818cf8', 'target-arrow-color': '#818cf8' } },
  { selector: 'edge[type="RELAYED"]', style: { 'line-style': 'dashed', 'line-color': '#38bdf8', 'target-arrow-color': '#38bdf8' } },
  // flow mode: value-carrying edges become moving dashes ("particles"); faster = more BTC
  { selector: 'edge.flow', style: { 'line-style': 'dashed', 'line-dash-pattern': [2, 7], 'line-cap': 'round', width: 2.2 } },
  { selector: '.evidence', style: { 'border-width': 5, 'border-color': '#dc2626', 'line-color': '#dc2626',
      'target-arrow-color': '#dc2626', width: 3, 'z-index': 10 } },
  { selector: 'edge.evidence.flow', style: { width: 3.2, 'line-dash-pattern': [3, 6] } },
  { selector: 'node.evidence', style: { 'underlay-color': '#f43f5e', 'underlay-opacity': 0.25, 'underlay-padding': 7 } },
  { selector: '.faded', style: { opacity: 0.25 } },
  { selector: 'node:selected', style: { 'border-width': 5, 'border-color': '#2563eb', 'overlay-color': '#2563eb', 'overlay-opacity': 0.12 } },
];

const LAYOUTS = {
  cose: { name: 'fcose', animate: false, randomize: true, nodeRepulsion: 9000, idealEdgeLength: 70, padding: 30 },
  breadthfirst: { name: 'breadthfirst', directed: true, spacingFactor: 1.1, padding: 30 },
  concentric: { name: 'concentric', concentric: (n) => n.data('risk_score') || 0, levelWidth: () => 20, padding: 30 },
};
const PHYSICS = { name: 'cola', infinite: true, fit: false, randomize: false, animate: true, avoidOverlap: true,
  nodeSpacing: 8, edgeLength: 70, maxSimulationTime: 1e9, handleDisconnected: true };

const speedBucket = (amt) => (amt >= 1 ? 3 : amt >= 0.05 ? 2 : 1);   // dash pixels per frame

function pointInPolygon([x, y], poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export default function LinkGraph({
  active = true, graphData, onSelectNode, selectedNode, onLoadGraph, onInspectEntity, onOpenTimeline,
  cases = [], onAddEntitiesToCase, onCreateCase,
}) {
  const theme = useTheme();
  const [layoutName, setLayoutName] = useState('cose');
  const [query, setQuery] = useState('');
  const [hops, setHops] = useState(2);
  const [minRisk, setMinRisk] = useState(0);
  const [showEvidence, setShowEvidence] = useState(true);
  const [motion, setMotion] = useState(() => !reducedMotion());
  const [physics, setPhysics] = useState(false);
  const [lassoMode, setLassoMode] = useState(false);
  const [lassoPath, setLassoPath] = useState(null);
  const [selection, setSelection] = useState([]);
  const [caseTarget, setCaseTarget] = useState('');
  const cyRef = useRef(null);
  const physicsRef = useRef(null);
  const boxRef = useRef(null);

  const elements = useMemo(() => [...(graphData?.nodes || []), ...(graphData?.edges || [])], [graphData]);
  const summary = graphData?.summary || {};
  const nodeCount = graphData?.nodes?.length || 0;
  const tooBig = nodeCount > MOTION_NODE_CAP;
  const animate = motion && active;
  const sheet = useMemo(() => stylesheet(canvasColors(theme)), [theme]);

  useEffect(() => { cyRef.current?.style(sheet); }, [sheet]);

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
    physicsRef.current?.stop();
    cy.layout(LAYOUTS[layoutName]).run();
    cy.fit(undefined, 30);
    if (physics) { physicsRef.current = cy.layout(PHYSICS); physicsRef.current.run(); }
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

  // ---- live physics (cola, runs until switched off)
  useEffect(() => {
    const cy = cyRef.current;
    physicsRef.current?.stop();
    physicsRef.current = null;
    if (!cy || !physics || !active || !elements.length) return undefined;
    physicsRef.current = cy.layout(PHYSICS);
    physicsRef.current.run();
    return () => physicsRef.current?.stop();
  }, [physics, active, graphData]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- flow particles + pulsing threat halos (one animation loop, ~30 fps, paused when hidden)
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return undefined;
    const valueEdges = cy.edges('[type="INPUT"], [type="OUTPUT"]');
    const flowEdges = tooBig
      ? valueEdges.filter((e) => e.connectedNodes().some((n) => (n.data('risk_score') || 0) >= 65)).slice(0, LARGE_FLOW_EDGE_CAP)
      : valueEdges;
    const halos = cy.nodes().filter((n) => n.data('is_seed') || (n.data('type') === 'WALLET' && (n.data('risk_score') || 0) >= 85)
      || (n.data('type') === 'IP' && RISKY_IP.includes(n.data('isp_type'))));
    if (!animate) {
      cy.batch(() => {
        valueEdges.removeClass('flow');
        halos.not('.rippling').style({ 'underlay-opacity': 0, 'underlay-padding': 0 });
      });
      return undefined;
    }
    const buckets = [1, 2, 3].map((b) => flowEdges.filter((e) => speedBucket(e.data('amount') || 0) === b));
    flowEdges.addClass('flow');
    let raf = 0;
    let last = 0;
    let offset = 0;
    const interval = tooBig ? 90 : 33;   // every tick redraws the canvas: tick less often on big graphs
    const tick = (t) => {
      raf = requestAnimationFrame(tick);
      if (document.hidden || t - last < interval) return;
      last = t;
      offset += 1;
      const phase = (Math.sin(t / 420) + 1) / 2;                       // 0..1 breathing
      cy.batch(() => {
        buckets.forEach((edges, i) => edges.style('line-dash-offset', -offset * (i + 1) * (tooBig ? 2.5 : 1)));
        halos.not('.rippling').style({ 'underlay-opacity': 0.12 + 0.28 * phase, 'underlay-padding': 4 + 9 * phase });
      });
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      cy.batch(() => {
        flowEdges.removeClass('flow');
        halos.style({ 'underlay-opacity': 0, 'underlay-padding': 0 });
      });
    };
  }, [animate, graphData, tooBig]);

  const ripple = (node) => {
    if (!motion || reducedMotion()) return;
    node.addClass('rippling');
    node.stop(true);
    node.style({ 'underlay-color': '#3b82f6', 'underlay-opacity': 0.45, 'underlay-padding': 2 });
    node.animate({ style: { 'underlay-opacity': 0, 'underlay-padding': 28 } }, {
      duration: 650, easing: 'ease-out',
      complete: () => { node.removeStyle('underlay-color underlay-opacity underlay-padding'); node.removeClass('rippling'); },
    });
  };
  const rippleRef = useRef(ripple);
  useEffect(() => { rippleRef.current = ripple; });

  // ---- lasso multi-select (polygon drawn on an overlay, hit-tested against rendered node positions)
  const toLocal = (e) => {
    const r = boxRef.current.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const lassoDown = (e) => { e.currentTarget.setPointerCapture(e.pointerId); setLassoPath([toLocal(e)]); };
  const lassoMove = (e) => {
    if (!lassoPath) return;
    const p = toLocal(e);
    const q = lassoPath[lassoPath.length - 1];
    if (Math.hypot(p[0] - q[0], p[1] - q[1]) > 4) setLassoPath([...lassoPath, p]);
  };
  const lassoUp = (e) => {
    const cy = cyRef.current;
    if (cy && lassoPath && lassoPath.length > 2) {
      const hit = cy.nodes().filter((n) => pointInPolygon([n.renderedPosition('x'), n.renderedPosition('y')], lassoPath));
      if (!e.shiftKey) cy.nodes().unselect();
      hit.select();
    }
    setLassoPath(null);
  };

  const selectedWallets = selection.filter((n) => n.type === 'WALLET');
  const addSelectionToCase = () => {
    const ids = selectedWallets.map((n) => n.full_id);
    if (!ids.length || !caseTarget) return;
    if (caseTarget === 'new') {
      onCreateCase?.({ case_name: `Graph selection · ${ids.length} wallets`, incident_type: 'UNKNOWN',
        notes: 'Created from a lasso selection in the link graph.', suspect_entities: ids });
    } else {
      onAddEntitiesToCase?.(caseTarget, ids);
    }
    setCaseTarget('');
    cyRef.current?.nodes().unselect();
  };

  const load = (center) => onLoadGraph({ center: center ?? (query.trim() || null), hops, minRisk });

  const btn = (on) =>
    `px-2.5 py-1 rounded-md text-xs font-semibold transition-all flex items-center gap-1 ${on ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`;

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
            <select value={hops} onChange={(e) => setHops(Number(e.target.value))} className="ml-1 border border-slate-200 bg-white rounded px-1 py-0.5">
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
          <button onClick={() => setMotion(!motion)} className={btn(motion)}
            title={tooBig ? `Large graph (> ${MOTION_NODE_CAP} nodes): only flows touching high-risk wallets animate` : 'Money-flow particles and threat halos'}>
            <Sparkles className="w-3.5 h-3.5" /> Motion
          </button>
          <button onClick={() => setPhysics(!physics)} className={btn(physics)} title="Continuous force simulation (nodes drift; drag to rearrange)">
            <Orbit className="w-3.5 h-3.5" /> Live physics
          </button>
          <button onClick={() => { setLassoMode(!lassoMode); setLassoPath(null); }} className={btn(lassoMode)}
            title="Draw around nodes to select them (Shift adds to the selection)">
            <Lasso className="w-3.5 h-3.5" /> Lasso
          </button>
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
        {animate && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 pulse-dot" /> pulsing = seed / critical / risky IP · dash speed = BTC value</span>}
        <span className="ml-auto text-slate-500">
          {summary.center ? <>centered on <span className="font-mono">{String(summary.center).slice(0, 18)}…</span> · </> : 'top alerts · '}
          {summary.node_count ?? 0} nodes · {summary.edge_count ?? 0} edges
          {tooBig && motion && <> · large graph: only high-risk flows animate</>}
        </span>
      </div>

      <div ref={boxRef} className="bg-white rounded-xl border border-slate-200 shadow-sm h-[620px] relative overflow-hidden">
        {elements.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">
            No graph data. Ingest a dataset first, or search for an entity.
          </div>
        )}
        <CytoscapeComponent
          elements={elements}
          stylesheet={sheet}
          style={{ width: '100%', height: '100%' }}
          minZoom={0.1}
          maxZoom={3}
          hideEdgesOnViewport
          boxSelectionEnabled
          cy={(cy) => {
            if (cyRef.current === cy) return;
            cyRef.current = cy;
            cy.on('tap', 'node', (evt) => { onSelectNode(evt.target.data()); rippleRef.current(evt.target); });
            let pending = 0;
            cy.on('select unselect', 'node', () => {
              cancelAnimationFrame(pending);
              pending = requestAnimationFrame(() => setSelection(cy.nodes(':selected').map((n) => n.data())));
            });
          }}
        />

        {lassoMode && (
          <svg className="absolute inset-0 w-full h-full cursor-crosshair touch-none" style={{ zIndex: 5 }}
            onPointerDown={lassoDown} onPointerMove={lassoMove} onPointerUp={lassoUp} onPointerCancel={() => setLassoPath(null)}>
            {lassoPath && (
              <polygon points={lassoPath.map((p) => p.join(',')).join(' ')}
                fill="rgba(37, 99, 235, 0.10)" stroke="#2563eb" strokeWidth="1.5" strokeDasharray="5 4" />
            )}
            {!lassoPath && (
              <text x="50%" y="28" textAnchor="middle" className="fill-slate-500" style={{ fontSize: 12 }}>
                Draw around nodes to select them · Shift adds to the selection
              </text>
            )}
          </svg>
        )}

        {selection.length > 0 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 glass border border-slate-200 shadow-xl rounded-xl px-3 py-2 flex items-center gap-2 text-xs z-10">
            <span className="font-bold text-slate-900">{selection.length} selected</span>
            <span className="text-slate-500">({selectedWallets.length} wallets)</span>
            <select value={caseTarget} onChange={(e) => setCaseTarget(e.target.value)}
              className="border border-slate-200 bg-white rounded-md px-2 py-1">
              <option value="">Add wallets to case…</option>
              {cases.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.case_name}</option>)}
              <option value="new">+ New case from selection</option>
            </select>
            <button onClick={addSelectionToCase} disabled={!caseTarget || !selectedWallets.length}
              className="px-2.5 py-1 rounded-md bg-blue-600 text-white font-semibold flex items-center gap-1 disabled:opacity-50">
              <Briefcase className="w-3.5 h-3.5" /> Add
            </button>
            <button onClick={() => cyRef.current?.nodes().unselect()} className="p-1 rounded hover:bg-slate-100 text-slate-500"><X className="w-3.5 h-3.5" /></button>
          </div>
        )}

        {selectedNode && (
          <div className="absolute top-4 right-4 w-80 p-4 rounded-xl glass border border-slate-200 shadow-xl text-xs space-y-2 z-10">
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
