"""E4: risk propagation from seed wallets on the value-weighted address flow graph.

- personalised PageRank from the seeds (downstream: where did seed money go)
- reverse PPR (upstream: who funds the seeds)
- decayed haircut taint (share of incoming value that traces back to seeds, ×0.9 per hop); hubs absorb taint
- hop distance + path to the nearest seed (evidence), not routed through hubs such as exchanges
- hop distance ignoring direction (≤ 4), which reaches the sibling outputs of a seed's funder
"""
from collections import deque

import networkx as nx
import pandas as pd

HUB_DEGREE = 60
ANY_DIRECTION_MAX_HOPS = 4


def graph(frames) -> nx.DiGraph:
    tot_in = frames.tin.groupby("txid")["amount"].sum()
    e = frames.tin[["txid", "address", "amount"]].merge(frames.tout[["txid", "address", "amount"]], on="txid",
                                                        suffixes=("_s", "_d"))
    e = e[e["address_s"] != e["address_d"]]
    e["w"] = e["amount_s"] / e["txid"].map(tot_in).clip(lower=1e-12) * e["amount_d"]
    agg = e.groupby(["address_s", "address_d"])["w"].sum().reset_index()
    G = nx.DiGraph()
    G.add_weighted_edges_from(agg.itertuples(index=False, name=None))
    return G


def _bfs(G, seeds, reverse=False, max_hops=8, undirected=False):
    nbrs = (lambda u: list(G.predecessors(u)) + list(G.successors(u))) if undirected else \
        (G.predecessors if reverse else G.successors)
    dist, parent, q = {s: 0 for s in seeds}, {}, deque(seeds)
    while q:
        u = q.popleft()
        if dist[u] >= max_hops or (G.degree(u) > HUB_DEGREE and dist[u] > 0):
            continue   # don't route through hubs (exchanges): paths via them say nothing about ownership
        for v in nbrs(u):
            if v not in dist:
                dist[v], parent[v] = dist[u] + 1, u
                q.append(v)
    return dist, parent


def propagate(G: nx.DiGraph, seeds: set, decay: float = 0.9) -> tuple[pd.DataFrame, dict]:
    seeds = {s for s in seeds if s in G}
    nodes = list(G.nodes)
    if not seeds:
        z = pd.DataFrame(0.0, index=nodes, columns=["ppr", "ppr_reverse", "taint"])
        z["hops_from_seed"] = z["hops_to_seed"] = z["hops_any_seed"] = 99
        return z, {}
    pers = {s: 1 / len(seeds) for s in seeds}
    ppr = nx.pagerank(G, alpha=0.85, personalization=pers, weight="weight", max_iter=200, tol=1e-8)
    rppr = nx.pagerank(G.reverse(copy=False), alpha=0.85, personalization=pers, weight="weight", max_iter=200, tol=1e-8)
    # haircut taint, iterated in time-agnostic fashion for a bounded number of rounds
    in_w = {v: sum(d["weight"] for _, _, d in G.in_edges(v, data=True)) or 1.0 for v in nodes}
    taint = {v: (1.0 if v in seeds else 0.0) for v in nodes}
    for _ in range(8):
        new = dict(taint)
        for v in nodes:
            if v in seeds:
                continue
            # hubs (exchanges, pools) are taint sinks: they pool everyone's coins, so passing taint through them
            # would mark their ordinary customers
            s = sum(taint[u] * d["weight"] for u, _, d in G.in_edges(v, data=True) if G.degree(u) <= HUB_DEGREE)
            new[v] = min(1.0, decay * s / in_w[v])
        taint = new
    down, parent = _bfs(G, seeds)
    up, _ = _bfs(G, seeds, reverse=True)
    # either direction (e.g. seed ← funder → sibling): siblings of a seeded split are one owner's other parts
    anyway, _ = _bfs(G, seeds, max_hops=ANY_DIRECTION_MAX_HOPS, undirected=True)
    mx, mr = max(ppr.values()) or 1, max(rppr.values()) or 1
    df = pd.DataFrame({"ppr": pd.Series(ppr) / mx, "ppr_reverse": pd.Series(rppr) / mr, "taint": pd.Series(taint),
                       "hops_from_seed": pd.Series(down), "hops_to_seed": pd.Series(up),
                       "hops_any_seed": pd.Series(anyway)}).reindex(nodes)
    df[["hops_from_seed", "hops_to_seed", "hops_any_seed"]] = df[["hops_from_seed", "hops_to_seed", "hops_any_seed"]].fillna(99)

    def path(a):
        p = [a]
        while p[-1] in parent:
            p.append(parent[p[-1]])
        return list(reversed(p)) if p[-1] in seeds else []
    return df.fillna(0), {"path": path, "seeds_in_graph": len(seeds)}
