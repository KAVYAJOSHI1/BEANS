"""Optional input resolvers for the live collector: amounts and addresses of already-confirmed coins.

The P2P stream only describes a spent coin when the collector saw the transaction that created it. Coins created in
earlier blocks (most ordinary payments) need a lookup. Two sources, both standard-library only:

  * BitcoindResolver: your own Bitcoin Core node over JSON-RPC, `gettxout` in batches. Works on a pruned node without
    -txindex, because a coin being spent from the mempool is still unspent in the chainstate. Nothing leaves your
    network. This is the recommended source.
  * EsploraResolver: an Esplora HTTP API (self-hosted electrs / mempool, or a public instance such as
    https://mempool.space/api). A public instance learns which transactions you look up, so use your own for casework.

A resolver takes [(txid, vout), ...] and returns {(txid, vout): (address, value_sat)} for what it found. Lookups that
fail are left out, so those inputs stay unresolved in the CSV rather than being guessed.
"""
import base64
import json
import urllib.parse
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from typing import Dict, List, Optional, Tuple

Outpoint = Tuple[str, int]


class BitcoindResolver:
    def __init__(self, url: str, batch: int = 500, timeout: float = 30.0):
        """url: http://user:password@host:8332 (credentials may also come from the cookie file's user:password)."""
        u = urllib.parse.urlsplit(url)
        self.endpoint = urllib.parse.urlunsplit((u.scheme, f"{u.hostname}:{u.port or 8332}", u.path or "/", "", ""))
        self.auth = base64.b64encode(f"{urllib.parse.unquote(u.username or '')}:{urllib.parse.unquote(u.password or '')}"
                                     .encode()).decode() if u.username else None
        self.batch, self.timeout = batch, timeout

    def _call(self, payload: list) -> list:
        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        if self.auth:
            req.add_header("Authorization", f"Basic {self.auth}")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def __call__(self, outpoints: List[Outpoint]) -> Dict[Outpoint, Tuple[str, int]]:
        found = {}
        for i in range(0, len(outpoints), self.batch):
            chunk = outpoints[i:i + self.batch]
            reply = self._call([{"jsonrpc": "1.0", "id": j, "method": "gettxout", "params": [t, v, False]}
                                for j, (t, v) in enumerate(chunk)])
            for r in reply:
                res = r.get("result")
                if not res:
                    continue
                spk = res.get("scriptPubKey") or {}
                addr = spk.get("address") or (spk.get("addresses") or [None])[0]
                if addr:
                    found[chunk[r["id"]]] = (addr, int(round(float(res["value"]) * 1e8)))
        return found


class EsploraResolver:
    def __init__(self, base_url: str, workers: int = 8, max_lookups: Optional[int] = 2000, timeout: float = 10.0,
                 budget_s: float = 60.0, give_up_after: int = 16):
        """base_url: e.g. http://127.0.0.1:3000 (electrs) or https://mempool.space/api. `max_lookups` caps the
        transactions fetched per call so a public instance is not hammered (None = no cap). One call never takes
        longer than `budget_s`, and stops early when its first `give_up_after` lookups all fail (server unreachable
        or rate-limiting): the collector must keep writing files whatever the resolver does."""
        self.base = base_url.rstrip("/")
        self.workers, self.max_lookups, self.timeout = workers, max_lookups, timeout
        self.budget_s, self.give_up_after = budget_s, give_up_after

    def _tx_outputs(self, txid: str) -> Optional[list]:
        req = urllib.request.Request(f"{self.base}/tx/{txid}", headers={"User-Agent": "beans-collector/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read()).get("vout") or []
        except (OSError, ValueError):
            return None

    def __call__(self, outpoints: List[Outpoint]) -> Dict[Outpoint, Tuple[str, int]]:
        txids = list(dict.fromkeys(t for t, _ in outpoints))
        if self.max_lookups is not None:
            txids = txids[:self.max_lookups]
        vouts, failed, deadline = {}, 0, time.monotonic() + self.budget_s
        pool = ThreadPoolExecutor(self.workers)
        futures = {pool.submit(self._tx_outputs, t): t for t in txids}
        try:
            for f in as_completed(futures, timeout=self.budget_s):
                res = f.result()
                if res is None:
                    failed += 1
                    if not vouts and failed >= self.give_up_after:
                        break
                else:
                    vouts[futures[f]] = res
                if time.monotonic() > deadline:
                    break
        except FuturesTimeout:
            pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        found = {}
        for t, v in outpoints:
            outs = vouts.get(t)
            if outs and v < len(outs) and outs[v].get("scriptpubkey_address"):
                found[(t, v)] = (outs[v]["scriptpubkey_address"], int(outs[v]["value"]))
        return found


def from_args(rpc: Optional[str], esplora: Optional[str], max_lookups: Optional[int] = 2000):
    if rpc and esplora:
        raise ValueError("give either --rpc or --esplora, not both")
    if rpc:
        return BitcoindResolver(rpc)
    if esplora:
        return EsploraResolver(esplora, max_lookups=max_lookups)
    return None
