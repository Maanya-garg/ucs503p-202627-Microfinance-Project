from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SHG, SHGLenderLink
from app.routers.auth import AdminActor, get_current_actor, get_current_admin, get_current_shg
from app.services.linkage_service import LinkageError, request_link
from app.schemas import LinkRequestIn

router = APIRouter(prefix="/api/shgs", tags=["shgs"])


def _summary(shg: SHG):
    scores = [m.latest_score.score for m in shg.members if m.latest_score is not None]
    return {
        "id": shg.id, "name": shg.name, "village": shg.village,
        "district": shg.district.name if shg.district else None,
        "formed_date": shg.formed_date.isoformat() if shg.formed_date else None,
        "total_members": shg.total_members, "status": shg.status,
        "n_members_actual": len(shg.members),
        "avg_member_score": round(sum(scores) / len(scores), 1) if scores else None,
        "aggregate_repayment_rate": shg.aggregate_repayment_rate,
        "aggregate_attendance_rate": shg.aggregate_attendance_rate,
    }


def _members(shg: SHG):
    return [
        {"id": m.id, "name": m.name, "score": m.latest_score.score if m.latest_score else None,
         "risk_category": m.latest_score.risk_category if m.latest_score else None}
        for m in shg.members
    ]


@router.get("")
def list_shgs(db: Session = Depends(get_db), district_id: int | None = None,
              actor=Depends(get_current_actor)):
    """Any logged-in role -- district-browse summary list, no members
    (docs/API_CONTRACT.md §3)."""
    q = db.query(SHG)
    if district_id is not None:
        q = q.filter(SHG.district_id == district_id)
    return [_summary(s) for s in q.order_by(SHG.id).all()]


@router.get("/{shg_id}")
def get_shg(shg_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    shg = db.get(SHG, shg_id)
    if shg is None:
        raise HTTPException(404, "SHG not found")

    if actor.role == "admin":
        return {**_summary(shg), "members": _members(shg)}

    if actor.role == "shg":
        if shg.id != actor.shg.id:
            raise HTTPException(403, "You can only view your own SHG.")
        return {**_summary(shg), "members": _members(shg)}

    if actor.role == "lender":
        link = (
            db.query(SHGLenderLink)
            .filter(SHGLenderLink.shg_id == shg_id, SHGLenderLink.lender_id == actor.lender.id,
                    SHGLenderLink.status == "Approved")
            .first()
        )
        if link is None:
            raise HTTPException(403, "This SHG isn't linked to your lender account.")
        return {**_summary(shg), "members": _members(shg)}

    if actor.role == "individual":
        if actor.individual.shg_id != shg_id:
            raise HTTPException(403, "You can only view your own SHG.")
        return _summary(shg)  # summary only, no members array

    raise HTTPException(403, "Not authorized for this resource.")


@router.get("/{shg_id}/lenders")
def shg_lenders(shg_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """SHG (own) or admin only (docs/API_CONTRACT.md §3)."""
    shg = db.get(SHG, shg_id)
    if shg is None:
        raise HTTPException(404, "SHG not found")
    if actor.role == "admin":
        pass
    elif actor.role == "shg" and actor.shg.id == shg_id:
        pass
    else:
        raise HTTPException(403, "Not authorized for this resource.")
    return [
        {"link_id": link.id, "lender_id": link.lender_id, "lender_name": link.lender.name,
         "status": link.status, "requested_date": link.requested_date.isoformat() if link.requested_date else None,
         "decided_date": link.decided_date.isoformat() if link.decided_date else None, "notes": link.notes,
         "initiated_by_role": link.initiated_by_role}
        for link in shg.lender_links
    ]


@router.post("/{shg_id}/link-lender")
def link_lender(shg_id: int, body: LinkRequestIn, db: Session = Depends(get_db),
                 current: SHG = Depends(get_current_shg)):
    """SHG (own) only -- creates an SHG-initiated link."""
    if current.id != shg_id:
        raise HTTPException(403, "You can only create link requests for your own SHG.")
    if body.shg_id != shg_id:
        raise HTTPException(400, "shg_id in body must match URL")
    try:
        link = request_link(db, shg_id=shg_id, lender_id=body.lender_id, notes=body.notes,
                             initiated_by_role="shg")
        db.commit()
    except LinkageError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return {"link_id": link.id, "status": link.status}
