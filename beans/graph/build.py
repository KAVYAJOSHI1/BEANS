import networkx as nx
from typing import Dict, Any, List, Optional
from beans.schema import CanonicalRecord

class HeterogeneousGraphBuilder:
    """
    Constructs the in-memory multi-layer heterogeneous forensic graph:
    - Wallet Nodes (address, balance, cluster_id)
    - Transaction Nodes (txid, fee, timestamp, value)
    - IP Nodes (ip, country, city, asn, isp_type)
    - ASN Nodes (asn, name, threat_type)
    - Edges: SPENDS(Wallet->TX), PAYS(TX->Wallet), RELAYED(IP->TX), IN_ASN(IP->ASN)
    """

    @classmethod
    def build_graph(cls, records: List[CanonicalRecord]) -> nx.MultiDiGraph:
        G = nx.MultiDiGraph()

        for r in records:
            tx_id = f"tx_{r.txid[:16]}"
            G.add_node(
                tx_id,
                node_type="TRANSACTION",
                txid=r.txid,
                label=f"TX: {r.txid[:8]}...",
                fee=r.fee,
                timestamp=r.timestamp.isoformat(),
                total_value=r.total_output,
                script_type=r.script_type
            )

            # IP & ASN Nodes
            ip_id = f"ip_{r.src_ip}"
            G.add_node(
                ip_id,
                node_type="IP",
                ip=r.src_ip,
                label=f"IP: {r.src_ip}",
                country=r.geo_country,
                city=r.geo_city,
                lat=r.geo_lat,
                lon=r.geo_lon,
                asn=r.asn,
                asn_type=r.asn_type
            )

            asn_id = f"asn_{r.asn}"
            G.add_node(
                asn_id,
                node_type="ASN",
                asn=r.asn,
                label=f"{r.asn} ({r.asn_name})",
                asn_type=r.asn_type
            )

            # Relayed Edge: IP -> TX
            G.add_edge(ip_id, tx_id, edge_type="RELAYED", timestamp=r.timestamp.isoformat())
            # ASN Edge: IP -> ASN
            G.add_edge(ip_id, asn_id, edge_type="IN_ASN")

            # Input Spends: Wallet -> TX
            for addr, amt in zip(r.input_addresses, r.input_amounts):
                w_id = f"w_{addr}"
                G.add_node(w_id, node_type="WALLET", address=addr, label=f"{addr[:6]}...{addr[-4:]}")
                G.add_edge(w_id, tx_id, edge_type="SPENDS", amount=amt)

            # Output Payments: TX -> Wallet
            for addr, amt in zip(r.output_addresses, r.output_amounts):
                w_id = f"w_{addr}"
                G.add_node(w_id, node_type="WALLET", address=addr, label=f"{addr[:6]}...{addr[-4:]}")
                G.add_edge(tx_id, w_id, edge_type="PAYS", amount=amt)

        return G
