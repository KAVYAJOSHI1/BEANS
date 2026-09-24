import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import OverviewDashboard from './components/OverviewDashboard';
import AlertTriage from './components/AlertTriage';
import LinkGraph from './components/LinkGraph';
import TimelineReplay from './components/TimelineReplay';
import GeoMap from './components/GeoMap';
import Entity360 from './components/Entity360';
import CaseManager from './components/CaseManager';
import ModelCard from './components/ModelCard';
import IngestStudio from './components/IngestStudio';

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

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      // 1. Stats
      const statsRes = await fetch(`${API_BASE}/stats/overview`).then((r) => r.json()).catch(() => null);
      if (statsRes) setStats(statsRes);

      // 2. Alerts
      const alertsRes = await fetch(`${API_BASE}/alerts?limit=100`).then((r) => r.json()).catch(() => []);
      if (Array.isArray(alertsRes)) setAlerts(alertsRes);

      // 3. Graph Topology
      const graphRes = await fetch(`${API_BASE}/graph/topology?limit=120`).then((r) => r.json()).catch(() => null);
      if (graphRes) setGraphData(graphRes);

      // 4. Timeline
      const timelineRes = await fetch(`${API_BASE}/timeline/sequence?limit=40`).then((r) => r.json()).catch(() => []);
      if (Array.isArray(timelineRes)) setTimelineEvents(timelineRes);

      // 5. GeoMap
      const geoRes = await fetch(`${API_BASE}/geomap/origins`).then((r) => r.json()).catch(() => null);
      if (geoRes) setGeoData(geoRes);

      // 6. Cases
      const casesRes = await fetch(`${API_BASE}/cases`).then((r) => r.json()).catch(() => []);
      if (Array.isArray(casesRes)) setCases(casesRes);

      // 7. Model Card
      const modelRes = await fetch(`${API_BASE}/modelcard`).then((r) => r.json()).catch(() => null);
      if (modelRes) setModelCardData(modelRes);

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

  const handleAddToCase = async (caseId, entityId) => {
    await fetch(`${API_BASE}/cases/${caseId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ add_entities: [entityId] }),
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

  const handleUploadFile = async (file) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
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

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onRefresh={fetchAllData}
        loading={loading}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
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

        {activeTab === 'graph' && (
          <LinkGraph
            graphData={graphData}
            selectedNode={selectedNode}
            onSelectNode={(n) => setSelectedNode(n)}
            onLoadGraph={loadGraph}
            onInspectEntity={inspectEntity}
            onOpenTimeline={openTimeline}
          />
        )}

        {activeTab === 'timeline' && <TimelineReplay timelineEvents={timelineEvents} />}

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

        {activeTab === 'modelcard' && <ModelCard modelCard={modelCardData} />}

        {activeTab === 'ingest' && (
          <IngestStudio
            onUploadFile={handleUploadFile}
            onGenerateDemo={handleGenerateDemo}
            onUploadSeeds={handleUploadSeeds}
            loading={loading}
            lastIngestResult={lastIngestResult}
          />
        )}
      </main>

      <footer className="text-center text-[11px] text-slate-400 py-4">
        BEANS · SIH PS 26146 · runs fully offline · IP geolocation by{' '}
        <a href="https://db-ip.com" className="underline">DB-IP</a> (CC BY 4.0) · all data shown is synthetic
      </footer>
    </div>
  );
}
