from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

from beans.api import db
from beans.config import settings
from beans.api.routes import stats, alerts, entities, graph, timeline, geomap, cases, seeds, ingest, modelcard, actions, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-Powered Monitoring & Analysis of Bitcoin Transaction Traffic — SIH PS 26146 (NTRO)"
)

app.add_middleware(
    CORSMiddleware,
    # the built UI is served from this same origin; this only admits the Vite dev server
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(stats.router, prefix=settings.API_PREFIX)
app.include_router(alerts.router, prefix=settings.API_PREFIX)
app.include_router(entities.router, prefix=settings.API_PREFIX)
app.include_router(graph.router, prefix=settings.API_PREFIX)
app.include_router(timeline.router, prefix=settings.API_PREFIX)
app.include_router(geomap.router, prefix=settings.API_PREFIX)
app.include_router(cases.router, prefix=settings.API_PREFIX)
app.include_router(seeds.router, prefix=settings.API_PREFIX)
app.include_router(ingest.router, prefix=settings.API_PREFIX)
app.include_router(modelcard.router, prefix=settings.API_PREFIX)
app.include_router(actions.router, prefix=settings.API_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_PREFIX)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "BEANS Pipeline",
        "version": settings.VERSION,
        "offline_mode": True,
        "db": str(settings.DB_PATH),
        "transactions": db.scalar("SELECT COUNT(*) FROM transactions"),
        "alerts": db.scalar("SELECT COUNT(*) FROM alerts"),
        "data_origin": _data_origin(),
    }


def _data_origin() -> str:
    """synthetic = the loaded data came with generator ground truth; operational = real ingested files; empty."""
    if not db.scalar("SELECT COUNT(*) FROM transactions"):
        return "empty"
    has_truth = db.table_exists("labels_address") and db.scalar("SELECT COUNT(*) FROM labels_address")
    return "synthetic" if has_truth else "operational"


@app.get("/api/config")
def public_config():
    """Thresholds the UI needs, so it never keeps its own copies."""
    return {
        "severity_thresholds": {"CRITICAL": settings.RISK_CRITICAL_MIN, "HIGH": settings.RISK_HIGH_MIN,
                                "MEDIUM": settings.RISK_MEDIUM_MIN},
        "alert_min_probability": settings.ALERT_MIN_PROBABILITY, "max_alerts": settings.MAX_ALERTS,
        "impossible_travel_kmh": settings.IMPOSSIBLE_TRAVEL_KMH,
        "actions": {k: getattr(settings, k) for k in type(settings).model_fields if k.startswith("ACTION_")},
        "data_origin": _data_origin(),
    }


@app.get("/api/audit")
def audit_log(limit: int = 200):
    return db.query("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", [limit])

# Mount static frontend if ui/dist exists
frontend_dist = settings.BASE_DIR / "ui" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static_ui")
