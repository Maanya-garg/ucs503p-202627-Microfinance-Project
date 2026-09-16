"""Admin-only endpoints beyond the existing dashboard/geo/anomalies routers.
Currently just model/scoring health (docs/API_CONTRACT.md §10)."""
import json
import os
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import ARTIFACTS_DIR, SCORE_MAX, SCORE_MIN
from app.db import get_db
from app.models import CreditScore, Individual
from app.routers.auth import AdminActor, get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/model-health")
def model_health(db: Session = Depends(get_db), admin: AdminActor = Depends(get_current_admin)):
    n_total = db.query(Individual.id).count()
    n_scored = db.execute(text("SELECT COUNT(DISTINCT individual_id) FROM credit_scores")).scalar()

    latest_scores_sql = """
        select cs.score
        from credit_scores cs
        join (
            select individual_id, max(calculated_date) as max_date
            from credit_scores group by individual_id
        ) latest on latest.individual_id = cs.individual_id and latest.max_date = cs.calculated_date
    """
    scores = [row[0] for row in db.execute(text(latest_scores_sql)).all()]

    band = 100
    buckets: dict[str, int] = {}
    lo = SCORE_MIN
    while lo < SCORE_MAX:
        hi = min(lo + band, SCORE_MAX)
        buckets[f"{lo}-{hi - 1}"] = 0
        lo += band
    for s in scores:
        idx = min((s - SCORE_MIN) // band, len(buckets) - 1)
        idx = max(idx, 0)
        key = list(buckets.keys())[int(idx)]
        buckets[key] += 1
    score_distribution = [{"bucket": k, "count": v} for k, v in buckets.items()]

    latest_score_row = (
        db.query(CreditScore).order_by(CreditScore.calculated_date.desc()).first()
    )
    model_version = latest_score_row.model_version if latest_score_row else None

    meta_path = ARTIFACTS_DIR / "scoring_meta.json"
    meta = {}
    last_computed = None
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        last_computed = date.fromtimestamp(os.path.getmtime(meta_path)).isoformat()

    return {
        "n_scored": n_scored,
        "n_total": n_total,
        "score_distribution": score_distribution,
        "model_version": model_version,
        "last_computed": last_computed,
        "n_training_rows": meta.get("n_training_rows"),
        "holdout_accuracy": meta.get("holdout_accuracy"),
        "holdout_auc": meta.get("holdout_auc"),
        "trained_on_shg_linked_only": meta.get("trained_on_shg_linked_only"),
        "feature_columns": meta.get("feature_columns"),
    }
