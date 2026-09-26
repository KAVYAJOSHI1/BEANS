"""Inline SVG diagrams for evidence documents (rendered by browsers and by WeasyPrint for PDFs, fully offline)."""
import html
from typing import List, Optional

INK, MUTED, EDGE, RED, INDIGO, AMBER = "#0f172a", "#64748b", "#94a3b8", "#b91c1c", "#4f46e5", "#b45309"


def _short(a: Optional[str], n: int = 10) -> str:
    return html.escape(f"{a[:n]}…{a[-4:]}" if a and len(a) > n + 5 else (a or "?"))


def trail_svg(trace: dict, max_hops: int = 12, width: int = 700) -> str:
    """Follow-the-money chain: one row per hop (wallet → change), peels drawn to the right; exchanges in red."""
    hops = (trace or {}).get("hops") or []
    if not hops:
        return ""
    hops = hops[:max_hops]
    row = 56
    h = 30 + row * len(hops) + 26
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
             f'font-family="DejaVu Sans, sans-serif" font-size="10">',
             f'<text x="0" y="14" fill="{INK}" font-weight="bold" font-size="11">Money trail (largest output followed as change; '
             f'other outputs are peels)</text>']
    start = hops[0]["amount_in"] or 1
    for i, hp in enumerate(hops):
        y = 30 + i * row
        cx = 22
        r = 7 + 9 * min(1.0, (hp["amount_in"] or 0) / start)
        parts.append(f'<circle cx="{cx}" cy="{y + 18}" r="{r:.1f}" fill="{INDIGO}" fill-opacity="0.85"/>')
        parts.append(f'<text x="{cx}" y="{y + 21}" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">{hp["hop"]}</text>')
        parts.append(f'<text x="48" y="{y + 14}" fill="{INK}">{_short(hp["from"])} spends {hp["amount_in"]:.4f} BTC</text>')
        gap = hp.get("minutes_since_previous")
        parts.append(f'<text x="48" y="{y + 27}" fill="{MUTED}" font-size="9">{html.escape(str(hp["timestamp"])[:16])} UTC'
                     f'{f" · {gap} min after previous hop" if gap is not None else ""} · relay {html.escape(str(hp.get("asn_type") or "?"))}</text>')
        if i < len(hops) - 1:
            parts.append(f'<line x1="{cx}" y1="{y + 18 + r}" x2="{cx}" y2="{y + row + 18 - 16}" stroke="{EDGE}" stroke-width="2" '
                         f'marker-end="url(#a)"/>')
        px = 360
        for j, p in enumerate(hp["peels"][:2]):
            py = y + 12 + j * 13
            color = RED if p.get("exchange") else AMBER
            label = html.escape(p["exchange"]) if p.get("exchange") else _short(p["address"])
            parts.append(f'<line x1="{px - 20}" y1="{py - 3}" x2="{px - 4}" y2="{py - 3}" stroke="{color}" stroke-width="1.5"/>')
            parts.append(f'<text x="{px}" y="{py}" fill="{color}">{p["amount"]:.4f} BTC → {label}</text>')
        if len(hp["peels"]) > 2:
            parts.append(f'<text x="{px}" y="{y + 38}" fill="{MUTED}" font-size="9">+{len(hp["peels"]) - 2} more outputs</text>')
    end_y = 30 + row * len(hops) + 8
    stop = html.escape(str(trace.get("stop_reason", "")))
    more = f" (first {max_hops} of {len(trace['hops'])} hops shown)" if len(trace["hops"]) > max_hops else ""
    parts.append(f'<text x="0" y="{end_y}" fill="{INK}" font-weight="bold">End: {stop}{html.escape(more)}</text>')
    parts.append(f'<defs><marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
                 f'<path d="M0,0 L8,4 L0,8 z" fill="{EDGE}"/></marker></defs></svg>')
    return "".join(parts)


def path_svg(path: List[str], width: int = 700) -> str:
    """Seed → … → flagged wallet, left to right, wrapping every 5 nodes."""
    if not path or len(path) < 2:
        return ""
    per_row, step, row_h = 5, 138, 58
    rows = (len(path) + per_row - 1) // per_row
    h = 26 + rows * row_h
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
             f'font-family="DejaVu Sans, sans-serif" font-size="9">',
             f'<text x="0" y="14" fill="{INK}" font-weight="bold" font-size="11">Path from the known illicit seed to this wallet</text>']
    for i, a in enumerate(path):
        r_, c = divmod(i, per_row)
        x, y = 20 + c * step, 40 + r_ * row_h
        color = RED if i == 0 else (AMBER if i == len(path) - 1 else INDIGO)
        parts.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{color}"/>')
        tag = "seed" if i == 0 else ("flagged" if i == len(path) - 1 else f"hop {i}")
        parts.append(f'<text x="{x}" y="{y + 20}" fill="{MUTED}">{tag}: {_short(a, 8)}</text>')
        if i < len(path) - 1 and c < per_row - 1:
            parts.append(f'<line x1="{x + 10}" y1="{y}" x2="{x + step - 12}" y2="{y}" stroke="{EDGE}" stroke-width="1.5"/>')
    parts.append("</svg>")
    return "".join(parts)
