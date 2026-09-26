"""Case evidence pack: JSON (machine-readable), Markdown (UI preview) and PDF (WeasyPrint, offline).

Everything in the pack comes from the database. If something is unknown it's labelled as unknown,
never filled with a placeholder value.
"""
import hashlib
import html
import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _canonical_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _stamp_line(ts: Dict[str, Any] = None) -> str:
    if not ts:
        return "not requested"
    if ts.get("status") != "stamped":
        return f"not available ({ts.get('reason')})"
    return f"{ts['gen_time']} · serial {ts['serial']} · {ts['tsa']} · CA SHA-256 {ts['tsa_ca_sha256_fingerprint']}"


class CaseReportGenerator:
    @classmethod
    def build(cls, case: Dict[str, Any], alerts: List[Dict[str, Any]], sources: List[Dict[str, Any]],
              audit: List[Dict[str, Any]], traces: Dict[str, Any] = None) -> Dict[str, Any]:
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        evidence = {
            "case": {k: case.get(k) for k in ("id", "case_name", "incident_type", "status", "priority",
                                              "investigator", "notes", "suspect_entities", "created_at")},
            "generated_at": generated,
            "source_files": sources,
            "findings": [{
                "alert_id": a["alert_id"], "entity_type": a["entity_type"], "entity_id": a["entity_id"],
                "alert_type": a["alert_type"], "severity": a["severity"], "risk_score": a["risk_score"],
                "calibrated_confidence": a["calibrated_confidence"], "status": a["status"],
                "reasons": a["reasons"], "shap_top_features": a["shap_top_features"],
                "engine_scores": a["engine_scores"], "evidence": a["evidence"],
                "recommended_action": {k: (a.get("recommended_action") or {}).get(k)
                                       for k in ("action", "title", "rule", "legal_basis", "facts")},
            } for a in alerts],
            "audit_trail": audit,
        }
        digest = _canonical_hash(evidence)
        from beans.report.timestamp import stamp
        ts = stamp(digest)   # RFC 3161 token over the evidence hash (local TSA)
        return {
            "case_id": case["id"], "case_name": case["case_name"], "evidence_sha256": digest, "timestamp": ts,
            "evidence": evidence, "markdown": cls._markdown(evidence, digest, ts),
            "html": cls._html(evidence, digest, ts, traces or {}),
        }

    # ------------------------------------------------------------------ markdown (UI preview / download)
    @staticmethod
    def _markdown(ev: Dict[str, Any], digest: str, ts: Dict[str, Any] = None) -> str:
        c = ev["case"]
        md = [f"# BEANS Case Evidence Pack: {c['case_name']}", "",
              f"- **Case ID:** {c['id']} · **Type:** {c.get('incident_type')} · **Status:** {c.get('status')} · "
              f"**Priority:** {c.get('priority')}",
              f"- **Investigator:** {c.get('investigator') or 'unassigned'}",
              f"- **Generated:** {ev['generated_at']}",
              f"- **Evidence SHA-256:** `{digest}` (hash of the JSON evidence below; recompute it to verify integrity)",
              f"- **RFC 3161 timestamp:** {_stamp_line(ts)}",
              "", "## Investigator notes", "", c.get("notes") or "_none_", "", "## Source data", ""]
        if ev["source_files"]:
            md += ["| File | SHA-256 | Records | Ingested |", "|---|---|---|---|"]
            md += [f"| {s['file']} | `{s['sha256']}` | {s.get('records', '')} | {s.get('ingested_at', '')} |"
                   for s in ev["source_files"]]
        else:
            md.append("_No ingest log recorded (dataset was loaded from the CLI before logging was enabled)._")
        md += ["", f"## Findings ({len(ev['findings'])})", ""]
        if not ev["findings"]:
            md.append("_No alerts are linked to this case's suspect entities._")
        for f in ev["findings"]:
            e = f["evidence"] or {}
            md += [f"### {f['entity_type']} `{f['entity_id']}`",
                   f"**{f['alert_type']}** · severity **{f['severity']}** · risk **{f['risk_score']:.0f}/100** · "
                   f"confidence **{f['calibrated_confidence'] * 100:.0f}%** · status {f['status']}", "",
                   f"**Recommended action:** {(f.get('recommended_action') or {}).get('title') or 'n/a'} "
                   f"({(f.get('recommended_action') or {}).get('rule') or 'no rule'})", "",
                   "**Why flagged:**"]
            md += [f"- {r}" for r in f["reasons"]] or ["- _no reasons recorded_"]
            if f["shap_top_features"]:
                md += ["", "**Top feature contributions:**"]
                md += [f"- `{s.get('feature')}` = {s.get('value')} → impact {s.get('impact')}" for s in f["shap_top_features"]]
            cf = (f.get("evidence") or {}).get("counterfactual")
            if cf:
                md += ["", f"**What would change the verdict:** {cf['summary']}"]
            md += ["", "**Evidence:**",
                   f"- Transaction: `{e.get('txid', 'n/a')}`",
                   f"- First-relaying IP: `{e.get('first_spy_ip') or 'unknown'}` (confidence {e.get('first_spy_confidence', 'n/a')})",
                   f"- Path to seed: {' → '.join(e.get('path_to_seed') or []) or 'none found'}", ""]
        md += ["## Audit trail", ""]
        md += [f"- {a.get('created_at')} · {a.get('investigator')} · {a.get('action')} · {a.get('entity_id')}"
               for a in ev["audit_trail"]] or ["_empty_"]
        md += ["", "---", "_Generated offline by BEANS from synthetic/ingested data. Automated findings are "
               "investigative leads that require analyst review._"]
        return "\n".join(md)

    # ------------------------------------------------------------------ HTML → PDF
    @staticmethod
    def _html(ev: Dict[str, Any], digest: str, ts: Dict[str, Any] = None, traces: Dict[str, Any] = None) -> str:
        from beans.report.diagram import path_svg, trail_svg
        traces = traces or {}
        esc = lambda v: html.escape(str(v if v is not None else ""))  # noqa: E731
        c = ev["case"]
        rows = "".join(
            f"<tr><td>{esc(s['file'])}</td><td class=mono>{esc(s['sha256'])}</td><td>{esc(s.get('records'))}</td></tr>"
            for s in ev["source_files"]) or "<tr><td colspan=3><i>No ingest log recorded</i></td></tr>"
        findings = []
        for f in ev["findings"]:
            e = f["evidence"] or {}
            f = {**f, "_figures": trail_svg(traces.get(f["entity_id"])) + path_svg(e.get("path_to_seed") or [])}
            reasons = "".join(f"<li>{esc(r)}</li>" for r in f["reasons"]) or "<li><i>none</i></li>"
            shap = "".join(f"<tr><td class=mono>{esc(s.get('feature'))}</td><td>{esc(s.get('value'))}</td>"
                           f"<td>{esc(s.get('impact'))}</td></tr>" for s in f["shap_top_features"])
            findings.append(f"""
            <div class=finding><h3>{esc(f['entity_type'])} <span class=mono>{esc(f['entity_id'])}</span></h3>
            <p><span class="sev {esc(f['severity'])}">{esc(f['severity'])}</span> {esc(f['alert_type'])} ·
               risk <b>{f['risk_score']:.0f}/100</b> · confidence <b>{f['calibrated_confidence'] * 100:.0f}%</b> ·
               status {esc(f['status'])}</p>
            <p><b>Recommended action:</b> {esc((f.get('recommended_action') or {}).get('title') or 'n/a')}
               <i>({esc((f.get('recommended_action') or {}).get('rule') or 'no rule')})</i></p>
            <b>Why flagged</b><ul>{reasons}</ul>
            {f'<p><b>What would change the verdict:</b> {esc(e["counterfactual"]["summary"])}</p>' if e.get("counterfactual") else ''}
            {f'<b>Top feature contributions</b><table><tr><th>Feature</th><th>Value</th><th>Impact</th></tr>{shap}</table>' if shap else ''}
            <b>Evidence</b><ul><li>Transaction <span class=mono>{esc(e.get('txid', 'n/a'))}</span></li>
            <li>First-relaying IP <span class=mono>{esc(e.get('first_spy_ip') or 'unknown')}</span>
                (confidence {esc(e.get('first_spy_confidence', 'n/a'))})</li>
            <li>Path to seed: {esc(' → '.join(e.get('path_to_seed') or []) or 'none found')}</li></ul>
            <div class=fig>{f.get('_figures', '')}</div></div>""")
        audit = "".join(f"<li>{esc(a.get('created_at'))} · {esc(a.get('investigator'))} · {esc(a.get('action'))} · "
                        f"{esc(a.get('entity_id'))}</li>" for a in ev["audit_trail"]) or "<li><i>empty</i></li>"
        return f"""<!doctype html><html><head><meta charset=utf-8><title>{esc(c['case_name'])}</title><style>
        @page {{ size: A4; margin: 16mm 14mm; @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #666; }} }}
        body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 9.5pt; color: #111; line-height: 1.4; }}
        h1 {{ font-size: 17pt; margin: 0 0 4px; }} h2 {{ font-size: 12pt; border-bottom: 1px solid #ccc; margin-top: 18px; }}
        h3 {{ font-size: 10.5pt; margin: 0 0 4px; }} .mono {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; word-break: break-all; }}
        table {{ border-collapse: collapse; width: 100%; margin: 4px 0 8px; }} td, th {{ border: 1px solid #ddd; padding: 3px 5px; text-align: left; font-size: 8.5pt; }}
        th {{ background: #f1f3f5; }} .meta td {{ border: none; padding: 1px 6px 1px 0; }}
        .finding {{ border: 1px solid #ddd; border-radius: 4px; padding: 8px 10px; margin: 8px 0; page-break-inside: avoid; }}
        .sev {{ padding: 1px 6px; border-radius: 3px; color: #fff; font-weight: bold; font-size: 8pt; }}
        .CRITICAL {{ background: #b91c1c; }} .HIGH {{ background: #c2410c; }} .MEDIUM {{ background: #a16207; }} .LOW {{ background: #15803d; }}
        .foot {{ color: #555; font-size: 8pt; margin-top: 16px; }} .fig svg {{ max-width: 100%; height: auto; }}
        </style></head><body>
        <h1>Case Evidence Pack: {esc(c['case_name'])}</h1>
        <table class=meta><tr><td>Case ID</td><td>{esc(c['id'])}</td><td>Type</td><td>{esc(c.get('incident_type'))}</td></tr>
        <tr><td>Status</td><td>{esc(c.get('status'))}</td><td>Priority</td><td>{esc(c.get('priority'))}</td></tr>
        <tr><td>Investigator</td><td>{esc(c.get('investigator'))}</td><td>Generated</td><td>{esc(ev['generated_at'])}</td></tr></table>
        <p>Evidence SHA-256: <span class=mono>{esc(digest)}</span><br>RFC 3161 timestamp: {esc(_stamp_line(ts))}</p>
        <h2>Investigator notes</h2><p>{esc(c.get('notes') or '—')}</p>
        <h2>Source data</h2><table><tr><th>File</th><th>SHA-256</th><th>Records</th></tr>{rows}</table>
        <h2>Findings ({len(ev['findings'])})</h2>{''.join(findings) or '<p><i>No alerts linked to the suspect entities.</i></p>'}
        <h2>Audit trail</h2><ul>{audit}</ul>
        <p class=foot>Generated offline by BEANS. Automated findings are investigative leads that require analyst review.</p>
        </body></html>"""

    @staticmethod
    def to_pdf(html_doc: str) -> bytes:
        from weasyprint import HTML  # imported lazily: needs system pango/cairo
        return HTML(string=html_doc).write_pdf()
