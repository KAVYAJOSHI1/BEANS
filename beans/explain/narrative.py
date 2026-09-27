"""Case narrative: a readable paragraph per alert, written only from facts BEANS already established.

1. `facts(alert)` turns the alert's evidence into a numbered fact sheet [F1] … [Fn]. Every fact is a BEANS finding
   (score, engine result, trace, directive), never a guess.
2. A local model (Ollama on 127.0.0.1, e.g. llama3.2; nothing leaves the machine) writes 3-6 sentences from the fact
   sheet, citing fact ids after every sentence.
3. `check()` keeps a sentence only if it cites existing facts and every number in it appears in the facts it cites,
   and no speculation words ("may have", "probably", ...) are used. Removed sentences are counted and reported.
4. Too little survives, the model is not running, or NARRATIVE_ENGINE=template: the deterministic template narrative
   is used instead. It says the same thing, less fluently, and is always available.

The narrative is a reading aid. The evidence pack, the facts and the rules stay the record.
"""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from beans.config import settings

SPECULATION = re.compile(r"\b(may|might|probabl[ey]|possibl[ey]|likely|appears? to|seems?|suspect(?:ed)? of|attempt(?:ed|ing)? to|"
                         r"potential(?:ly)?|indicat(?:e|es|ing)|suggest(?:s|ing)?|i am|i'm|we believe|clearly|obviously)\b", re.I)
WORD = re.compile(r"[a-z][a-z_]{2,}")
# the same fact is told with different verbs: "sent / reached / moved / deposited to" all mean funds moved
SYNONYMS = {w: "move" for w in ("sent", "send", "reach", "reached", "moved", "move", "went", "transferr", "transfer",
                                "deposit", "deposited", "flow", "flowed", "pass", "passed", "paid", "routed")}
STOP = {"the", "and", "for", "its", "has", "was", "are", "out", "one", "all", "per", "via", "had", "not", "who",
        "this", "that", "with", "from", "into", "have", "been", "were", "which", "their", "there", "these", "those",
        "wallet", "wallets", "further", "analysis", "revealed", "shows", "show", "also", "then", "than", "while", "where",
        "about", "after", "before", "because", "being", "case", "flagged", "identifier", "addition", "additionally",
        "furthermore", "however", "investigators", "investigator", "based", "total", "used", "using", "made", "each",
        "due", "level", "closely", "very", "high", "its", "it", "owner", "resembling", "resembles", "similar", "like"}
MIN_OVERLAP = 0.6   # share of a sentence's content words that must occur in the facts it cites
CITE = re.compile(r"\[F(\d+)\]")
NUM = re.compile(r"\d+(?:[.,]\d+)*")
MIN_SENTENCES = 2


def _short(a: Optional[str], n: int = 12) -> str:
    return f"{a[:n]}…" if a and len(a) > n + 3 else (a or "?")


def facts(alert: Dict[str, Any]) -> List[str]:
    """The fact sheet, in reading order. Addresses are shortened; amounts and counts are kept exactly."""
    ev, es, ra = alert.get("evidence") or {}, alert.get("engine_scores") or {}, alert.get("recommended_action") or {}
    typ = str(alert.get("alert_type") or "").replace("_PATTERN", "").replace("_", " ").lower()
    out = [f"Wallet {_short(alert['entity_id'])} has risk {alert.get('risk_score'):g} of 100 ({alert.get('severity')}), "
           f"with its behaviour closest to the {typ} typology."]
    for r in (alert.get("reasons") or [])[:4]:
        out.append(f"Model reason: {r}.")
    if (ev.get("cluster_size") or 1) > 1:
        out.append(f"The wallet belongs to an entity cluster of {ev['cluster_size']} addresses controlled by one owner.")
    chain = ev.get("peel_chain") or []
    if len(chain) >= 3:
        out.append(f"The funds pass through a peel chain of {len(chain)} transactions.")
    path = ev.get("path_to_seed") or []
    if len(path) >= 2:
        out.append(f"The wallet is {len(path) - 1} hops from a known illicit seed wallet.")
    if (es.get("e4_taint") or 0) >= 0.01:
        out.append(f"{100 * es['e4_taint']:.0f} % of its funds trace back to seed wallets (taint).")
    if ev.get("first_spy_ip"):
        conf = ev.get("first_spy_confidence")
        out.append(f"Its key transaction was first relayed by IP {ev['first_spy_ip']} ({ev.get('first_spy_asn_type') or 'unknown'} "
                   f"network{'' if conf is None else f', attribution confidence {conf:g}'}); a first relay can be a VPN or Tor exit, not the owner.")
    if (es.get("network_risky_share") or 0) > 0:
        out.append(f"{100 * es['network_risky_share']:.0f} % of its spends were broadcast through Tor, VPN or bulletproof hosting.")
    for h in (ra.get("vasp_exposure") or [])[:2]:
        when = "" if h.get("minutes_after_receipt") is None else f", {h['minutes_after_receipt']:g} minutes after receipt"
        out.append(f"{h['amount_btc']:g} BTC reached exchange {h['vasp']} ({h.get('country')}) in {h['hops']} hop(s){when}.")
    for h in (ra.get("cross_chain_exits") or [])[:1]:
        out.append(f"{h['amount_btc']:g} BTC went to swap service {h['vasp']} in {h['hops']} hop(s), where the funds leave Bitcoin.")
    if ra.get("action"):
        out.append(f"Recommended action: {ra.get('title')}. Rule: {ra.get('rule')}.")
    cf = ev.get("counterfactual") or {}
    if cf.get("summary"):
        out.append(f"What decides the alert: {cf['summary']}")
    for c in (alert.get("linked_cases") or [])[:2]:
        out.append(f"The wallet is linked to open case #{c.get('case_id', c.get('id'))} ({c.get('case_name', '')}).")
    return out


def _stem(w: str) -> str:
    w = w.replace("behavior", "behaviour")   # US / UK spelling
    if w in SYNONYMS:
        return SYNONYMS[w]
    for suf in ("ings", "ing", "ied", "ies", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return SYNONYMS.get(w[: -len(suf)], w[: -len(suf)])
    return w


def _content(text: str) -> set:
    return {_stem(w) for w in WORD.findall(text.lower()) if w not in STOP}


def _numbers(text: str) -> set:
    return {n.replace(",", "") .rstrip(".") for n in NUM.findall(text)}


def check(text: str, sheet: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    """Split into sentences; keep those that cite real facts, use only numbers from them and do not speculate."""
    kept, dropped = [], 0
    for s in re.split(r"(?<=[.!?\]])\s+(?=[A-Z0-9])", text.strip()):
        s = s.strip()
        if not s:
            continue
        ids = [int(i) for i in CITE.findall(s)]
        body = CITE.sub("", s).strip()
        ok = bool(ids) and all(1 <= i <= len(sheet) for i in ids) and not SPECULATION.search(body)
        if ok:
            cited = " ".join(sheet[i - 1] for i in ids)
            words = _content(body)
            ok = _numbers(body) <= _numbers(cited) and (not words or len(words & _content(cited)) / len(words) >= MIN_OVERLAP)
        if ok:
            body = re.sub(r"\s+([.,;:])", r"\1", body).rstrip(" ,")
            kept.append({"text": body if body.endswith((".", "!", "?")) else body + ".", "facts": sorted(set(ids))})
        else:
            dropped += 1
    return kept, dropped


def template(sheet: List[str]) -> List[Dict[str, Any]]:
    """Deterministic narrative: the fact sheet itself, as sentences with their citations."""
    return [{"text": f, "facts": [i]} for i, f in enumerate(sheet, 1)]


def _prompt(sheet: List[str]) -> str:
    numbered = "\n".join(f"[F{i}] {f}" for i, f in enumerate(sheet, 1))
    return ("You write case summaries for police investigators. Use ONLY the facts below.\n"
            f"{numbered}\n\n"
            "Write 3 to 6 plain sentences in the third person that summarise the case in a sensible order: who, what "
            "happened to the money, where it went, and the recommended action. After EVERY sentence write the ids of the "
            "facts it uses, e.g. [F2][F5]. Copy numbers exactly; never add a number, name or claim that is not in the "
            "facts. Do not speculate about intent (no 'may have', 'probably', 'likely'). Do not connect two facts with "
            "'because', 'due to', 'then' or 'before' unless one fact says so: facts that sit next to each other are not "
            "a sequence of events. No heading, no bullet points.")


def _ollama(prompt: str) -> str:
    body = json.dumps({"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0, "seed": 42, "num_predict": 400}}).encode()
    req = urllib.request.Request(settings.OLLAMA_URL.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=settings.NARRATIVE_TIMEOUT_S) as r:
        return json.loads(r.read())["response"]


def generate(alert: Dict[str, Any], engine: str = "auto", llm=None) -> Dict[str, Any]:
    """engine: auto (model, falling back to the template) | template. `llm(prompt) -> text` overrides Ollama (tests)."""
    sheet = facts(alert)
    result = {"alert_id": alert["alert_id"], "facts": [{"id": f"F{i}", "text": f} for i, f in enumerate(sheet, 1)],
              "facts_sha256": hashlib.sha256(json.dumps(sheet).encode()).hexdigest(),
              "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), "dropped_sentences": 0}
    note = None
    if engine != "template" and settings.NARRATIVE_ENGINE != "template":
        try:
            kept, dropped = check((llm or _ollama)(_prompt(sheet)), sheet)
            if len(kept) >= MIN_SENTENCES:
                return {**result, "engine": f"{settings.OLLAMA_MODEL} (local, via Ollama)" if llm is None else "test model",
                        "sentences": kept, "dropped_sentences": dropped}
            note = f"the model's text failed the fact check ({dropped} sentence(s) removed); template used"
        except Exception as e:   # Ollama not running / model missing / timeout
            note = f"local model unavailable ({type(e).__name__}); template used"
    return {**result, "engine": "template", "note": note, "sentences": template(sheet)}
