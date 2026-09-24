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
  const [activeTab, setActiveTab] = useState('overview');
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

  const fetchEntity360 = async (address) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/entity/wallet/${address}`).then((r) => r.json());
      setEntityData(res);
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

  const handleUploadFile = async (file) => {
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/ingest/upload`, {
        method: 'POST',
        body: formData,
      }).then((r) => r.json());
      setLastIngestResult(res);
      await fetchAllData();
      setActiveTab('alerts');
    } catch (e) {
      console.error('Error uploading file:', e);
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
            onInspectEntity={(addr) => fetchEntity360(addr)}
          />
        )}

        {activeTab === 'graph' && (
          <LinkGraph
            graphData={graphData}
            selectedNode={selectedNode}
            onSelectNode={(n) => setSelectedNode(n)}
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
            loading={loading}
            lastIngestResult={lastIngestResult}
          />
        )}
      </main>
    </div>
  );
}
