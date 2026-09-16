from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.ml.clustering import cluster_districts
from app.routers.auth import AdminActor, get_current_admin

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/districts")
def districts(db: Session = Depends(get_db), n_clusters: int = 3, admin: AdminActor = Depends(get_current_admin)):
    """Admin only (docs/API_CONTRACT.md §8)."""
    return cluster_districts(db, n_clusters=n_clusters)
