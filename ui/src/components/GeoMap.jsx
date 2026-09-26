import React from 'react';
import * as echarts from 'echarts';
import ReactECharts from './Chart';
import { feature } from 'topojson-client';
import worldTopo from 'world-atlas/countries-110m.json';
import { Globe, Plane, ShieldAlert, Radio, Server } from 'lucide-react';
import { useTheme } from '../theme';

// Natural Earth 110m outlines bundled at build time, so the map works fully offline.
if (!echarts.getMap('world')) echarts.registerMap('world', feature(worldTopo, worldTopo.objects.countries));

const RISKY = new Set(['TOR_EXIT', 'BULLETPROOF', 'VPN']);

function WorldMap({ points, arcs }) {
  const dark = useTheme() === 'dark';
  const option = {
    tooltip: { trigger: 'item', formatter: (p) => p.data?.tip || p.name },
    geo: { map: 'world', roam: true, zoom: 1.15, itemStyle: { areaColor: dark ? '#1c2940' : '#e2e8f0', borderColor: dark ? '#0f1729' : '#fff' },
      emphasis: { itemStyle: { areaColor: dark ? '#2b3b58' : '#cbd5e1' }, label: { show: false } } },
    series: [
      { type: 'effectScatter', coordinateSystem: 'geo', rippleEffect: { scale: 3 }, zlevel: 2,
        data: points.map((p) => ({ name: p.ip, value: [p.lon, p.lat, p.tx_count],
          tip: `${p.ip}<br/>${p.country}${p.approximate ? ' (country centroid)' : ''} · ${p.asn || ''}<br/>${p.asn_type} · ${p.tx_count} obs`,
          itemStyle: { color: RISKY.has(p.asn_type) ? '#ef4444' : (dark ? '#60a5fa' : '#2563eb') } })),
        symbolSize: (v) => Math.min(6 + Math.sqrt(v[2]) * 2, 26) },
      { type: 'lines', coordinateSystem: 'geo', zlevel: 1,
        effect: { show: true, period: 4, symbol: 'arrow', symbolSize: 6, color: '#dc2626' },
        lineStyle: { color: '#dc2626', width: 1.5, opacity: 0.7, curveness: 0.3 },
        data: arcs.map((a) => ({ coords: [[a.from.lon, a.from.lat], [a.to.lon, a.to.lat]], tip: a.label })) },
    ],
  };
  return <ReactECharts option={option} style={{ height: 460 }} />;
}

export default function GeoMap({ geoData }) {
  const points = geoData?.points || [];
  const arcs = geoData?.arcs || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Network SIGINT & Geo-Velocity Radar</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Geographical broadcast coordinates, impossible travel speed anomalies (&gt;900 km/h), and bulletproof hosting ASNs.
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs">
          <span className="px-2.5 py-1 rounded-md bg-red-50 text-red-700 font-bold border border-red-200">
            {arcs.length} Velocity Anomalies
          </span>
          <span className="px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 font-bold border border-blue-200">
            {points.length} Relaying Entry Points
          </span>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-3">
        <WorldMap points={points} arcs={arcs} />
        <p className="text-[11px] text-slate-500 px-2">
          Red points: Tor / VPN / bulletproof-hosting relays. Red arcs: the same wallet broadcast from two places faster than
          {' '}{geoData?.threshold_kmh || 900} km/h allows. Positions use country centroids where the offline GeoIP DB has no coordinates.
        </p>
      </div>

      {/* Impossible Travel Arcs Highlights */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {arcs.map((arc, idx) => (
          <div key={idx} className="bg-white p-5 rounded-xl border border-red-200 bg-red-50/20 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Plane className="w-5 h-5 text-red-600" />
                <span className="text-xs font-bold text-red-800 uppercase tracking-wider">{arc.label}</span>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-bold bg-red-100 text-red-700">
                {arc.speed_kmh.toFixed(0)} km/h
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-semibold text-slate-800 pt-1">
              <div className="p-2 rounded bg-white border border-slate-200 w-[45%] text-center">
                <div className="text-[10px] text-slate-400">ORIGIN HOP</div>
                <div className="font-bold">{arc.from.city} ({arc.from.country})</div>
              </div>
              <span className="text-slate-400 font-bold">&rarr;</span>
              <div className="p-2 rounded bg-white border border-slate-200 w-[45%] text-center">
                <div className="text-[10px] text-slate-400">CONSECUTIVE HOP</div>
                <div className="font-bold">{arc.to.city} ({arc.to.country})</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Relaying Nodes Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 bg-slate-50 font-bold text-xs text-slate-600 uppercase tracking-wider">
          Observed P2P Entry Relayer Nodes (DB-IP Lite Offline Enriched)
        </div>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-slate-50/50 border-b border-slate-100 text-xs text-slate-500 font-semibold">
              <th className="py-2.5 px-4">Relayer IP</th>
              <th className="py-2.5 px-4">Country & City</th>
              <th className="py-2.5 px-4">Autonomous System (ASN)</th>
              <th className="py-2.5 px-4">ISP Infrastructure Type</th>
              <th className="py-2.5 px-4 text-right">Observations</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {points.map((pt, idx) => (
              <tr key={idx} className="hover:bg-slate-50/80">
                <td className="py-2.5 px-4 font-mono text-xs font-bold text-slate-900">{pt.ip}</td>
                <td className="py-2.5 px-4 text-xs font-medium text-slate-700">{pt.country} — {pt.city}</td>
                <td className="py-2.5 px-4 text-xs text-slate-600 font-mono">{pt.asn} ({pt.asn_name})</td>
                <td className="py-2.5 px-4">
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded font-bold ${
                      pt.asn_type === 'BULLETPROOF'
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : pt.asn_type === 'VPN' || pt.asn_type === 'TOR_EXIT'
                        ? 'bg-amber-50 text-amber-700 border border-amber-200'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {pt.asn_type}
                  </span>
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-xs font-bold text-slate-900">{pt.tx_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
