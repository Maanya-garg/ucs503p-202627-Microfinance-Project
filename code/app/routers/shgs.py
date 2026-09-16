from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import SHG, SHGLenderLink
from app.routers.auth import AdminActor, get_current_actor, get_current_admin, get_current_shg
from app.services.linkage_service import LinkageError, request_link
from app.schemas import LinkRequestIn

router = APIRouter(prefix="/api/shgs", tags=["shgs"])

# GROUP BY aggregates for the list endpoint -- see _list_summaries() for why
# these exist instead of the SHG.aggregate_repayment_rate/
# aggregate_attendance_rate model properties.
_REPAYMENT_RATE_BY_SHG_SQL = """
    SELECT i.shg_id AS shg_id,
           SUM(CASE WHEN re.status = 'On_Time' THEN 1 ELSE 0 END) * 1.0 / COUNT(re.id) AS rate
    FROM individuals i
    JOIN loans l ON l.individual_id = i.id
    JOIN repayment_events re ON re.loan_id = l.id
    WHERE i.shg_id IS NOT NULL
    GROUP BY i.shg_id
"""
_ATTENDANCE_RATE_BY_SHG_SQL = """
    SELECT shg_id, SUM(CASE WHEN present THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS rate
    FROM shg_attendance_records
    GROUP BY shg_id
"""
_AVG_SCORE_BY_SHG_SQL = """
    SELECT i.shg_id AS shg_id, AVG(cs.score) AS avg_score
    FROM individuals i
    JOIN credit_scores cs ON cs.individual_id = i.id
        AND cs.calculated_date = (
            SELECT MAX(cs2.calculated_date) FROM credit_scores cs2
            WHERE cs2.individual_id = i.id
        )
    WHERE i.shg_id IS NOT NULL
    GROUP BY i.shg_id
"""
_MEMBER_COUNT_BY_SHG_SQL = """
    SELECT shg_id, COUNT(*) AS n FROM individuals WHERE shg_id IS NOT NULL GROUP BY shg_id
"""


def _summary(shg: SHG):
    """Single-SHG detail view (GET /{shg_id}) -- shg.members is small here
    (one SHG's worth), so the O(members) property walk is fine; it's the
    per-row cost across *all* SHGs in the list endpoint that wasn't."""
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


def _list_summaries(db: Session, shgs: list[SHG]):
    """Was: shg.aggregate_repayment_rate / .aggregate_attendance_rate per
    SHG, which walks members -> loans -> repayment_events in Python. Across
    51 SHGs that meant materializing ~25,600 RepaymentEvent ORM objects just
    to compute a rate -- measured at ~1.1s median. Replaced with three GROUP
    BY aggregate queries (one row per SHG each, computed in SQL) joined here
    by id -- no per-row ORM object materialization at all."""
    repayment = {r.shg_id: r.rate for r in db.execute(text(_REPAYMENT_RATE_BY_SHG_SQL))}
    attendance = {r.shg_id: r.rate for r in db.execute(text(_ATTENDANCE_RATE_BY_SHG_SQL))}
    avg_score = {r.shg_id: r.avg_score for r in db.execute(text(_AVG_SCORE_BY_SHG_SQL))}
    member_count = {r.shg_id: r.n for r in db.execute(text(_MEMBER_COUNT_BY_SHG_SQL))}

    return [
        {
            "id": s.id, "name": s.name, "village": s.village,
            "district": s.district.name if s.district else None,
            "formed_date": s.formed_date.isoformat() if s.formed_date else None,
            "total_members": s.total_members, "status": s.status,
            "n_members_actual": member_count.get(s.id, 0),
            "avg_member_score": round(avg_score[s.id], 1) if s.id in avg_score else None,
            "aggregate_repayment_rate": round(repayment[s.id], 4) if s.id in repayment else None,
            "aggregate_attendance_rate": round(attendance[s.id], 4) if s.id in attendance else None,
        }
        for s in shgs
    ]


@router.get("")
def list_shgs(db: Session = Depends(get_db), district_id: int | None = None,
              actor=Depends(get_current_actor)):
    """Any logged-in role -- district-browse summary list, no members
    (docs/API_CONTRACT.md §3)."""
    q = db.query(SHG).options(selectinload(SHG.district))
    if district_id is not None:
        q = q.filter(SHG.district_id == district_id)
    shgs = q.order_by(SHG.id).all()
    return _list_summaries(db, shgs)


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
