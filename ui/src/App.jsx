import React, { useState, useEffect, Suspense, lazy } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';

// Tabs are code-split so the first paint doesn't wait on echarts/cytoscape/world-atlas.
const OverviewDashboard = lazy(() => import('./components/OverviewDashboard'));
const AlertTriage = lazy(() => import('./components/AlertTriage'));
const LinkGraph = lazy(() => import('./components/LinkGraph'));
const TimelineReplay = lazy(() => import('./components/TimelineReplay'));
const GeoMap = lazy(() => import('./components/GeoMap'));
const Entity360 = lazy(() => import('./components/Entity360'));
const CaseManager = lazy(() => import('./components/CaseManager'));
const ModelCard = lazy(() => import('./components/ModelCard'));
const IngestStudio = lazy(() => import('./components/IngestStudio'));
const Integrations = lazy(() => import('./components/Integrations'));
// Warm the graph chunk in the background once the shell is up.
const preloadGraph = () => import('./components/LinkGraph');

const API_BASE = '/api';

export default function App() {
  const tabFromHash = () => (window.location.hash || '#overview').slice(1).split('?')[0] || 'overview';
  const [activeTab, setActiveTabState] = useState(tabFromHash);
  const setActiveTab = (tab) => {
    setActiveTabState(tab);
    if (window.location.hash.slice(1) !== tab) window.history.replaceState(null, '', `#${tab}`);
  };
  useEffect(() => {
    const onHash = () => setActiveTabState(tabFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  const [loading, setLoading] = useState(false);

  // Global State
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState(null);
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [geoData, setGeoData] = useState({ points: [], arcs: [] });
  const [entityData, setEntityData] = useState(null);
  const [cases, setCases] = useState([]);
  const [exportResult, setExportResult] = useState(null);
  const [modelCardData, setModelCardData] = useState(null);
  const [lastIngestResult, setLastIngestResult] = useState(null);

  // Keep the graph mounted after its first visit so switching tabs doesn't redo the layout.
  const [graphVisited, setGraphVisited] = useState(activeTab === 'graph');
  if (activeTab === 'graph' && !graphVisited) setGraphVisited(true);

  useEffect(() => {
    fetchAllData();
    const t = setTimeout(preloadGraph, 1500);
    return () => clearTimeout(t);
  }, []);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      // All independent requests run in parallel; each panel fills in as soon as its data arrives.
      const getJson = (path, fallback) => fetch(`${API_BASE}${path}`).then((r) => r.json()).catch(() => fallback);
      const [, alertsRes] = await Promise.all([
        getJson('/stats/overview', null).then((res) => { if (res) setStats(res); }),
        getJson('/alerts?limit=500', []).then((res) => { if (Array.isArray(res)) setAlerts(res); return res; }),
        getJson('/graph/topology?limit=120', null).then((res) => { if (res) setGraphData(res); }),
        getJson('/timeline/sequence?limit=40', []).then((res) => { if (Array.isArray(res)) setTimelineEvents(res); }),
        getJson('/geomap/origins', null).then((res) => { if (res) setGeoData(res); }),
        getJson('/cases', []).then((res) => { if (Array.isArray(res)) setCases(res); }),
        getJson('/modelcard', null).then((res) => { if (res) setModelCardData(res); }),
      ]);

      // Set default entity for 360 inspection if alerts exist
      if (alertsRes?.length > 0 && !entityData) {
        fetchEntity360(alertsRes[0].entity_id);
      }
    } catch (e) {
      console.error('Error fetching data:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadGraph = async ({ center = null, hops = 2, minRisk = 0 } = {}) => {
    const params = new URLSearchParams({ hops, min_risk: minRisk, limit: 150 });
    if (center) params.set('center', center);
    try {
      const r = await fetch(`${API_BASE}/graph/topology?${params}`);
      if (r.ok) setGraphData(await r.json());
      else alert(`Nothing found for ${center}`);
    } catch (e) {
      console.error('Error loading graph:', e);
    }
  };

  const openTimeline = async (entity) => {
    const r = await fetch(`${API_BASE}/timeline/sequence?limit=100&entity=${encodeURIComponent(entity)}`);
    if (r.ok) setTimelineEvents(await r.json());
    setActiveTab('timeline');
  };

  const inspectEntity = async (address) => {
    await fetchEntity360(address);
    setActiveTab('entity');
  };

  const openGraphFor = async (entity) => {
    await loadGraph({ center: entity, hops: 2 });
    setActiveTab('graph');
  };

  const fetchEntity360 = async (address) => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/entity/wallet/${encodeURIComponent(address)}`);
      setEntityData(r.ok ? await r.json() : { error: `No wallet found for ${address}` });
    } catch (e) {
      console.error('Error fetching entity 360:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStatus = async (alertId, newStatus) => {
    try {
      await fetch(`${API_BASE}/alerts/${alertId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      // Refresh local alerts
      setAlerts((prev) =>
        prev.map((a) => (a.alert_id === alertId ? { ...a, status: newStatus } : a))
      );
      if (selectedAlert?.alert_id === alertId) {
        setSelectedAlert((prev) => ({ ...prev, status: newStatus }));
      }
    } catch (e) {
      console.error('Error updating status:', e);
    }
  };

  const handleCreateCase = async (casePayload) => {
    try {
      await fetch(`${API_BASE}/cases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(casePayload),
      });
      fetchAllData();
    } catch (e) {
      console.error('Error creating case:', e);
    }
  };

  const handleAddToCase = async (caseId, entityIds) => {
    await fetch(`${API_BASE}/cases/${caseId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ add_entities: [].concat(entityIds) }),
    });
    const casesRes = await fetch(`${API_BASE}/cases`).then((r) => r.json()).catch(() => []);
    if (Array.isArray(casesRes)) setCases(casesRes);
  };

  const handleExportDossier = async (caseId) => {
    try {
      const res = await fetch(`${API_BASE}/cases/${caseId}/export`).then((r) => r.json());
      setExportResult(res);
    } catch (e) {
      console.error('Error exporting dossier:', e);
    }
  };

  const handleGenerateDemo = async (nTx) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/ingest/synth-demo?n_tx=${nTx}`, { method: 'POST' }).then((r) =>
        r.json()
      );
      setLastIngestResult(res);
      await fetchAllData();
      setActiveTab('overview');
    } catch (e) {
      console.error('Error running synthetic demo:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSeeds = async (file) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const r = await fetch(`${API_BASE}/seeds/upload`, { method: 'POST', body: formData });
      const res = await r.json();
      if (!r.ok) throw new Error(res.detail || 'seed upload failed');
      setLastIngestResult(res);
      await fetchAllData();
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFile = async (file, mapping) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (mapping) formData.append('mapping', mapping);
      const r = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: formData });
      const res = await r.json();
      if (!r.ok) throw new Error(res.detail || 'upload failed');
      setLastIngestResult(res);
      await fetchAllData();
      setActiveTab('alerts');
    } catch (e) {
      alert(`Ingest failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluate = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/modelcard/evaluate`, { method: 'POST' });
      const res = await r.json();
      if (!r.ok) throw new Error(res.detail || 'evaluation failed');
      setModelCardData(res);
      await fetchAllData();
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  const counts = {
    alerts: stats?.kpis?.open_alerts ?? alerts.filter((a) => a.status === 'OPEN').length,
    cases: cases.length,
  };

  return (
    <div className="min-h-screen flex">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} counts={counts} />
      <div className="themed flex-1 min-w-0 flex flex-col bg-slate-50 text-slate-900">
      <TopBar
        activeTab={activeTab}
        stats={stats}
        loading={loading}
        onRefresh={fetchAllData}
        onSearchWallet={inspectEntity}
        onSearchGraph={openGraphFor}
      />

      <main className="flex-1 w-full max-w-[1500px] mx-auto px-6 py-6">
        <Suspense fallback={<div className="py-24 text-center text-sm text-slate-400">Loading…</div>}>
        {activeTab === 'overview' && (
          <OverviewDashboard
            stats={stats}
            alerts={alerts}
            onSelectAlert={(a) => {
              setSelectedAlert(a);
              setActiveTab('alerts');
            }}
            setActiveTab={setActiveTab}
          />
        )}

        {activeTab === 'alerts' && (
          <AlertTriage
            alerts={alerts}
            selectedAlert={selectedAlert}
            onSelectAlert={(a) => setSelectedAlert(a)}
            onCloseDrawer={() => setSelectedAlert(null)}
            onUpdateStatus={handleUpdateStatus}
            setActiveTab={setActiveTab}
            onInspectEntity={inspectEntity}
            onOpenGraph={openGraphFor}
            onOpenTimeline={openTimeline}
            cases={cases}
            onAddToCase={handleAddToCase}
            onCreateCase={handleCreateCase}
          />
        )}

        {graphVisited && (
          <div style={{ display: activeTab === 'graph' ? undefined : 'none' }}>
          <LinkGraph
            active={activeTab === 'graph'}
            graphData={graphData}
            selectedNode={selectedNode}
            onSelectNode={(n) => setSelectedNode(n)}
            onLoadGraph={loadGraph}
            onInspectEntity={inspectEntity}
            onOpenTimeline={openTimeline}
            cases={cases}
            onAddEntitiesToCase={handleAddToCase}
            onCreateCase={handleCreateCase}
          />
          </div>
        )}

        {activeTab === 'timeline' && <TimelineReplay timelineEvents={timelineEvents} onLoadTimeline={openTimeline} />}

        {activeTab === 'geomap' && <GeoMap geoData={geoData} />}

        {activeTab === 'entity' && (
          <Entity360
            entityData={entityData}
            onSearch={(addr) => fetchEntity360(addr)}
            loading={loading}
          />
        )}

        {activeTab === 'cases' && (
          <CaseManager
            cases={cases}
            onCreateCase={handleCreateCase}
            onExportDossier={handleExportDossier}
            exportResult={exportResult}
          />
        )}

        {activeTab === 'modelcard' && <ModelCard modelCard={modelCardData} onEvaluate={handleEvaluate} loading={loading} verdicts={stats?.kpis?.analyst_verdicts || 0} />}

        {activeTab === 'ingest' && (
          <IngestStudio
            onUploadFile={handleUploadFile}
            onGenerateDemo={handleGenerateDemo}
            onUploadSeeds={handleUploadSeeds}
            loading={loading}
            lastIngestResult={lastIngestResult}
          />
        )}

        {activeTab === 'integrations' && <Integrations onDataChanged={fetchAllData} />}
        </Suspense>
      </main>

      <footer className="text-center text-[11px] text-slate-400 py-4">
        BEANS · SIH PS 26146 · runs fully offline · IP geolocation by{' '}
        <a href="https://db-ip.com" className="underline">DB-IP</a> (CC BY 4.0) · all data shown is synthetic
      </footer>
      </div>
    </div>
  );
}
