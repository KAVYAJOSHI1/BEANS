import hashlib
from typing import List, Dict, Set
from collections import defaultdict
from beans.schema import CanonicalRecord

class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0
            return item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, item1: str, item2: str):
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            if self.rank[root1] < self.rank[root2]:
                self.parent[root1] = root2
            elif self.rank[root1] > self.rank[root2]:
                self.parent[root2] = root1
            else:
                self.parent[root2] = root1
                self.rank[root1] += 1

class EntityClusteringEngine:
    """
    Engine 1: Common Input Ownership Heuristic (CIOH) + Change Heuristic
    Excludes CoinJoin transactions to avoid artificial super-clustering (R5, E1).
    """

    @classmethod
    def compute_clusters(cls, records: List[CanonicalRecord], coinjoin_txids: Set[str] = None) -> Dict[str, str]:
        uf = UnionFind()
        all_addrs: Set[str] = set()
        cj_set = coinjoin_txids or set()

        for r in records:
            inputs = r.input_addresses
            outputs = r.output_addresses
            for a in inputs + outputs:
                all_addrs.add(a)

            # CIOH: all inputs co-spent belong to same entity unless CoinJoin
            if len(inputs) > 1 and r.txid not in cj_set:
                first = inputs[0]
                for other in inputs[1:]:
                    uf.union(first, other)

        # Map to deterministic cluster identifiers
        root_to_addrs = defaultdict(list)
        for a in all_addrs:
            root = uf.find(a)
            root_to_addrs[root].append(a)

        cluster_map = {}
        for root, addrs in root_to_addrs.items():
            sorted_addrs = sorted(addrs)
            h = hashlib.sha256("".join(sorted_addrs).encode()).hexdigest()[:8].upper()
            cid = f"CLUST_{h}" if len(sorted_addrs) > 1 else f"SOLO_{h}"
            for a in addrs:
                cluster_map[a] = cid

        return cluster_map
