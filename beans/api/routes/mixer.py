"""Mixer traversal (E6): who a CoinJoin's outputs could belong to, with link probabilities."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from beans.api import db

router = APIRouter(prefix="/mixer", tags=["Mixer traversal"])


@router.get("/transactions")
def mixing_transactions(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    """Traversed mixing transactions, most informative first: certain change links, then the smallest anonymity set."""
    if not db.table_exists("mixer_links"):
        return {"transactions": []}
    rows = db.query("""
        SELECT m.txid, any_value(t.timestamp) AS timestamp, any_value(t.total_output) AS total_btc,
               COUNT(DISTINCT m.src) FILTER (WHERE m.kind = 'POOL') AS anonymity_set,
               COUNT(*) FILTER (WHERE m.kind = 'CHANGE' AND m.prob >= 0.99) AS certain_change,
               COUNT(*) FILTER (WHERE m.kind = 'CHANGE') AS change_links,
               COUNT(DISTINCT m.src) AS participants
        FROM mixer_links m LEFT JOIN transactions t ON t.txid = m.txid GROUP BY m.txid
        ORDER BY certain_change DESC, anonymity_set ASC, timestamp DESC LIMIT ?""", [limit])
    if rows and db.table_exists("wallet_scores"):
        tainted = {r["txid"]: r["n"] for r in db.query(
            """SELECT m.txid, COUNT(DISTINCT m.src) AS n FROM mixer_links m JOIN wallet_scores w ON w.address = m.src
               WHERE w.taint > 0.01 AND list_contains(?, m.txid) GROUP BY m.txid""", [[r["txid"] for r in rows]])}
        for r in rows:
            r["tainted_inputs"] = tainted.get(r["txid"], 0)
    return {"transactions": rows}


@router.get("/{txid}")
def mixer_links(txid: str) -> Dict[str, Any]:
    """Input → output link probabilities of one mixing transaction (empty when it was not traversed)."""
    txid = txid.lower()
    if not db.table_exists("mixer_links"):
        raise HTTPException(404, "no mixer analysis yet: run scoring first")
    rows = db.query("SELECT src, dst, prob, kind, amount FROM mixer_links WHERE txid = ? ORDER BY prob DESC, src, dst",
                    [txid])
    if not rows:
        raise HTTPException(404, f"{txid} is not a traversed mixing transaction")
    taint = {r["address"]: r["taint"] for r in db.query(
        "SELECT address, taint FROM wallet_scores WHERE list_contains(?, address)",
        [sorted({r["src"] for r in rows} | {r["dst"] for r in rows})])} if db.table_exists("wallet_scores") else {}
    pool = [r for r in rows if r["kind"] == "POOL"]
    return {"txid": txid, "anonymity_set": len({r["src"] for r in pool}) or None,
            "links": [{**r, "src_taint": taint.get(r["src"], 0.0), "dst_taint": taint.get(r["dst"], 0.0)} for r in rows],
            "note": "POOL links (equal outputs) are 1/k by construction; CHANGE links come from amount matching"}


@router.get("")
def mixer_summary() -> Dict[str, Any]:
    if not db.table_exists("mixer_links"):
        return {"mixing_transactions": 0, "links": 0}
    r = db.query("SELECT COUNT(DISTINCT txid) AS txs, COUNT(*) AS links, "
                 "COUNT(*) FILTER (WHERE kind = 'CHANGE' AND prob >= 0.99) AS certain_change FROM mixer_links")[0]
    return {"mixing_transactions": r["txs"], "links": r["links"], "certain_change_links": r["certain_change"]}
