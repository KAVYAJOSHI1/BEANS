"""Entity/transaction graph. OWNER: Dharmik."""


def build(con) -> dict:
    """Fill tx_first_spy, wallet_ip, flow_edge from the ingested tables. Returns counts."""
    raise NotImplementedError("Dharmik: beans.graph.build")


def subgraph(con, center: str, hops: int = 2, min_risk: float = 0.0, limit: int = 300) -> dict:
    """center = "wallet:<addr>" | "tx:<txid>" | "ip:<ip>" | "cluster:<id>".
    Returns {"nodes": [...], "edges": [...]} in the shape documented in docs/CONTRACTS.md §4."""
    raise NotImplementedError("Dharmik: beans.graph.subgraph")
