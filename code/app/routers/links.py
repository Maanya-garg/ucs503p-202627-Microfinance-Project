from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lender, SHGLenderLink
from app.routers.auth import AdminActor, get_current_admin, get_current_actor, get_current_lender
from app.schemas import LinkDecisionIn, LinkRequestIn
from app.services.linkage_service import LinkageError, decide_link, request_link

router = APIRouter(prefix="/api/links", tags=["links"])


def _summary(link: SHGLenderLink):
    return {
        "id": link.id, "shg_id": link.shg_id, "shg_name": link.shg.name,
        "lender_id": link.lender_id, "lender_name": link.lender.name,
        "status": link.status,
        "requested_date": link.requested_date.isoformat() if link.requested_date else None,
        "decided_date": link.decided_date.isoformat() if link.decided_date else None,
        "notes": link.notes,
        "initiated_by_role": link.initiated_by_role,
    }


@router.get("")
def list_links(db: Session = Depends(get_db), status: str | None = None,
               admin: AdminActor = Depends(get_current_admin)):
    """Admin only (docs/API_CONTRACT.md §5)."""
    q = db.query(SHGLenderLink)
    if status is not None:
        q = q.filter(SHGLenderLink.status == status)
    return [_summary(l) for l in q.order_by(SHGLenderLink.id.desc()).limit(200).all()]


@router.post("")
def create_link(body: LinkRequestIn, db: Session = Depends(get_db),
                 current: Lender = Depends(get_current_lender)):
    """Lender only -- lender_id is forced from session, not trusted from the
    body. Creates a lender-initiated link (docs/API_CONTRACT.md §5)."""
    try:
        link = request_link(db, shg_id=body.shg_id, lender_id=current.id, notes=body.notes,
                             initiated_by_role="lender")
        db.commit()
    except LinkageError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(link)


@router.post("/{link_id}/decide")
def decide(link_id: int, body: LinkDecisionIn, db: Session = Depends(get_db),
           actor=Depends(get_current_actor)):
    """Who may decide depends on who initiated (docs/SPEC.md §4):
    - initiated_by_role == "shg"    -> only the lender session, lender_id == link.lender_id
    - initiated_by_role == "lender" -> only the SHG session, shg_id == link.shg_id
    Admin: 403 (read-only scope, no moderation actions)."""
    link = db.get(SHGLenderLink, link_id)
    if link is None:
        raise HTTPException(404, f"Link {link_id} not found")

    if link.initiated_by_role == "shg":
        if actor.role != "lender" or actor.lender.id != link.lender_id:
            raise HTTPException(403, "Only the lender this link was requested from may decide it.")
    elif link.initiated_by_role == "lender":
        if actor.role != "shg" or actor.shg.id != link.shg_id:
            raise HTTPException(403, "Only the SHG this link was proposed to may decide it.")
    else:
        raise HTTPException(403, "Not authorized for this resource.")

    try:
        link = decide_link(db, link_id=link_id, approve=body.approve, notes=body.notes)
        db.commit()
    except LinkageError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(link)
