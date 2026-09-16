from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.ml.anomaly import run_anomaly_detection
from app.models import AnomalyFlag
from app.routers.auth import AdminActor, get_current_admin

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies(db: Session = Depends(get_db), admin: AdminActor = Depends(get_current_admin)):
    """Admin only (docs/API_CONTRACT.md §8)."""
    rows = db.query(AnomalyFlag).order_by(AnomalyFlag.anomaly_score.asc()).all()
    return [
        {"individual_id": a.individual_id, "individual_name": a.individual.name,
         "anomaly_score": a.anomaly_score, "reason": a.reason,
         "flagged_date": a.flagged_date.isoformat() if a.flagged_date else None}
        for a in rows
    ]


@router.post("/run")
def run_detection(db: Session = Depends(get_db), admin: AdminActor = Depends(get_current_admin)):
    """Admin only -- compute action, admin's one non-read-only exception."""
    results = run_anomaly_detection(db)
    db.commit()
    return {"n_flagged": len(results), "results": results}
