import { useSyncExternalStore } from 'react';

// Severity cut-offs come from the backend (/api/config ← beans/config.py). The values below are only the
// first-paint fallback until that request returns.
let config = { severity_thresholds: { CRITICAL: 85, HIGH: 65, MEDIUM: 40 }, data_origin: null, loaded: false };
const listeners = new Set();

export async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    if (r.ok) {
      config = { ...(await r.json()), loaded: true };
      listeners.forEach((l) => l());
    }
  } catch { /* keep the fallback */ }
  return config;
}

export function useConfig() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => config);
}

export const thresholds = () => config.severity_thresholds;

export function severityOf(risk) {
  const t = config.severity_thresholds;
  return risk >= t.CRITICAL ? 'CRITICAL' : risk >= t.HIGH ? 'HIGH' : risk >= t.MEDIUM ? 'MEDIUM' : 'LOW';
}

export const SEVERITY_COLOR = { CRITICAL: '#dc2626', HIGH: '#f97316', MEDIUM: '#eab308', LOW: '#3b82f6' };
export const riskColor = (risk) => SEVERITY_COLOR[severityOf(risk || 0)];
