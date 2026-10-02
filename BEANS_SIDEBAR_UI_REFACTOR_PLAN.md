# BEANS: Sidebar UI Overhaul (implemented)

`ui/src/components/Sidebar.jsx` had 15 pages in one flat list. It now has 17 pages in five collapsible groups and a compact
icon rail. This is the plan as built; the larger roadmap is in
[`BEANS_IMPROVEMENT_EXECUTION_PLAN.md`](BEANS_IMPROVEMENT_EXECUTION_PLAN.md).

## Structure

| Group | Pages |
|---|---|
| Monitor | Overview, Alert Triage, Watchlist, Live Monitor, Review Queue |
| Investigate | Link Graph, Entity 360, Timeline, Geo Map |
| Intelligence | Cash-Out Forecast, Mixer Lab |
| Legal & Evidence | Cases & Evidence, Legal Approvals, Model Card, Audit Trail (supervisors) |
| Data | Ingest & Seeds, Rules & Integrations |

## Behaviour

- **Collapsible groups.** Each group header toggles its pages (`aria-expanded`). While a group is closed, its header shows the sum
  of its badge counts, so an urgent count (open movements, pending approvals) is never hidden.
- **Icon rail.** One button toggles 240 px (`w-60`) and 64 px (`w-16`). In the rail the labels become native tooltips and
  accessible names, badges sit on the icon, and groups are separated by a line.
- **Remembered per browser** in `localStorage`; every access is guarded, so the sidebar works when storage is blocked.
- **Accessibility.** Buttons carry `aria-label` and `aria-current="page"`, and have a visible keyboard focus ring.
- **Unchanged:** role-based hiding (`minRole`), badges, the Ctrl+K command palette, and `PAGE_TITLES` (the top bar's group
  label follows the group names).

## Decisions

- **No in-sidebar search.** The command palette (Ctrl+K) already finds wallets, transactions, IPs, alerts, clusters and cases.
- **No Threat Matrix page.** It had no data behind it (see the execution plan).
- **Group name `Report` became `Legal & Evidence`,** because the group now holds the court-evidence and approval pages.

## Verification

1. `cd ui && npm run lint && npm run build` on **Node 22** (the build needs ≥ 20.19). CI fails if the committed `ui/dist` does not
   match the source, so commit the rebuilt `ui/dist`.
2. `beans serve`, open `http://127.0.0.1:8000`: collapse a group and reload (it stays collapsed); collapse to the rail and reload
   (it stays a rail); open Cash-Out Forecast and Mixer Lab.
3. Checked in headless Chromium against the synthetic demo data: five groups, rail width 64 px, state persisted across reloads,
   both new pages render, no console errors.
