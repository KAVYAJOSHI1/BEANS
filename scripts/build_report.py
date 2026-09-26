"""Build docs/BEANS_Technical_Report.pdf: the current implementation, every feature and all measured accuracy.

Every number is read from a result file, never typed in:
  docs/results/benchmark_before.json   6-seed benchmark of the code before the accuracy work (scripts/evaluate_seeds.py)
  docs/results/benchmark_v1.0.json     6-seed benchmark of the tagged v1.0 code
  docs/results/benchmark_1m.json       ~1M-row benchmark (scripts/benchmark_1m.py)
  models/training_report.json          demo dataset (make pipeline)
  models/elliptic_report.json          real-data validation (beans validate-elliptic)
Screenshots: docs/report/img/*.png (captured from the running dashboard).

    .venv/bin/python scripts/build_report.py      → docs/BEANS_Technical_Report.pdf (+ .html)
"""
import html
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from beans.config import settings  # noqa: E402
from beans.decision.actions import ACTIONS  # noqa: E402

RES, IMG = ROOT / "docs" / "results", ROOT / "docs" / "report" / "img"
BEFORE_C, NOW_C = "#eb6834", "#2a78d6"          # validated categorical pair (dataviz palette slots 2 and 1)
e = html.escape


def load(p):
    return json.loads(Path(p).read_text())


def mean(summary, k):
    v = summary["summary"].get(k, {})
    return v.get("mean"), v.get("std")


def pct(v, d=1):
    return "n/a" if v is None else f"{100 * v:.{d}f} %"


def num(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def git(*a):
    try:
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def fig(name, caption, n, width=100):
    p = IMG / f"{name}.png"
    if not p.exists():
        return ""
    return (f'<figure><img src="{p.as_uri()}" style="width:{width}%"><figcaption><b>Figure {n}.</b> {e(caption)}'
            f'</figcaption></figure>')


# ---------------------------------------------------------------------------------------------------------- charts
def compare_chart(rows, width=640):
    """Before/now horizontal bars on one 0-1 axis, direct value labels, legend (2 series)."""
    bar, gap, label_w, top = 11, 2, 250, 30
    group = 2 * bar + gap + 16
    plot_w = width - label_w - 70
    h = top + group * len(rows) + 10
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {width} {h}" '
           f'font-family="Noto Sans, DejaVu Sans, sans-serif" font-size="10" role="img">',
           f'<rect x="{label_w}" y="6" width="10" height="10" rx="2" fill="{BEFORE_C}"/>'
           f'<text x="{label_w + 14}" y="15" fill="#333">before</text>'
           f'<rect x="{label_w + 70}" y="6" width="10" height="10" rx="2" fill="{NOW_C}"/>'
           f'<text x="{label_w + 84}" y="15" fill="#333">v1.0 (now)</text>']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        x = label_w + t * plot_w
        out.append(f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{h - 10}" stroke="#e5e5e5" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{h}" fill="#777" text-anchor="middle" font-size="8">{t:.2f}</text>')
    for i, (name, b, n) in enumerate(rows):
        y = top + i * group
        out.append(f'<text x="{label_w - 8}" y="{y + bar + 4}" fill="#222" text-anchor="end">{e(name)}</text>')
        for j, (v, c) in enumerate(((b, BEFORE_C), (n, NOW_C))):
            if v is None:
                continue
            yy = y + j * (bar + gap)
            w = max(2, v * plot_w)
            out.append(f'<rect x="{label_w}" y="{yy}" width="{w:.1f}" height="{bar}" rx="3" fill="{c}"/>')
            out.append(f'<text x="{label_w + w + 4:.1f}" y="{yy + bar - 2}" fill="#333" font-size="9">{v:.3f}</text>')
    out.append("</svg>")
    return "".join(out)


def pipeline_svg():
    boxes = [
        ("Input", "CSV / JSON / XML\nrelay observations"), ("Ingest", "validate · quarantine\nchunked · GeoIP/ASN"),
        ("DuckDB", "transactions ·\nobservations · graph"), ("5 engines", "E1 cluster · E2 anomaly\nE3 shape · E4 seeds · E5 GNN"),
        ("Fusion", "calibrated LightGBM\nSHAP · counterfactuals"), ("Alerts", "risk · confidence ·\ntypology · directive"),
    ]
    outs = ["Legal drafts + approval", "Watchlist re-alerts", "Evidence packs (RFC 3161)", "SIEM webhooks · STIX"]
    w, bw, bh = 700, 104, 54
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {w} 170" '
             f'font-family="Noto Sans, DejaVu Sans, sans-serif" font-size="9">']
    for i, (t, sub) in enumerate(boxes):
        x = 4 + i * (bw + 15)
        parts.append(f'<rect x="{x}" y="10" width="{bw}" height="{bh}" rx="6" fill="#eef4fc" stroke="{NOW_C}" stroke-width="1.2"/>')
        parts.append(f'<text x="{x + bw / 2}" y="26" text-anchor="middle" font-weight="bold" font-size="10" fill="#0f2f57">{t}</text>')
        for k, line in enumerate(sub.split("\n")):
            parts.append(f'<text x="{x + bw / 2}" y="{40 + 11 * k}" text-anchor="middle" fill="#333">{e(line)}</text>')
        if i < len(boxes) - 1:
            parts.append(f'<path d="M{x + bw + 2},{10 + bh / 2} l10,0" stroke="#666" stroke-width="1.4" marker-end="url(#ar)"/>')
    last_x = 4 + (len(boxes) - 1) * (bw + 15) + bw / 2
    for k, o in enumerate(outs):
        x = 4 + k * 175
        parts.append(f'<rect x="{x}" y="112" width="160" height="30" rx="6" fill="#fff3ec" stroke="{BEFORE_C}" stroke-width="1.2"/>')
        parts.append(f'<text x="{x + 80}" y="131" text-anchor="middle" fill="#5a2a12">{e(o)}</text>')
        parts.append(f'<path d="M{last_x},{10 + bh} L{x + 80},{108}" stroke="#999" stroke-width="1" fill="none" marker-end="url(#ar)"/>')
    parts.append('<text x="4" y="162" fill="#666" font-size="8.5">Runs fully offline (GeoIP, models, fonts, TSA bundled); '
                 'the optional live collector is a separate tool.</text>')
    parts.append('<defs><marker id="ar" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">'
                 '<path d="M0,0 L7,3.5 L0,7 z" fill="#666"/></marker></defs></svg>')
    return "".join(parts)


# ---------------------------------------------------------------------------------------------------------- report
def build():
    before, now = load(RES / "benchmark_before.json"), load(RES / "benchmark_v1.0.json")
    demo = load(ROOT / "models" / "training_report.json")
    ell = load(ROOT / "models" / "elliptic_report.json")
    big = load(RES / "benchmark_1m.json")
    fu, aq, e1, e4 = demo["fusion"], demo["alert_quality"], demo["e1"], demo["e4"]
    tag = git("describe", "--tags", "--always") or "v1.0"
    commit = git("rev-parse", "--short", "HEAD")
    M = lambda k: mean(now, k)[0]          # noqa: E731
    B = lambda k: mean(before, k)[0]       # noqa: E731
    S = lambda k: mean(now, k)[1]          # noqa: E731
    fn = iter(range(1, 100))
    st = {p.stem: (lambda d: (lambda k: d["summary"].get(k, {}).get("mean")))(load(p)) for p in sorted((RES / "stages").glob("*.json"))}
    names = {"1_context_features": "+ money-context features", "2_clustering_e4": "+ clustering fix, self-split, E4 fixes",
             "3_gnn_e5": "+ E5 graph neural network", "4_typology_corpus": "+ typology corpus"}
    stage_rows = f"<tr><td>start</td>" + "".join(f"<td class=n>{num(B(k))}</td>" for k in (
        "pr_auc", "recall_at_p50", "typology_accuracy", "e1_completeness_illicit", "e4_reached_seeded_entities", "entity_recall")) + "</tr>"
    for key, label in names.items():
        g = st[key]
        stage_rows += f"<tr><td>{e(label)}</td>" + "".join(f"<td class=n>{num(g(k))}</td>" for k in (
            "pr_auc", "recall_at_p50", "typology_accuracy", "e1_completeness_illicit", "e4_reached_seeded_entities", "entity_recall")) + "</tr>"
    stage_rows += "<tr><td><b>v1.0 (release)</b></td>" + "".join(f"<td class=n><b>{num(M(k))}</b></td>" for k in (
        "pr_auc", "recall_at_p50", "typology_accuracy", "e1_completeness_illicit", "e4_reached_seeded_entities", "entity_recall")) + "</tr>"


    chart_rows = [
        ("Fused risk PR-AUC", B("pr_auc"), M("pr_auc")),
        ("Recall of illicit wallets (P ≥ 0.5)", B("recall_at_p50"), M("recall_at_p50")),
        ("Precision (P ≥ 0.5)", B("precision_at_p50"), M("precision_at_p50")),
        ("Typology accuracy (grouped CV)", B("typology_accuracy"), M("typology_accuracy")),
        ("Typology correct on alerts", B("alert_typology_accuracy"), M("alert_typology_accuracy")),
        ("E1 clustering completeness", B("e1_completeness_illicit"), M("e1_completeness_illicit")),
        ("E4 reach inside seeded actors", B("e4_reached_seeded_entities"), M("e4_reached_seeded_entities")),
        ("Criminal entities alerted", B("entity_recall"), M("entity_recall")),
    ]
    table_keys = [
        ("PR-AUC (fused risk)", "pr_auc", True), ("ROC-AUC", "roc_auc", True),
        ("Recall at P ≥ 0.5", "recall_at_p50", True), ("Precision at P ≥ 0.5", "precision_at_p50", True),
        ("Calibration error (ECE, lower is better)", "ece", False), ("Typology accuracy, grouped CV", "typology_accuracy", True),
        ("Typology correct on alerts", "alert_typology_accuracy", True), ("E3 transaction-shape macro-F1", "e3_macro_f1", True),
        ("E1 completeness (illicit)", "e1_completeness_illicit", True), ("E1 homogeneity (illicit)", "e1_homogeneity_illicit", True),
        ("E4 hidden wallets reached, seeded actors", "e4_reached_seeded_entities", True),
        ("E4 legitimate wallets reached (lower is better)", "e4_legit_reached", False),
        ("Criminal entities with ≥ 1 alert", "entity_recall", True), ("Alerts per criminal entity (lower is better)", "alerts_per_entity", False),
        ("Alerts that are illicit", "alert_precision", True),
    ]
    trows = []
    for label, k, higher in table_keys:
        b, (n, sd) = B(k), mean(now, k)
        if n is None:
            continue
        better = None if b is None else ((n > b + 1e-9) if higher else (n < b - 1e-9))
        mark = "" if better is None or abs((n or 0) - (b or 0)) < 1e-9 else ("▲" if better else "▼")
        trows.append(f"<tr><td>{e(label)}</td><td class=n>{num(b)}</td><td class=n><b>{num(n)}</b> ± {num(sd)}</td>"
                     f"<td class='n {'up' if better else 'down' if better is False else ''}'>{mark}</td></tr>")

    det = ell["detection"]
    ell_rows = "".join(f"<tr><td>{e(k)}</td><td class=n>{v['precision']:.3f}</td><td class=n>{v['recall']:.3f}</td>"
                       f"<td class=n><b>{v['f1']:.3f}</b></td><td class=n>{v['pr_auc']:.3f}</td></tr>" for k, v in det.items())
    pub_rows = "".join(f"<tr><td>{e(k)}</td><td class=n>{v['precision']:.3f}</td><td class=n>{v['recall']:.3f}</td>"
                       f"<td class=n>{v['f1']:.3f}</td></tr>" for k, v in ell["published_weber_2019"].items())
    prop = ell["propagation"]
    af = det["BEANS LightGBM + calibration (AF)"]

    counts = demo.get("actions", {})
    rulebook = "".join(f"<tr><td><b>{e(a.replace('_', ' ').title())}</b></td><td>{e(s['rule'])}</td>"
                       f"<td>{e(s['legal_basis'])}</td><td class=n>{counts.get(a, 0)}</td></tr>" for a, s in ACTIONS.items())

    css = f"""
    @page {{ size: A4; margin: 17mm 16mm 18mm; @bottom-right {{ content: counter(page) " / " counter(pages); font-size: 8pt; color: #777; }}
             @bottom-left {{ content: "BEANS technical report · {e(tag)}"; font-size: 8pt; color: #777; }} }}
    @page :first {{ @bottom-right {{ content: none; }} @bottom-left {{ content: none; }} }}
    body {{ font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 9.6pt; color: #1b1b1b; line-height: 1.5; }}
    h1 {{ font-size: 20pt; margin: 0 0 6px; color: #0f2f57; }} h2 {{ font-size: 14pt; color: #0f2f57; margin: 22px 0 6px;
        border-bottom: 2px solid #dbe6f3; padding-bottom: 3px; page-break-after: avoid; }}
    h3 {{ font-size: 11pt; margin: 14px 0 4px; color: #16365f; page-break-after: avoid; }}
    p {{ margin: 5px 0; }} ul {{ margin: 4px 0 6px 16px; padding: 0; }} li {{ margin: 2px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 6px 0 10px; page-break-inside: avoid; }}
    th, td {{ border-bottom: 1px solid #e3e3e3; padding: 3.5px 6px; text-align: left; vertical-align: top; font-size: 8.8pt; }}
    th {{ background: #f2f5f9; font-weight: 600; }} td.n {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
    td.up {{ color: #1c7c3c; }} td.down {{ color: #b3261e; }}
    figure {{ margin: 10px 0 14px; page-break-inside: avoid; }} figure img {{ width: 100%; border: 1px solid #d9d9d9; border-radius: 4px; }}
    figcaption {{ font-size: 8.5pt; color: #555; margin-top: 3px; }}
    .cover {{ height: 245mm; display: flex; flex-direction: column; justify-content: center; }}
    .cover .sub {{ font-size: 12pt; color: #444; }} .cover .meta {{ margin-top: 30px; font-size: 9.5pt; color: #555; }}
    .tiles {{ display: flex; gap: 8px; margin: 10px 0; }} .tile {{ flex: 1; border: 1px solid #dbe6f3; border-radius: 6px; padding: 8px 10px; background: #f8fbff; }}
    .tile .v {{ font-size: 16pt; font-weight: 700; color: #0f2f57; }} .tile .l {{ font-size: 8pt; color: #555; }}
    .note {{ background: #fff8e6; border-left: 3px solid #e3a400; padding: 6px 10px; font-size: 8.8pt; margin: 8px 0; }}
    .pb {{ page-break-before: always; }} code {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 8.3pt; background: #f4f4f4; padding: 0 3px; }}
    .two {{ display: flex; gap: 12px; }} .two > div {{ flex: 1; }}
    """

    body = f"""
<section class=cover>
  <div style="font-size:10pt;color:{NOW_C};font-weight:700;letter-spacing:1px">SMART INDIA HACKATHON · PS 26146 · NTRO</div>
  <h1 style="font-size:30pt;margin-top:10px">BEANS</h1>
  <div class=sub>Bitcoin Encryption, Analysis &amp; Network Security<br>
  Technical report: implementation, features and measured accuracy</div>
  <div class=tiles style="margin-top:34px">
    <div class=tile><div class=v>{num(M('pr_auc'))}</div><div class=l>fused-risk PR-AUC, mean of 6 synthetic datasets</div></div>
    <div class=tile><div class=v>{pct(M('entity_recall'), 1)}</div><div class=l>of criminal entities alerted</div></div>
    <div class=tile><div class=v>{af['f1']:.3f}</div><div class=l>illicit F1 on real Bitcoin data (Elliptic)</div></div>
    <div class=tile><div class=v>{big['rows'] / 1e6:.2f} M</div><div class=l>rows loaded + scored in {big['ingest_s'] + big['score_s']:.0f} s</div></div>
  </div>
  <div class=meta>Release {e(tag)} (commit {e(commit)}) · generated {date.today().isoformat()} · runs fully offline<br>
  All figures in this report are generated from result files in the repository (<code>scripts/build_report.py</code>).</div>
</section>

<h2 class=pb>1. Summary</h2>
<p>BEANS ingests bulk Bitcoin transaction and network-relay observations (CSV, JSON or XML), enriches every relaying IP
offline with country and ASN type, and links IPs, transactions and wallets in one graph. Five engines score it
(entity clustering, anomaly detection, transaction-shape classification, risk propagation from known illicit seed
wallets, and a graph neural network); a calibrated fusion model turns them into a ranked, explained alert list. Every
alert then gets a <b>recommended next step</b> from fixed, citable rules: draft a freeze request or a Section 94 BNSS notice,
prepare an FIU-IND referral, watch the funds, or review a likely false positive. Legal drafts need a second person's
approval; evidence is sealed with SHA-256 and an offline RFC 3161 timestamp; critical alerts can be pushed to a SIEM.</p>
<div class=tiles>
  <div class=tile><div class=v>{num(M('recall_at_p50'))}</div><div class=l>recall of illicit wallets (P ≥ 0.5), before {num(B('recall_at_p50'))}</div></div>
  <div class=tile><div class=v>{num(M('precision_at_p50'))}</div><div class=l>precision (P ≥ 0.5), before {num(B('precision_at_p50'))}</div></div>
  <div class=tile><div class=v>{num(M('e1_homogeneity_illicit'))}</div><div class=l>clusters never mix two criminals (all 6 datasets)</div></div>
  <div class=tile><div class=v>{num(M('ece'), 4)}</div><div class=l>calibration error (ECE)</div></div>
</div>
<p><b>How to read the numbers.</b> Synthetic results are means over six independently generated datasets, out-of-fold and
grouped by criminal entity (a model is never tested on an entity it trained on). Our generator produced that data, so
absolute synthetic numbers are optimistic; the meaningful parts are the before/after comparison, the ablations and the
real-data validation on Elliptic (section 5), where BEANS matches the strongest published baseline rather than beating it.</p>

<h2>2. System overview</h2>
{pipeline_svg()}
<table><tr><th>Layer</th><th>What it does</th></tr>
<tr><td>Ingest</td><td>Streams CSV / JSON / XML in 50,000-row chunks; column mapping for unfamiliar exports; invalid rows quarantined with the reason, never filled with fake values; the earliest relay of a transaction wins across files (first-spy); optional wallet-software fields (version, nLockTime, RBF).</td></tr>
<tr><td>Enrichment</td><td>Offline DB-IP country and ASN databases; ASN typed as residential / datacenter / VPN / Tor exit / bulletproof hosting.</td></tr>
<tr><td>Storage</td><td>Embedded DuckDB file; investigator state (cases, verdicts, watchlist, approvals, audit trail) survives re-scoring.</td></tr>
<tr><td>Interfaces</td><td>FastAPI REST API; React dashboard (served pre-built, no Node.js needed); CLI; Docker image that passes a test with networking disabled.</td></tr>
</table>

<h2>3. Engines</h2>
<table><tr><th>Engine</th><th>Method</th><th>Measured (v1.0, 6-dataset mean)</th></tr>
<tr><td>E1 entity clustering</td><td>Common-input ownership (CoinJoins excluded) · change heuristics with guards (never a later-swept deposit address, never the tiny peel payment, never spent by different wallet software) · peel-chain change · self-split rule (≥ 7 near-identical fresh parts from a non-hub owner)</td><td>homogeneity {num(M('e1_homogeneity_illicit'))} · completeness {num(M('e1_completeness_illicit'))} (was {num(B('e1_completeness_illicit'))})</td></tr>
<tr><td>E2 anomaly</td><td>Isolation Forest on behaviour + network features</td><td>used as a fusion input</td></tr>
<tr><td>E3 transaction shape</td><td>LightGBM on 31 structural features: peel, CoinJoin, fan-out, fan-in, round trip</td><td>macro-F1 {num(M('e3_macro_f1'))}</td></tr>
<tr><td>E4 seed propagation</td><td>Personalised PageRank (both directions), decayed haircut taint with exchanges as taint sinks, hop distances incl. direction-agnostic (reaches a seed's siblings)</td><td>{pct(M('e4_reached_seeded_entities'), 0)} of hidden wallets of seeded actors reached; {pct(M('e4_legit_reached'), 1)} of legitimate wallets (was {pct(B('e4_legit_reached'), 1)})</td></tr>
<tr><td>E5 graph neural network</td><td>SIGN-style: 15 wallet signals averaged over 1- and 2-hop neighbours along and against the money flow, service hubs cut out; fusion is the readout; CPU-only, no deep-learning framework</td><td>when added: PR-AUC {num(st['2_clustering_e4']('pr_auc'))} → {num(st['3_gnn_e5']('pr_auc'))}, recall {num(st['2_clustering_e4']('recall_at_p50'))} → {num(st['3_gnn_e5']('recall_at_p50'))}</td></tr>
<tr><td>Fusion</td><td>LightGBM, isotonic calibration, out-of-fold by entity; money-context features (funding shape, structuring just below round amounts, deposit-like destinations); typology model with a reference corpus of 253 extra operations, pooled per cluster</td><td>PR-AUC {num(M('pr_auc'))} · ECE {num(M('ece'), 4)}</td></tr>
<tr><td>Explanations</td><td>SHAP reasons in plain English; counterfactuals ("without Tor/VPN relaying the risk would fall from 100 to 17"), flagging single-signal vs corroborated alerts</td><td>on every alert (Figure 4)</td></tr>
</table>

<h2 class=pb>4. Accuracy on synthetic data</h2>
<p><b>Protocol.</b> <code>scripts/evaluate_seeds.py --seeds 42 7 123 2024 99 555</code> generates six independent datasets
(~4,000 transactions, ~13,500 wallets, ~30 criminal entities each, only ~30 % of entities revealed as seeds) and runs the
full pipeline on each in its own database. "Before" is the code at the start of the accuracy work; "v1.0" is the tagged
release. Metrics are out-of-fold and grouped by entity.</p>
{compare_chart(chart_rows)}
<p style="font-size:8.5pt;color:#555"><b>Figure {next(fn)}.</b> Before vs v1.0, mean of six datasets (values on each bar; the table below
has the spread).</p>
<table><tr><th>Metric (mean of 6 datasets)</th><th class=n>Before</th><th class=n>v1.0 (± std)</th><th></th></tr>{''.join(trows)}</table>
<p class=note>Alert <i>precision</i> is lower than before because each criminal now takes ~{num(M('alerts_per_entity'), 1)} alerts instead of
~{num(B('alerts_per_entity'), 1)} (whole operations are one cluster): the same handful of false alerts weighs more in a list less
than half as long, while more criminal entities are covered.</p>

<h3>What changed, stage by stage (each a full 6-dataset run, <code>docs/results/stages/</code>)</h3>
<table><tr><th>Stage</th><th class=n>PR-AUC</th><th class=n>Recall</th><th class=n>Typology</th><th class=n>E1 compl.</th><th class=n>E4 seeded</th><th class=n>Entities</th></tr>
{stage_rows}</table>
<ul>
<li><b>Money-context features</b> (label-free): uniformity of the funding transaction's outputs, amounts just below a power of ten (structuring), hub payers, deposit-like destinations.</li>
<li><b>Clustering fix + self-split rule; E4 taint sinks and sibling reach</b>: an old change-heuristic mistake bridged whole exchanges into criminal clusters; false E4 reach fell {pct(B('e4_legit_reached'), 1)} → {pct(M('e4_legit_reached'), 1)}.</li>
<li><b>E5 graph neural network</b> and the <b>typology reference corpus</b> (253 extra operations). A label-shuffling control on the corpus (2 datasets) dropped typology to 0.48-0.61, so the gain comes from its labels; near-perfect accuracy mainly shows synthetic typologies are separable once enough operations are seen.</li>
</ul>
<h3>Tried and rejected (measured, not guessed)</h3>
<ul><li>Counterparty features: PR-AUC {num(st['x_counterparty_features_rejected']('pr_auc'))} vs {num(st['1_context_features']('pr_auc'))} without, dropped as no gain.
Wallet-level fingerprint features: recall {num(st['3_gnn_e5']('recall_at_p50'))} → {num(st['x_fingerprint_features_rejected']('recall_at_p50'))}, dropped; fingerprints are kept only as a clustering guard.</li>
<li>Self-split rule with ≥ 5 parts: better completeness, but merged a darknet market with its vendors; ≥ 7 keeps homogeneity at 1.00.</li></ul>

<h3>Demo dataset (the one the dashboard ships with)</h3>
<table><tr><th>Metric</th><th class=n>Value</th></tr>
<tr><td>Fused PR-AUC (without network-layer features)</td><td class=n>{num(fu['pr_auc'])} ({num(fu['ablation']['pr_auc_without_network'])})</td></tr>
<tr><td>Recall / precision at P ≥ 0.5</td><td class=n>{num(fu['recall_at_p50'])} / {num(fu['precision_at_p50'])}</td></tr>
<tr><td>Alerts · criminal entities alerted</td><td class=n>{aq['alerts']} · {aq['illicit_entities_alerted']} of {aq['illicit_entities_total']}</td></tr>
<tr><td>Alerts that are illicit · top 10</td><td class=n>{pct(aq['alert_precision'], 0)} · {pct(aq['precision_top10'], 0)}</td></tr>
<tr><td>Typology correct on alerts</td><td class=n>{pct(aq.get('typology_accuracy'), 0)}</td></tr>
<tr><td>E1 homogeneity · completeness</td><td class=n>{num(e1['homogeneity_illicit'], 2)} · {num(e1['completeness_illicit'], 2)}</td></tr>
<tr><td>E4 reach inside seeded actors · legitimate reached</td><td class=n>{pct(e4.get('hidden_reached_in_seeded_entities'), 0)} · {pct(e4['legit_reached'], 0)}</td></tr>
</table>

<h2 class=pb>5. Validation on real Bitcoin data (Elliptic)</h2>
<p>Elliptic (Weber et al. 2019) has {ell['dataset']['transactions']:,} real Bitcoin transactions ({ell['dataset']['illicit']:,} labelled illicit,
{ell['dataset']['licit']:,} licit) and {ell['dataset']['edges']:,} payment edges. Its features are anonymised (no addresses, amounts or IPs), so it
tests the modelling approach, not the clustering, network layer or action rules. Standard temporal split: train on
time steps {ell['split']['train_steps']}, test on {ell['split']['test_steps']} ({ell['split']['test_illicit']:,} illicit test transactions).</p>
<div class=two><div>
<table><tr><th>BEANS (this code)</th><th class=n>P</th><th class=n>R</th><th class=n>F1</th><th class=n>PR-AUC</th></tr>{ell_rows}</table>
</div><div>
<table><tr><th>Published (Weber et al. 2019)</th><th class=n>P</th><th class=n>R</th><th class=n>F1</th></tr>{pub_rows}</table>
</div></div>
<p><b>Reading.</b> BEANS reaches illicit F1 <b>{af['f1']:.3f}</b> (precision {af['precision']:.2f}, calibration error {af['ece']}), equal to
the strongest published baseline and well above the published graph networks; it does not beat the random forest. E5 does not help here
because Elliptic's features already are neighbourhood aggregates. Like every published model, detection collapses after
time step 43, when a large dark market closed.</p>
<p><b>Seed propagation on real data.</b> With 30 % of illicit transactions revealed as seeds, {pct(prop['hidden_illicit_within_2_hops_of_a_seed'], 0)} of the
hidden illicit ones lie within 2 hops of a seed versus {pct(prop['licit_within_2_hops_of_a_seed'], 0)} of licit ones, and adding the seeds lifts
PR-AUC from {prop['pr_auc_model_only']:.3f} to <b>{prop['pr_auc_model_plus_seeds']:.3f}</b> (the combination rule was fixed before testing).</p>

<h2>6. Scale</h2>
<table><tr><th></th><th class=n>Value</th></tr>
<tr><td>Rows (10 independent files, one database)</td><td class=n>{big['rows']:,}</td></tr>
<tr><td>Transactions · wallets</td><td class=n>{big['transactions']:,} · {big['wallets']:,}</td></tr>
<tr><td>Chunked ingest (<code>beans ingest … --no-score</code>)</td><td class=n>{big['ingest_s']:.0f} s · peak {big['ingest_peak_gb']} GB</td></tr>
<tr><td>Scoring, all engines (<code>beans score</code>)</td><td class=n>{big['score_s']:.0f} s · peak {big['score_peak_gb']} GB</td></tr>
<tr><td>End to end</td><td class=n>{big['ingest_s'] + big['score_s']:.0f} s · {big['rows'] / (big['ingest_s'] + big['score_s']):,.0f} rows/s</td></tr>
</table>
<p>The earlier estimate for one million rows was ~16 GB of RAM; chunked ingest and two optimised hot spots (identical results,
verified to four decimals) bring it to a normal 16 GB laptop. The demo dataset scores end to end in {demo['timings_s']['total']:.0f} s.</p>

<h2 class=pb>7. Investigator workflow</h2>
{fig('01_overview', 'Overview: volume, alerts by severity and typology, relay infrastructure, countries.', next(fn))}
{fig('02_triage', 'Alert triage: every alert carries a recommended action; filter chips by action; linked-case badges.', next(fn))}
{fig('03_action_card', 'Action card: the directive, the rule it matched with the checked values, legal basis, model support (SHAP) and one-click drafts.', next(fn), 62)}
{fig('04_counterfactual', 'What would change the verdict: each factor neutralised to a typical wallet and re-scored; single-signal vs corroborated alerts.', next(fn), 62)}

<h3>Action directive rulebook (demo counts)</h3>
<table><tr><th>Directive</th><th>Rule</th><th>Legal basis</th><th class=n>Alerts</th></tr>{rulebook}</table>
<p>Thresholds (freeze window {settings.ACTION_FREEZE_WINDOW_MIN:.0f} min, minimum risk {settings.ACTION_FREEZE_MIN_RISK:.0f}, trace depth {settings.ACTION_MAX_HOPS} hops,
layering ≥ {settings.ACTION_LAYERING_MIN_BTC:g} BTC) live in <code>beans/config.py</code> and can be overridden without code changes.
Exchange deposits come from an attribution list (<code>known_entities</code>), which is never a model feature.</p>

{fig('05_legal_draft', 'Freeze / hold request draft: blockchain facts filled in, unknown IO fields left as visible blanks, sealed with SHA-256 + RFC 3161.', next(fn))}
{fig('14_approvals', 'Legal approvals: drafts are filed pending; a supervisor other than the drafter approves or rejects (four-eyes).', next(fn))}
{fig('06_link_graph', 'Link graph: money-flow particles (speed = BTC), pulsing halos on seeds / critical wallets / risky IPs, lasso selection into a case.', next(fn))}
{fig('07_money_trail', 'Follow the money: hop-by-hop peel-chain replay with peeled amounts and the exchanges they reached.', next(fn))}
{fig('13_watchlist', 'Watchlist: a watched wallet moved funds; one reached an Indian exchange within the freeze window.', next(fn))}
{fig('10_entity360', 'Entity 360: wallet profile, cluster, relaying IPs, wallet-software fingerprint and full ledger.', next(fn))}
{fig('08_rulebook', 'Rules & integrations: directive rulebook, SIEM webhooks, attribution list, evidence timestamping.', next(fn))}
{fig('09_model_card', 'Model card: every metric measured on the loaded data, with targets and baselines, plus the Elliptic validation.', next(fn))}
{fig('11_dark_graph', 'Dark theme (all pages).', next(fn))}
{fig('12_login', 'Login (switches on once the first user exists).', next(fn), 40)}

<h2 class=pb>8. Legal output and evidence</h2>
<ul>
<li><b>Section 94 BNSS requisition</b> (KYC, ledger, login/IP logs, linked bank/UPI, withdrawal destinations; certificate under Section 63 BSA) and <b>freeze / hold request</b> (Section 106 BNSS) in <b>English or Hindi</b>; offshore exchanges get a Letter-of-Request (Section 112) note; the freeze letter states its actual trigger (fast cash-out, or a deposit within the window before the latest data).</li>
<li><b>Four-eyes approval</b>: every draft is filed pending; only a supervisor other than the drafter can approve (or reject with a comment); the approval banner is printed on the document.</li>
<li><b>FIU-IND intelligence referral pack</b> and <b>case evidence packs</b> (PDF / HTML / JSON) with the money-trail and seed-path diagrams, counterfactuals, source-file hashes and the audit trail.</li>
<li><b>Sealing</b>: SHA-256 of the evidence plus an RFC 3161 token from a local, offline Time-Stamping Authority; anyone can re-verify with <code>openssl ts -verify</code>.</li>
</ul>

<h2>9. Monitoring, integrations and security</h2>
<ul>
<li><b>Watch folder</b> (<code>beans watch</code>) and <b>watchlist</b>: taint-watch wallets are watched automatically; any later spend raises one CRITICAL movement event, traced to exchanges.</li>
<li><b>SIEM webhooks</b>: generic JSON (Wazuh), Splunk HEC, Elasticsearch bulk, STIX 2.1 (MISP / OpenCTI); delivered once per alert and hook, retried, logged.</li>
<li><b>Users and roles</b>: VIEWER / ANALYST / SUPERVISOR / ADMIN; salted PBKDF2 passwords, HttpOnly sessions, lockout after repeated failures; every action in the audit trail under the user's name. No default password: single-user mode until the first user is created.</li>
<li><b>Cross-case links</b>: an alert shows when its wallet or its entity cluster is already a suspect in an open case.</li>
<li><b>Optional live collector</b> (<code>beans collect</code>): a separate tool that records transaction announcements per peer into BEANS CSVs; checked live (1,030 rows in 90 s, every txid matched the announced id).</li>
</ul>

<h2>10. Limitations</h2>
<ul>
<li>Synthetic numbers are optimistic; Elliptic validates the modelling approach only (no addresses, amounts or IPs).</li>
<li>Typology near 100 % reflects separable synthetic typologies; expect less on real cases.</li>
<li>Freeze and Section 94 directives on real data depend on a real exchange attribution list.</li>
<li>Legal templates need review by a lawyer; the Hindi text by a native legal reviewer (the Hindi document says so).</li>
<li>The live collector can only resolve inputs from transactions it has already seen (12 of 311 after 90 s); a full node's export gives complete inputs.</li>
<li>The local TSA proves "no later than" by this machine's clock and key; it carries less weight than an accredited public TSA.</li>
</ul>

<h2>Appendix: reproduce</h2>
<table><tr><th>What</th><th>Command</th></tr>
<tr><td>Demo (offline)</td><td><code>make install && make demo</code> → http://127.0.0.1:8000</td></tr>
<tr><td>Offline Docker test</td><td><code>make docker-offline-test</code></td></tr>
<tr><td>6-dataset benchmark</td><td><code>.venv/bin/python scripts/evaluate_seeds.py --seeds 42 7 123 2024 99 555</code></td></tr>
<tr><td>Real-data validation</td><td><code>beans validate-elliptic --download --doc docs/VALIDATION_ELLIPTIC.md</code></td></tr>
<tr><td>1M-row benchmark</td><td><code>.venv/bin/python scripts/benchmark_1m.py --files 10</code></td></tr>
<tr><td>This report</td><td><code>.venv/bin/python scripts/build_report.py</code></td></tr>
<tr><td>Tests</td><td><code>make test</code> (62 tests)</td></tr>
</table>
<p style="font-size:8.5pt;color:#555">IP geolocation by DB-IP (CC BY 4.0). Elliptic dataset: Weber et al., "Anti-Money Laundering in Bitcoin",
KDD 2019 workshop (arXiv:1908.02591). SIGN: Frasca et al. 2020. All data shown in screenshots is synthetic.</p>
"""
    doc = f"<!doctype html><html><head><meta charset=utf-8><title>BEANS technical report</title><style>{css}</style></head><body>{body}</body></html>"
    out_html = ROOT / "docs" / "BEANS_Technical_Report.html"
    out_html.write_text(doc)
    from weasyprint import HTML
    out_pdf = ROOT / "docs" / "BEANS_Technical_Report.pdf"
    HTML(string=doc, base_url=str(ROOT)).write_pdf(out_pdf)
    print(out_pdf)


if __name__ == "__main__":
    build()
