from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lender, SHGLenderLink
from app.routers.auth import AdminActor, get_current_admin, get_current_actor, get_current_lender
from app.services.matching_service import MatchingError, eligible_borrowers
from app.services.linkage_service import approved_shgs_for_lender
from app.services.reputation_service import compute_reputation_with_rank

router = APIRouter(prefix="/api/lenders", tags=["lenders"])


def _summary(l: Lender):
    return {
        "id": l.id, "name": l.name, "type": l.type,
        "min_score_threshold": l.min_score_threshold, "max_loan_amount": l.max_loan_amount,
        "base_interest_rate": l.base_interest_rate, "serves_independents": l.serves_independents,
    }


@router.get("")
def list_lenders(db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """Any logged-in role -- full lender directory (docs/API_CONTRACT.md §4)."""
    return [_summary(l) for l in db.query(Lender).order_by(Lender.id).all()]


@router.get("/{lender_id}")
def get_lender(lender_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise HTTPException(404, "Lender not found")

    include_shgs = (
        actor.role == "admin"
        or (actor.role == "lender" and actor.lender.id == lender_id)
        or actor.role == "shg"
    )
    if not include_shgs:
        return _summary(lender)

    linked_shgs = approved_shgs_for_lender(db, lender_id)
    return {**_summary(lender), "approved_shgs": [{"id": s.id, "name": s.name} for s in linked_shgs]}


@router.get("/{lender_id}/eligible-borrowers")
def get_eligible_borrowers(lender_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """Lender (own) or admin only (docs/API_CONTRACT.md §4)."""
    if actor.role == "admin":
        pass
    elif actor.role == "lender" and actor.lender.id == lender_id:
        pass
    else:
        raise HTTPException(403, "Not authorized for this resource.")
    try:
        return eligible_borrowers(db, lender_id)
    except MatchingError as e:
        raise HTTPException(404, str(e))


@router.get("/{lender_id}/reputation")
def get_reputation(lender_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """NEW -- any role (docs/API_CONTRACT.md §4)."""
    result = compute_reputation_with_rank(db, lender_id)
    if result is None:
        raise HTTPException(404, "Lender not found")
    return result


@router.get("/{lender_id}/links")
def get_links(lender_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """NEW -- lender (own) or admin only (docs/API_CONTRACT.md §4)."""
    if actor.role == "admin":
        pass
    elif actor.role == "lender" and actor.lender.id == lender_id:
        pass
    else:
        raise HTTPException(403, "Not authorized for this resource.")

    lender = db.get(Lender, lender_id)
    if lender is None:
        raise HTTPException(404, "Lender not found")

    def shape(link: SHGLenderLink):
        return {
            "id": link.id, "shg_id": link.shg_id, "shg_name": link.shg.name,
            "lender_id": link.lender_id, "lender_name": link.lender.name,
            "status": link.status,
            "requested_date": link.requested_date.isoformat() if link.requested_date else None,
            "decided_date": link.decided_date.isoformat() if link.decided_date else None,
            "notes": link.notes,
            "initiated_by_role": link.initiated_by_role,
        }

    links = db.query(SHGLenderLink).filter(SHGLenderLink.lender_id == lender_id).all()
    approved = [shape(l) for l in links if l.status == "Approved"]
    pending_incoming = [
        {**shape(l), "can_decide": True}
        for l in links if l.status == "Pending" and l.initiated_by_role == "shg"
    ]
    pending_outgoing = [shape(l) for l in links if l.status == "Pending" and l.initiated_by_role == "lender"]
    return {"approved": approved, "pending_incoming": pending_incoming, "pending_outgoing": pending_outgoing}
