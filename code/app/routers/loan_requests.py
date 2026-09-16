from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Individual, LoanRequest
from app.routers.auth import get_current_actor, get_current_individual, get_current_lender
from app.schemas import LoanRequestDecisionIn, LoanRequestIn, RetargetIn
from app.services import loan_request_service
from app.services.loan_request_service import LoanRequestError

router = APIRouter(prefix="/api/loan-requests", tags=["loan-requests"])


def _summary(r: LoanRequest):
    return {
        "id": r.id,
        "individual_id": r.individual_id,
        "individual_name": r.individual.name,
        "requested_principal": r.requested_principal,
        "requested_tenure": r.requested_tenure,
        "purpose": r.purpose,
        "status": r.status,
        "created_date": r.created_date.isoformat() if r.created_date else None,
        "decided_date": r.decided_date.isoformat() if r.decided_date else None,
        "decided_by_lender_id": r.decided_by_lender_id,
        "decided_by_lender_name": r.decided_by_lender.name if r.decided_by_lender else None,
        "resulting_loan_id": r.resulting_loan_id,
        "target_lender_id": r.target_lender_id,
        "target_lender_name": r.target_lender.name if r.target_lender else None,
    }


@router.get("")
def list_requests(
    db: Session = Depends(get_db),
    individual_id: int | None = None,
    lender_id: int | None = None,
    status: str | None = None,
    actor=Depends(get_current_actor),
):
    """Borrower (own), lender (own), or admin (docs/API_CONTRACT.md §7)."""
    if actor.role == "admin":
        pass
    elif actor.role == "individual":
        if individual_id is not None and individual_id != actor.individual.id:
            raise HTTPException(403, "You can only view your own loan requests.")
        individual_id = actor.individual.id
    elif actor.role == "lender":
        if lender_id is not None and lender_id != actor.lender.id:
            raise HTTPException(403, "You can only view your own loan requests.")
        lender_id = actor.lender.id
    else:
        raise HTTPException(403, "Not authorized for this resource.")

    if lender_id is not None:
        try:
            rows = loan_request_service.requests_for_lender(db, lender_id)
        except LoanRequestError as e:
            raise HTTPException(404, str(e))
    elif individual_id is not None:
        rows = (
            db.query(LoanRequest)
            .filter(LoanRequest.individual_id == individual_id)
            .order_by(LoanRequest.id.desc())
            .all()
        )
    else:
        rows = db.query(LoanRequest).order_by(LoanRequest.id.desc()).limit(200).all()

    if status is not None:
        rows = [r for r in rows if r.status == status]
    return [_summary(r) for r in rows]


@router.get("/eligible-lenders")
def eligible_lenders(individual_id: int, db: Session = Depends(get_db), actor=Depends(get_current_actor)):
    """Borrower (own) or admin (docs/API_CONTRACT.md §7)."""
    if actor.role == "admin":
        pass
    elif actor.role == "individual" and actor.individual.id == individual_id:
        pass
    else:
        raise HTTPException(403, "You can only view your own eligible lenders.")

    ind = db.get(Individual, individual_id)
    if ind is None:
        raise HTTPException(404, f"Individual {individual_id} not found")
    lenders = loan_request_service.eligible_lenders_for_individual(db, ind)
    return {"count": len(lenders), "lenders": [{"id": l.id, "name": l.name} for l in lenders]}


@router.post("")
def create_request(body: LoanRequestIn, db: Session = Depends(get_db),
                    current: Individual = Depends(get_current_individual)):
    """Borrower only -- individual_id in body ignored/validated against session."""
    try:
        req = loan_request_service.create_request(
            db, individual_id=current.id, principal=body.principal,
            tenure=body.tenure, purpose=body.purpose,
            target_lender_id=body.target_lender_id,
        )
        db.commit()
    except LoanRequestError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(req)


@router.post("/{request_id}/retarget")
def retarget(request_id: int, body: RetargetIn, db: Session = Depends(get_db),
             current: Individual = Depends(get_current_individual)):
    """Borrower only -- must own the request. Redirects a Pending request to
    a different (or no) target lender (docs/API_CONTRACT_PAYMENTS.md §3.4)."""
    req = db.get(LoanRequest, request_id)
    if req is None:
        raise HTTPException(404, f"Loan request {request_id} not found")
    if req.individual_id != current.id:
        raise HTTPException(403, "You can only retarget your own loan requests.")
    try:
        req = loan_request_service.retarget_request(db, request_id, current.id, body.target_lender_id)
        db.commit()
    except LoanRequestError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(req)


@router.post("/{request_id}/withdraw")
def withdraw(request_id: int, db: Session = Depends(get_db),
             current: Individual = Depends(get_current_individual)):
    """Borrower only -- must own the request."""
    req = db.get(LoanRequest, request_id)
    if req is None:
        raise HTTPException(404, f"Loan request {request_id} not found")
    if req.individual_id != current.id:
        raise HTTPException(403, "You can only withdraw your own loan requests.")
    try:
        req = loan_request_service.withdraw_request(db, request_id)
        db.commit()
    except LoanRequestError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(req)


@router.post("/{request_id}/decide")
def decide(request_id: int, body: LoanRequestDecisionIn, db: Session = Depends(get_db),
           current=Depends(get_current_lender)):
    """Lender only -- lender_id in body ignored/validated against session."""
    req = db.get(LoanRequest, request_id)
    if req is None:
        raise HTTPException(404, f"Loan request {request_id} not found")
    try:
        if body.approve:
            if body.rate is None:
                raise HTTPException(400, "rate is required to approve a loan request")
            req = loan_request_service.approve_request(db, request_id, current.id, body.rate)
        else:
            req = loan_request_service.decline_request(db, request_id, current.id)
        db.commit()
    except LoanRequestError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(req)
