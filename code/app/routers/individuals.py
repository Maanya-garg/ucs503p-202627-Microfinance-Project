from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Individual, Lender, SHGLenderLink
from app.routers.auth import AdminActor, get_current_admin, get_current_actor, get_current_individual
from app.services.scoring_service import compute_and_store_score

router = APIRouter(prefix="/api/individuals", tags=["individuals"])


def _score_summary(ind: Individual):
    s = ind.latest_score
    if s is None:
        return None
    return {"score": s.score, "risk_category": s.risk_category, "base_component": s.base_component,
            "calculated_date": s.calculated_date.isoformat() if s.calculated_date else None}


def _summary(ind: Individual):
    return {
        "id": ind.id, "name": ind.name, "phone": ind.phone,
        "district": ind.district.name if ind.district else None,
        "village": ind.village, "occupation": ind.occupation,
        "monthly_income": ind.monthly_income, "has_bank_account": ind.has_bank_account,
        "is_shg_linked": ind.is_shg_linked,
        "shg_id": ind.shg_id, "shg_name": ind.shg.name if ind.shg else None,
        "status": ind.status,
        "latest_score": _score_summary(ind),
    }


def _third_party_summary(ind: Individual):
    """Summary-only shape for a lender/SHG viewing someone else's individual
    -- no phone, monthly_income, score_explanation, loans, or improvement
    tips (docs/API_CONTRACT.md §2)."""
    s = ind.latest_score
    return {
        "id": ind.id, "name": ind.name,
        "district": ind.district.name if ind.district else None,
        "village": ind.village,
        "shg_id": ind.shg_id, "shg_name": ind.shg.name if ind.shg else None,
        "latest_score": {"score": s.score, "risk_category": s.risk_category} if s else None,
    }


# Feature -> improvement tip mapping, adopted verbatim from
# docs/REQUIREMENTS.md §2.1. Only applied to features with a negative
# shap_contribution (i.e. currently hurting the score).
def _humanize(feature_name: str) -> str:
    return feature_name.replace("_", " ")


def _tip_for_feature(feature_name: str) -> str:
    if feature_name in ("on_time_rate", "late_rate", "missed_rate", "partial_rate"):
        return "Pay your installments on time — missed or late payments are currently lowering your score the most."
    if feature_name == "avg_days_late":
        return "When a payment is late, pay it as soon as possible — the number of days late matters, not just that it was late."
    if feature_name in ("savings_regularity", "savings_consistency"):
        return "Save your expected amount consistently each month — irregular savings is pulling your score down."
    if feature_name == "attendance_rate":
        return "Attend more of your SHG's meetings — your attendance record factors into your score."
    if feature_name == "shg_peer_repayment_rate":
        return "Your SHG group's overall repayment record affects your bootstrap score — encourage fellow members to stay current."
    if feature_name in ("n_repayment_events", "n_loans"):
        return "You don't have much repayment history yet — each on-time repayment you make going forward will move your score more."
    if feature_name == "has_bank_account":
        return "Linking a bank account is a positive signal lenders look for."
    return f"This factor is currently working against your score: {_humanize(feature_name)}."


def _improvement_tips(ind: Individual) -> list[str]:
    latest = ind.latest_score
    if latest is None:
        return []
    negatives = [e for e in latest.explanations if e.shap_contribution < 0]
    negatives.sort(key=lambda e: e.shap_contribution)  # most negative first
    seen = set()
    tips = []
    for e in negatives:
        tip = _tip_for_feature(e.feature_name)
        if tip in seen:
            continue
        seen.add(tip)
        tips.append(tip)
        if len(tips) >= 5:
            break
    return tips


@router.get("")
def list_individuals(
    db: Session = Depends(get_db),
    admin: AdminActor = Depends(get_current_admin),
    search: str | None = None,
    district_id: int | None = None,
    shg_id: int | None = None,
    is_shg_linked: bool | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    """Admin only -- full population browse/search (docs/API_CONTRACT.md §2)."""
    q = db.query(Individual)
    if search:
        term = search.strip()
        like = f"%{term}%"
        conditions = [Individual.name.ilike(like), Individual.phone.ilike(like)]
        if term.isdigit():
            conditions.append(Individual.id == int(term))
        from sqlalchemy import or_
        q = q.filter(or_(*conditions))
    if district_id is not None:
        q = q.filter(Individual.district_id == district_id)
    if shg_id is not None:
        q = q.filter(Individual.shg_id == shg_id)
    if is_shg_linked is not None:
        q = q.filter(Individual.shg_id.isnot(None) if is_shg_linked else Individual.shg_id.is_(None))
    total = q.count()
    rows = q.order_by(Individual.id).offset(offset).limit(limit).all()
    return {"total": total, "items": [_summary(r) for r in rows]}


def _lender_can_view(db: Session, lender_id: int, ind: Individual, lender) -> bool:
    if ind.shg_id is not None:
        link = (
            db.query(SHGLenderLink)
            .filter(SHGLenderLink.shg_id == ind.shg_id, SHGLenderLink.lender_id == lender_id,
                    SHGLenderLink.status == "Approved")
            .first()
        )
        return link is not None
    return bool(lender.serves_independents)


@router.get("/{individual_id}")
def get_individual(
    individual_id: int,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    ind = db.get(Individual, individual_id)
    if ind is None:
        raise HTTPException(404, "Individual not found")

    if actor.role == "admin":
        latest = ind.latest_score
        explanations = []
        if latest is not None:
            explanations = [
                {"feature_name": e.feature_name, "feature_value": e.feature_value, "points": e.shap_contribution}
                for e in sorted(latest.explanations, key=lambda e: -abs(e.shap_contribution))
            ]
        loans = [
            {"id": l.id, "principal_amount": l.principal_amount, "interest_rate": l.interest_rate,
             "tenure_months": l.tenure_months, "status": l.status,
             "disbursement_date": l.disbursement_date.isoformat() if l.disbursement_date else None,
             "outstanding_balance": l.outstanding_balance,
             "n_repayment_events": len(l.repayment_events)}
            for l in ind.loans
        ]
        return {
            **_summary(ind),
            "joined_date": ind.joined_date.isoformat() if ind.joined_date else None,
            "score_explanation": explanations,
            "loans": loans,
            "n_savings_records": len(ind.savings_records),
            "n_attendance_records": len(ind.attendance_records),
        }

    if actor.role == "individual":
        if ind.id != actor.individual.id:
            raise HTTPException(403, "You can only view your own record.")
        latest = ind.latest_score
        explanations = []
        if latest is not None:
            explanations = [
                {"feature_name": e.feature_name, "feature_value": e.feature_value, "points": e.shap_contribution}
                for e in sorted(latest.explanations, key=lambda e: -abs(e.shap_contribution))
            ]
        loans = [
            {"id": l.id, "principal_amount": l.principal_amount, "interest_rate": l.interest_rate,
             "tenure_months": l.tenure_months, "status": l.status,
             "disbursement_date": l.disbursement_date.isoformat() if l.disbursement_date else None,
             "outstanding_balance": l.outstanding_balance,
             "n_repayment_events": len(l.repayment_events)}
            for l in ind.loans
        ]
        return {
            **_summary(ind),
            "joined_date": ind.joined_date.isoformat() if ind.joined_date else None,
            "score_explanation": explanations,
            "loans": loans,
            "n_savings_records": len(ind.savings_records),
            "n_attendance_records": len(ind.attendance_records),
            "improvement_tips": _improvement_tips(ind),
        }

    if actor.role == "lender":
        if not _lender_can_view(db, actor.lender.id, ind, actor.lender):
            raise HTTPException(403, "This individual isn't visible to your lender account.")
        return _third_party_summary(ind)

    if actor.role == "shg":
        if ind.shg_id != actor.shg.id:
            raise HTTPException(403, "This individual isn't a member of your SHG.")
        return _third_party_summary(ind)

    raise HTTPException(403, "Not authorized for this resource.")


@router.get("/{individual_id}/score-history")
def score_history(
    individual_id: int,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    ind = db.get(Individual, individual_id)
    if ind is None:
        raise HTTPException(404, "Individual not found")
    if actor.role == "admin":
        pass
    elif actor.role == "individual" and ind.id == actor.individual.id:
        pass
    else:
        raise HTTPException(403, "You can only view your own score history.")
    return [
        {"score": s.score, "risk_category": s.risk_category, "base_component": s.base_component,
         "calculated_date": s.calculated_date.isoformat() if s.calculated_date else None}
        for s in ind.credit_scores
    ]


@router.post("/{individual_id}/recompute-score")
def recompute_score(
    individual_id: int,
    db: Session = Depends(get_db),
    admin: AdminActor = Depends(get_current_admin),
):
    """Admin only -- ops/compute action, per docs/SPEC.md §10."""
    ind = db.get(Individual, individual_id)
    if ind is None:
        raise HTTPException(404, "Individual not found")
    score_row = compute_and_store_score(db, ind, notes="Manual recompute via API")
    db.commit()
    return {"score": score_row.score, "risk_category": score_row.risk_category,
            "base_component": score_row.base_component}


@router.get("/{individual_id}/suggested-lenders")
def suggested_lenders(
    individual_id: int,
    db: Session = Depends(get_db),
    actor=Depends(get_current_actor),
):
    """NEW -- borrower (own) or admin. docs/API_CONTRACT.md §2."""
    if actor.role == "admin":
        pass
    elif actor.role == "individual" and actor.individual.id == individual_id:
        pass
    else:
        raise HTTPException(403, "You can only view your own suggested lenders.")

    ind = db.get(Individual, individual_id)
    if ind is None:
        raise HTTPException(404, "Individual not found")

    from app.services import loan_request_service
    from app.services.reputation_service import compute_reputation

    lenders = loan_request_service.eligible_lenders_for_individual(db, ind)
    all_lenders = db.query(Lender).all()
    items = []
    for l in lenders:
        rep = compute_reputation(db, l, all_lenders)
        items.append({
            "id": l.id, "name": l.name, "type": l.type,
            "base_interest_rate": l.base_interest_rate, "max_loan_amount": l.max_loan_amount,
            "serves_independents": l.serves_independents,
            "reputation_score": rep["reputation_score"],
        })
    items.sort(key=lambda x: x["base_interest_rate"])
    return {"count": len(items), "lenders": items}
