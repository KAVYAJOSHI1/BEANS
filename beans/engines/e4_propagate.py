import networkx as nx
from typing import Dict, List, Set, Tuple
from beans.schema import CanonicalRecord

class RiskPropagationEngine:
    """
    Engine 4: Personalized PageRank (PPR) & Decayed Haircut Taint Model (R5, E4).
    Propagates risk scores downstream from known illicit seed addresses.
    """

    @classmethod
    def compute_ppr_and_taint(
        cls,
        records: List[CanonicalRecord],
        seed_addresses: Set[str],
        alpha: float = 0.85,
        decay_lambda: float = 0.75
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, List[str]]]:
        """
        Returns:
        1. ppr_scores: { address: ppr_value }
        2. taint_shares: { address: taint_percentage }
        3. paths_to_seed: { address: [seed, hop1, ..., address] }
        """
        G = nx.DiGraph()

        # Build address-to-address value-weighted directed graph
        for r in records:
            inputs = r.input_addresses
            outputs = r.output_addresses
            out_amts = r.output_amounts
            
            if not inputs or not outputs:
                continue

            # Weight per input-output pair
            share_per_in = 1.0 / len(inputs)
            for u in inputs:
                for v, amt in zip(outputs, out_amts):
                    if u == v:
                        continue
                    edge_w = amt * share_per_in
                    if G.has_edge(u, v):
                        G[u][v]["weight"] += edge_w
                    else:
                        G.add_edge(u, v, weight=edge_w)

        all_nodes = list(G.nodes)
        if not all_nodes:
            return {}, {}, {}

        # 1. Personalized PageRank
        # Build personalization vector targeting seeds
        personalization = {}
        active_seeds = [s for s in seed_addresses if s in G]
        
        if active_seeds:
            seed_weight = 1.0 / len(active_seeds)
            for node in all_nodes:
                personalization[node] = seed_weight if node in active_seeds else 0.0
        else:
            uniform = 1.0 / len(all_nodes)
            for node in all_nodes:
                personalization[node] = uniform

        try:
            ppr_dict = nx.pagerank(G, alpha=alpha, personalization=personalization, weight="weight", max_iter=100)
        except Exception:
            ppr_dict = {n: (1.0 if n in active_seeds else 0.0) for n in all_nodes}

        # Normalize PPR 0 to 1
        max_ppr = max(ppr_dict.values()) if ppr_dict else 1.0
        norm_ppr = {k: round(v / (max_ppr + 1e-8), 4) for k, v in ppr_dict.items()}

        # 2. Decayed Taint & Shortest Paths
        taint_dict = {}
        paths_dict = {}

        for node in all_nodes:
            if node in active_seeds:
                taint_dict[node] = 1.0
                paths_dict[node] = [node]
                continue

            best_path = None
            best_taint = 0.0

            for s in active_seeds:
                if nx.has_path(G, s, node):
                    try:
                        p = nx.shortest_path(G, s, node)
                        hops = len(p) - 1
                        taint_val = (decay_lambda ** hops)
                        if taint_val > best_taint:
                            best_taint = taint_val
                            best_path = p
                    except Exception:
                        pass

            taint_dict[node] = round(best_taint, 4)
            if best_path:
                paths_dict[node] = best_path

        return norm_ppr, taint_dict, paths_dict
