import networkx as nx
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.app.models.schema import Transaction, WalletProfile, NetworkObservation

class ForensicsGraphEngine:
    """
    Constructs and traverses multi-layer forensic knowledge graphs:
    - Layer 1: Wallet Address Nodes & Clusters
    - Layer 2: Transaction Edge Flows with BTC Amounts & Timestamps
    - Layer 3: Network IP & ASN Observation Nodes
    """

    @classmethod
    def build_subgraph(
        cls,
        db: Session,
        center_node: Optional[str] = None,
        max_hops: int = 2,
        limit_nodes: int = 80
    ) -> Dict[str, Any]:
        """
        Builds graph representation centered around `center_node` or top risk entities.
        Returns Cytoscape-compatible JSON structure: { "nodes": [...], "edges": [...] }
        """
        G = nx.MultiDiGraph()

        # Load all transactions or filter around center node
        tx_query = db.query(Transaction)
        transactions = tx_query.order_by(Transaction.timestamp.desc()).limit(150).all()

        # Load wallet profiles
        wallets = {w.address: w for w in db.query(WalletProfile).all()}
        # Load network observations
        net_obs = {n.src_ip: n for n in db.query(NetworkObservation).all()}

        for tx in transactions:
            inputs = tx.get_input_addrs()
            outputs = tx.get_output_addrs()
            in_amts = tx.get_input_amts()
            out_amts = tx.get_output_amts()
            ips = tx.get_observed_ips()

            # Transaction node
            tx_node_id = f"tx_{tx.txid[:10]}"
            G.add_node(
                tx_node_id,
                type="TRANSACTION",
                label=f"TX: {tx.txid[:8]}...",
                full_id=tx.txid,
                total_value=tx.total_output,
                fee=tx.fee,
                timestamp=tx.timestamp.isoformat(),
                script_type=tx.script_type
            )

            # Input edges: Wallet -> Transaction
            for idx, in_addr in enumerate(inputs):
                w_prof = wallets.get(in_addr)
                risk = float(w_prof.risk_score) if w_prof else 0.0
                threat = w_prof.threat_classification if w_prof else "UNKNOWN"
                cluster = w_prof.cluster_id if w_prof else None

                G.add_node(
                    in_addr,
                    type="WALLET",
                    label=f"{in_addr[:6]}...{in_addr[-4:]}",
                    full_id=in_addr,
                    risk_score=risk,
                    threat_class=threat,
                    cluster_id=cluster,
                    balance=float(w_prof.balance) if w_prof else 0.0
                )

                amt = in_amts[idx] if idx < len(in_amts) else (tx.total_input / max(1, len(inputs)))
                G.add_edge(
                    in_addr,
                    tx_node_id,
                    type="INPUT_SPEND",
                    label=f"{amt:.3f} BTC",
                    amount=amt
                )

            # Output edges: Transaction -> Wallet
            for idx, out_addr in enumerate(outputs):
                w_prof = wallets.get(out_addr)
                risk = float(w_prof.risk_score) if w_prof else 0.0
                threat = w_prof.threat_classification if w_prof else "UNKNOWN"
                cluster = w_prof.cluster_id if w_prof else None

                G.add_node(
                    out_addr,
                    type="WALLET",
                    label=f"{out_addr[:6]}...{out_addr[-4:]}",
                    full_id=out_addr,
                    risk_score=risk,
                    threat_class=threat,
                    cluster_id=cluster,
                    balance=float(w_prof.balance) if w_prof else 0.0
                )

                amt = out_amts[idx] if idx < len(out_amts) else (tx.total_output / max(1, len(outputs)))
                G.add_edge(
                    tx_node_id,
                    out_addr,
                    type="OUTPUT_PAYMENT",
                    label=f"{amt:.3f} BTC",
                    amount=amt
                )

            # IP Broadcast edges: IP -> Transaction
            for ip in ips:
                n_info = net_obs.get(ip)
                isp = n_info.isp_type if n_info else "DATACENTER"
                asn = n_info.src_asn if n_info else "AS_UNKNOWN"
                country = n_info.src_country if n_info else "XX"

                G.add_node(
                    ip,
                    type="IP_ADDRESS",
                    label=f"IP: {ip}",
                    full_id=ip,
                    isp_type=isp,
                    asn=asn,
                    country=country
                )
                G.add_edge(
                    ip,
                    tx_node_id,
                    type="BROADCAST_FROM",
                    label=f"Broadcast ({country})"
                )

        # Filter around center node if specified
        if center_node and center_node in G:
            nodes_in_scope = set([center_node])
            current_frontier = set([center_node])
            for _ in range(max_hops):
                next_frontier = set()
                for n in current_frontier:
                    neighbors = set(G.predecessors(n)).union(set(G.successors(n)))
                    next_frontier.update(neighbors)
                nodes_in_scope.update(next_frontier)
                current_frontier = next_frontier
            sub_G = G.subgraph(list(nodes_in_scope)[:limit_nodes])
        else:
            sub_G = G.subgraph(list(G.nodes)[:limit_nodes])

        # Convert to Cytoscape format
        elements_nodes = []
        for n, data in sub_G.nodes(data=True):
            elements_nodes.append({
                "data": {
                    "id": str(n),
                    **data
                }
            })

        elements_edges = []
        edge_id = 0
        for u, v, k, data in sub_G.edges(keys=True, data=True):
            edge_id += 1
            elements_edges.append({
                "data": {
                    "id": f"e_{edge_id}",
                    "source": str(u),
                    "target": str(v),
                    **data
                }
            })

        return {
            "summary": {
                "total_nodes": len(elements_nodes),
                "total_edges": len(elements_edges)
            },
            "elements": {
                "nodes": elements_nodes,
                "edges": elements_edges
            }
        }
