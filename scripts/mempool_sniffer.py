#!/usr/bin/env python3
"""Standalone live mempool sniffer for a separate, connected machine (the BEANS analysis box stays offline).

Same collector as `beans collect` (beans/collector/p2p.py), with no ML, database or API imports, so it can be
copied with just the `beans/collector` package. It writes rotated CSVs; carry them to the analysis machine or point
`beans watch` at the folder.

    python scripts/mempool_sniffer.py --dns-seed --out data/inbox --minutes 30
    python scripts/mempool_sniffer.py --peer 203.0.113.5:8333 --peer 198.51.100.7
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from beans.collector.p2p import Collector, dns_seed_peers  # noqa: E402
from beans.collector.resolve import from_args  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--peer", action="append", default=[], help="host:port of a Bitcoin node (repeatable)")
    ap.add_argument("--dns-seed", action="store_true", help="ask the public DNS seeds for peers")
    ap.add_argument("--ipv6", action="store_true", help="also use IPv6 peers from the DNS seeds")
    ap.add_argument("--out", default="data/inbox", help="folder for rotated CSVs")
    ap.add_argument("--minutes", type=float, default=None, help="stop after this long (default: until Ctrl+C)")
    ap.add_argument("--rotate", type=int, default=300, help="seconds per output file")
    ap.add_argument("--max-peers", type=int, default=8)
    ap.add_argument("--rpc", help="resolve confirmed inputs from your Bitcoin Core node: http://user:pass@host:8332")
    ap.add_argument("--esplora", help="… or from an Esplora API (self-hosted electrs, or https://mempool.space/api)")
    a = ap.parse_args(argv)

    peers = [(p.rsplit(":", 1)[0], int(p.rsplit(":", 1)[1])) if ":" in p else (p, 8333) for p in a.peer]
    if a.dns_seed:
        peers += dns_seed_peers(a.max_peers, ipv6=a.ipv6)
    if not peers:
        ap.error("give --peer host:port and/or --dns-seed")
    c = Collector(Path(a.out), rotate_s=a.rotate, max_peers=a.max_peers, resolver=from_args(a.rpc, a.esplora))
    print(f"Collecting from {min(len(peers), a.max_peers)} peer(s) into {a.out}", flush=True)
    try:
        asyncio.run(c.run(peers, None if a.minutes is None else a.minutes * 60, log=lambda m: print(m, flush=True)))
    except KeyboardInterrupt:
        c.flush()
    print(c.stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
