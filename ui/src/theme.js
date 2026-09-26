import { useSyncExternalStore } from 'react';

// Light / dark theme: a class on <html>, remembered per browser, defaulting to the OS preference.
const KEY = 'beans-theme';
const listeners = new Set();

const read = () => {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'dark' || saved === 'light') return saved;
  } catch { /* storage blocked */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

let current = read();
const apply = () => document.documentElement.classList.toggle('dark', current === 'dark');
apply();

export function setTheme(theme) {
  current = theme;
  try { localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
  apply();
  listeners.forEach((l) => l());
}

export const toggleTheme = () => setTheme(current === 'dark' ? 'light' : 'dark');

export function useTheme() {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => current);
}

// Colours for canvas-drawn widgets (Cytoscape, ECharts) that cannot read CSS variables.
export const canvasColors = (theme) => (theme === 'dark'
  ? { label: '#cbd5e1', muted: '#7d8ba3', edge: '#34445f', grid: '#22304b', surface: '#0f1729', text: '#e2e8f0' }
  : { label: '#1e293b', muted: '#475569', edge: '#cbd5e1', grid: '#e2e8f0', surface: '#ffffff', text: '#0f172a' });
