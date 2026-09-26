"""Push alerts to SIEM / threat-intel webhooks after every scoring run.

Formats:
  json        generic JSON (Wazuh integrations, n8n, custom collectors): {"source": "beans", "alerts": [...]}
  splunk_hec  Splunk HTTP Event Collector: one {"event": …, "sourcetype": "beans:alert"} per alert,
              newline-joined, header `Authorization: Splunk <token>`
  elastic     Elasticsearch _bulk NDJSON (URL = https://es:9200/<index>/_bulk), header `Authorization: ApiKey <token>`
  stix        STIX 2.1 bundle (MISP `/events/upload_stix/2`, OpenCTI), header `Authorization: <token>`

Only alerts at or above the hook's `min_severity` (plus movement events of watched wallets, always CRITICAL)
that were not delivered to that hook before are sent, so
re-scoring never floods the SIEM with duplicates. Every attempt is written to `webhook_log`. Delivery runs
in a background thread with 3 attempts (1 s, 3 s back-off) and never breaks the scoring pipeline.
The whole tool is offline: webhooks point at SIEMs on the local / agency network.
"""
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from beans.export import stix_bundle

log = logging.getLogger("beans.webhooks")

FORMATS = {"json", "splunk_hec", "elastic", "stix"}
SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
RETRIES = (1.0, 3.0)
TIMEOUT_S = 5
_lock = threading.Lock()

ALERT_COLS = ("alert_id", "entity_id", "entity_type", "alert_type", "risk_score", "calibrated_confidence", "severity",
              "reasons", "engine_scores", "evidence", "recommended_action", "status", "created_at")


def _alert_dict(row) -> Dict[str, Any]:
    a = dict(zip(ALERT_COLS, row))
    for k in ("engine_scores", "evidence", "recommended_action"):
        if isinstance(a[k], str):
            try:
                a[k] = json.loads(a[k])
            except ValueError:
                pass
    a["reasons"] = list(a["reasons"] or [])
    a["created_at"] = str(a["created_at"])
    return a


def _summary(a: Dict[str, Any]) -> Dict[str, Any]:
    ev, ra = a.get("evidence") or {}, a.get("recommended_action") or {}
    return {"alert_id": a["alert_id"], "wallet": a["entity_id"], "typology": a["alert_type"].replace("_PATTERN", ""),
            "severity": a["severity"], "risk_score": a["risk_score"], "confidence": a["calibrated_confidence"],
            "reasons": a["reasons"], "recommended_action": ra.get("action"), "action_rule": ra.get("rule"),
            "first_relay_ip": ev.get("first_spy_ip"), "first_relay_asn_type": ev.get("first_spy_asn_type"),
            "key_txid": ev.get("txid"), "cluster_id": ev.get("cluster_id"), "created_at": a.get("created_at")}


def build_request(hook: Dict[str, Any], alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """HTTP request (headers + body) for one hook and a batch of alerts."""
    fmt, token = hook["fmt"], hook.get("token") or ""
    headers = {"User-Agent": "BEANS-webhook/1.0"}
    now = datetime.now(timezone.utc)
    if fmt == "splunk_hec":
        body = "\n".join(json.dumps({"time": now.timestamp(), "source": "beans", "sourcetype": "beans:alert",
                                     "event": _summary(a)}, default=str) for a in alerts)
        headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Splunk {token}"
    elif fmt == "elastic":
        body = "".join(json.dumps({"index": {"_id": a["alert_id"]}}) + "\n" +
                       json.dumps({"@timestamp": now.isoformat(), "event": {"kind": "alert", "module": "beans"},
                                   **_summary(a)}, default=str) + "\n" for a in alerts)
        headers["Content-Type"] = "application/x-ndjson"
        if token:
            headers["Authorization"] = f"ApiKey {token}"
    elif fmt == "stix":
        body = json.dumps(stix_bundle(alerts), default=str)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        if token:
            headers["Authorization"] = token
    else:
        body = json.dumps({"source": "beans", "sent_at": now.isoformat(), "count": len(alerts),
                           "alerts": [_summary(a) for a in alerts]}, default=str)
        headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return {"url": hook["url"], "headers": headers, "data": body.encode()}


def _post(req: Dict[str, Any], retries=RETRIES) -> tuple:
    """(ok, http_status, attempts, error)."""
    err, status = None, None
    for attempt in range(len(retries) + 1):
        try:
            r = requests.post(req["url"], headers=req["headers"], data=req["data"], timeout=TIMEOUT_S)
            status = r.status_code
            if r.status_code < 300:
                return True, status, attempt + 1, None
            err = f"HTTP {r.status_code}: {r.text[:200]}"
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return False, status, attempt + 1, err    # client error: retrying won't help
        except requests.RequestException as e:
            err = str(e)[:300]
        if attempt < len(retries):
            time.sleep(retries[attempt])
    return False, status, len(retries) + 1, err


def pending(conn, hook: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_rank = SEVERITY_RANK.get(str(hook.get("min_severity") or "CRITICAL").upper(), 3)
    sevs = [s for s, r in SEVERITY_RANK.items() if r >= min_rank]
    rows = conn.execute(f"""SELECT {', '.join(ALERT_COLS)} FROM alerts a
        WHERE list_contains(?, severity) AND NOT EXISTS (
            SELECT 1 FROM webhook_log l WHERE l.webhook_id = ? AND l.alert_id = a.alert_id AND l.status = 'SENT')
        ORDER BY risk_score DESC LIMIT 500""", [sevs, hook["id"]]).fetchall()
    out = [_alert_dict(r) for r in rows]
    from beans.alerting import watch   # movement events of watched wallets are always CRITICAL
    if SEVERITY_RANK[watch.EVENT_SEVERITY] >= min_rank:
        cur = conn.execute("""SELECT * FROM watch_events e WHERE NOT EXISTS (
            SELECT 1 FROM webhook_log l WHERE l.webhook_id = ? AND l.alert_id = e.event_id AND l.status = 'SENT')
            ORDER BY ts""", [hook["id"]])
        cols = [d[0] for d in cur.description]
        out = [watch.as_alert(dict(zip(cols, r))) for r in cur.fetchall()] + out
    return out


def _hooks(conn, only: Optional[int] = None) -> List[Dict[str, Any]]:
    cols = ("id", "name", "url", "fmt", "min_severity", "token", "enabled")
    q = f"SELECT {', '.join(cols)} FROM webhooks WHERE enabled"
    rows = conn.execute(q + (" AND id = ?" if only else ""), [only] if only else []).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def dispatch_pending(store, only: Optional[int] = None) -> List[Dict[str, Any]]:
    """Send undelivered alerts to every enabled hook. Returns one result per hook."""
    with _lock:
        conn = store.get_connection()
        try:
            jobs = [(h, pending(conn, h)) for h in _hooks(conn, only)]
        finally:
            conn.close()
        results = []
        for hook, alerts in jobs:
            if not alerts:
                results.append({"webhook_id": hook["id"], "sent": 0})
                continue
            ok, status, attempts, err = _post(build_request(hook, alerts))
            conn = store.get_connection()
            try:
                conn.executemany("INSERT INTO webhook_log (webhook_id, alert_id, status, http_status, attempts, error) "
                                 "VALUES (?, ?, ?, ?, ?, ?)",
                                 [[hook["id"], a["alert_id"], "SENT" if ok else "FAILED", status, attempts, err] for a in alerts])
            finally:
                conn.close()
            if not ok:
                log.warning("webhook %s (%s) failed: %s", hook["name"], hook["url"], err)
            results.append({"webhook_id": hook["id"], "sent": len(alerts) if ok else 0, "ok": ok, "http_status": status,
                            "error": err})
        return results


def dispatch_in_background(store) -> threading.Thread:
    """Fire-and-forget after scoring. Non-daemon, so a one-shot CLI run still finishes delivering before exit."""
    def run():
        try:
            dispatch_pending(store)
        except Exception as e:  # never let delivery problems surface in the pipeline
            log.warning("webhook dispatch failed: %s", e)
    t = threading.Thread(target=run, name="beans-webhooks", daemon=False)
    t.start()
    return t


def send_test(hook: Dict[str, Any]) -> Dict[str, Any]:
    sample = {"alert_id": "A-TEST", "entity_id": "bc1qtestwallet000000000000000000000000000", "entity_type": "WALLET",
              "alert_type": "TEST_PATTERN", "risk_score": 99.0, "calibrated_confidence": 0.9, "severity": "CRITICAL",
              "reasons": ["BEANS webhook connectivity test"], "engine_scores": {}, "evidence": {},
              "recommended_action": {"action": "ANALYST_REVIEW"}, "status": "OPEN",
              "created_at": datetime.now(timezone.utc).isoformat()}
    ok, status, attempts, err = _post(build_request(hook, [sample]), retries=())
    return {"ok": ok, "http_status": status, "attempts": attempts, "error": err}
