from typing import Dict, List, Set
from collections import defaultdict
import hashlib

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

class EntityClusterService:
    """
    Applies the Common Input Ownership Heuristic (CIOH) to group
    co-spent addresses into distinct cluster entities, excluding detected CoinJoin operations.
    """

    @staticmethod
    def compute_clusters(transactions: List[Dict]) -> Dict[str, str]:
        """
        Takes a list of transaction dicts and returns a mapping:
        { "address": "cluster_id" }
        """
        uf = UnionFind()
        all_addresses: Set[str] = set()

        for tx in transactions:
            inputs = tx.get("input_addresses", [])
            outputs = tx.get("output_addresses", [])
            is_coinjoin = tx.get("is_coinjoin", False)

            for addr in inputs + outputs:
                all_addresses.add(addr)

            # Common Input Ownership: All inputs co-spent in standard tx belong to same entity
            if len(inputs) > 1 and not is_coinjoin:
                first_input = inputs[0]
                for other_input in inputs[1:]:
                    uf.union(first_input, other_input)

        # Build stable human-readable cluster IDs
        root_to_addresses = defaultdict(list)
        for addr in all_addresses:
            root = uf.find(addr)
            root_to_addresses[root].append(addr)

        addr_to_cluster = {}
        for root, addrs in root_to_addresses.items():
            sorted_addrs = sorted(addrs)
            # Create a 8-char hash cluster identifier
            cluster_hash = hashlib.sha256("".join(sorted_addrs).encode()).hexdigest()[:8].upper()
            cluster_id = f"CLUST-{cluster_hash}" if len(sorted_addrs) > 1 else f"SOLO-{cluster_hash}"
            for addr in addrs:
                addr_to_cluster[addr] = cluster_id

        return addr_to_cluster
