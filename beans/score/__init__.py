"""Fusion, calibration, alert generation, evaluation. OWNER: Dhairya."""


def run_all(con, train: bool = True) -> dict:
    """Features -> E3 -> E1 -> E2 -> E4 -> fusion -> alerts. Replaces cluster, cluster_suggest, tx_scores,
    wallet_scores, alert. Trains and saves models to models/ when train=True, otherwise loads them."""
    raise NotImplementedError("Dhairya: beans.score.run_all")


def evaluate(con) -> dict:
    """Compare predictions with labels_*; write metrics to model_card. Returns the metrics dict."""
    raise NotImplementedError("Dhairya: beans.score.evaluate")
