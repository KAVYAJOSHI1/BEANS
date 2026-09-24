import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from beans.api import db
from beans.config import settings

router = APIRouter(prefix="/modelcard", tags=["Model Card"])

# Written by the evaluation step (Dhairya). Shape:
# {"model_overview": {...}, "engine_metrics": [{"engine","metric","score","target"}],
#  "confusion_matrix": {"labels": [...], "matrix": [[...]]}, "feature_importances": [{"feature","importance"}], ...}
CARD_FILE = settings.MODELS_DIR / "model_card.json"


@router.get("")
def get_model_card() -> Dict[str, Any]:
    """Only measured numbers: from models/model_card.json or a model_card table. Nothing hard-coded."""
    if CARD_FILE.exists():
        card = json.loads(CARD_FILE.read_text())
        return {"status": "evaluated", "source": str(CARD_FILE.name), **card}
    if db.table_exists("model_card"):
        rows = db.query("SELECT * FROM model_card")
        if rows:
            card = {}
            for r in rows:
                val = r.get("value")
                try:
                    card[r["key"]] = json.loads(val) if isinstance(val, str) else val
                except ValueError:
                    card[r["key"]] = val
            return {"status": "evaluated", "source": "model_card table", **card}
    return {
        "status": "not_evaluated",
        "message": "No evaluation has been run yet. Run the evaluation step to populate the model card.",
        "model_overview": {"name": "BEANS multi-engine forensic suite"},
        "engine_metrics": [], "feature_importances": [], "confusion_matrix": None,
    }


@router.post("/evaluate")
def run_evaluation(labels: str | None = None) -> Dict[str, Any]:
    """Measure the stored pipeline output against a labels.csv (default: newest synthetic dataset)."""
    from pathlib import Path

    from beans.score.model_card import build_model_card, default_labels_path
    path = Path(labels) if labels else default_labels_path()
    if not path or not path.exists():
        raise HTTPException(404, "no labels.csv found; generate a synthetic dataset first")
    with db.connection() as conn:
        card = build_model_card(conn, path)
    db.audit("MODEL_EVALUATE", "MODEL", "model_card", {"labels": str(path.name)})
    return {"status": "evaluated", "source": CARD_FILE.name, **card}
