"""Model card: turns the last training/evaluation report into what the dashboard's Model Card page shows.

All numbers come from models/training_report.json, written by beans.score.run after each pipeline run.
Fusion metrics are OUT-OF-FOLD (grouped by entity), i.e. every wallet is scored by a model that never saw
any wallet of the same entity. Nothing is estimated or hard-coded; missing parts are listed as not measured.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from beans.config import settings

CARD_PATH = settings.MODELS_DIR / "model_card.json"
REPORT_PATH = settings.MODELS_DIR / "training_report.json"


def build_model_card(conn=None, labels_path: Optional[Path] = None) -> Dict[str, Any]:
    if not REPORT_PATH.exists():
        raise FileNotFoundError("no training report yet: run the pipeline on a labelled dataset first")
    r = json.loads(REPORT_PATH.read_text())
    fu, e3, e1, e4, aq = r.get("fusion", {}), r.get("e3", {}), r.get("e1", {}), r.get("e4", {}), r.get("alert_quality", {})
    m = []

    def add(engine, metric, score, target=None, baseline=None):
        if isinstance(score, (int, float)):
            m.append({"engine": engine, "metric": metric, "score": score, "target": target, "baseline": baseline})

    add("Fusion (calibrated LightGBM)", "PR-AUC, out-of-fold by entity", fu.get("pr_auc"), ">= 0.80", fu.get("base_rate"))
    add("Fusion (calibrated LightGBM)", "ROC-AUC, out-of-fold", fu.get("roc_auc"), ">= 0.90", 0.5)
    add("Fusion (calibrated LightGBM)", "Precision@50", fu.get("precision_at_50"), ">= 0.80", fu.get("base_rate"))
    add("Fusion (calibrated LightGBM)", "Recall of illicit wallets at p ≥ 0.5", fu.get("recall_at_p50"), ">= 0.60")
    add("Fusion (calibrated LightGBM)", "Expected calibration error", fu.get("ece"), "<= 0.05")
    add("Network-layer ablation", "PR-AUC without network features", fu.get("ablation", {}).get("pr_auc_without_network"),
        None, fu.get("pr_auc"))
    add("Alert list", "Precision (alerted wallets that are illicit)", aq.get("alert_precision"), ">= 0.70")
    add("Alert list", "Illicit entities with ≥1 alert", aq.get("entity_recall"), ">= 0.75")
    add("E3 tx-shape classifier (LightGBM)", "Macro F1, grouped CV", e3.get("macro_f1"), ">= 0.80")
    add("E1 clustering (CIOH + change + self-split)", "Homogeneity: clusters never mix entities", e1.get("homogeneity_illicit"), ">= 0.95")
    add("E1 clustering (CIOH + change + self-split)", "Completeness: entity kept in one cluster", e1.get("completeness_illicit"), ">= 0.50")
    add("E4 seed propagation", "Hidden wallets of seeded entities reached", e4.get("hidden_reached_in_seeded_entities"),
        ">= 0.75", e4.get("legit_reached"))
    add("E4 seed propagation", "All hidden illicit wallets reached (most entities have no seed)", e4.get("hidden_reached"),
        None, e4.get("legit_reached"))
    add("Typology model", "Accuracy on illicit wallets, grouped CV", fu.get("typology_accuracy_grouped_cv"), ">= 0.70")

    ext = _elliptic()
    if ext:
        best = ext["detection"].get("BEANS LightGBM + calibration (AF)", {})
        add("External: Elliptic (real Bitcoin, temporal split)", "Illicit F1 (published random forest 0.788, GCN 0.628)",
            best.get("f1"), ">= 0.70", ext["published_weber_2019"]["Random forest (AF)"]["f1"])
        add("External: Elliptic (real Bitcoin, temporal split)", "Illicit precision / calibration error", best.get("precision"),
            ">= 0.80", best.get("ece"))
        prop = ext.get("propagation", {})
        add("External: Elliptic (real Bitcoin, temporal split)", "PR-AUC with 30 % of illicit known as seeds (without: baseline column)",
            prop.get("pr_auc_model_plus_seeds"), None, prop.get("pr_auc_model_only"))

    conf = e3.get("confusion")
    card = {
        "model_overview": {
            "name": "BEANS: five engines + calibrated fusion",
            "evaluated_at": r.get("evaluated_at"), "trained_this_run": r.get("trained"),
            "transactions": r.get("transactions"), "wallets": r.get("wallets"),
            "illicit_wallets": fu.get("illicit_wallets"), "illicit_entities": fu.get("illicit_entities"),
            "seeds": r.get("seeds"), "features": r.get("feature_count"),
            "analyst_feedback_used": fu.get("analyst_feedback_used", 0), "pipeline_seconds": r.get("timings_s", {}).get("total"),
        },
        "engine_metrics": m,
        "confusion_matrix": conf,
        "feature_importances": r.get("global_importance", []),
        "calibration_reliability": fu.get("reliability"),
        "e3_per_class_f1": e3.get("per_class_f1"),
        "e1_clustering": {k: v for k, v in e1.items() if not isinstance(v, (list, dict))},
        "e4_propagation": e4,
        "alert_quality": aq,
        "evaluation_protocol": {
            "split": "StratifiedGroupKFold (5 folds) by entity; calibration on held-out entities inside each fold",
            "labels_used_for": "training targets and evaluation only, never as features",
            "baseline_column": "PR-AUC/P@50: share of illicit wallets (random ranking); ablation row: PR-AUC with network features; E4: share of legitimate wallets also reached",
        },
    }
    if ext:
        card["external_validation_elliptic"] = {k: ext[k] for k in ("dataset", "split", "detection", "published_weber_2019",
                                                                    "propagation", "notes") if k in ext}
    if conf is None:
        card["not_measured"] = {"E3 confusion matrix": "no labelled transactions in this dataset"}
    CARD_PATH.write_text(json.dumps(card, indent=2, default=str))
    return card


def _elliptic() -> Optional[Dict[str, Any]]:
    from beans.validate.elliptic import REPORT as ELLIPTIC_REPORT
    return json.loads(ELLIPTIC_REPORT.read_text()) if ELLIPTIC_REPORT.exists() else None


def default_labels_path() -> Optional[Path]:
    return REPORT_PATH if REPORT_PATH.exists() else None
