"""Borrower-initiated loan requests -- the mirror of matching_service's
lender-initiated offers. A request is broadcast (visible to every lender the
borrower is currently eligible for, computed the same way as
matching_service.eligible_borrowers, just from the individual's side rather
than the lender's), and any one of those lenders can approve it, which
creates the loan immediately. Declining is per-lender and non-terminal: it
only removes the request from that lender's own queue (LoanRequestDecline),
it doesn't close the request for anyone else."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Individual, Lender, Loan, LoanRequest, LoanRequestDecline, SHGLenderLink


class LoanRequestError(ValueError):
    pass


def _lender_eligible_for_individual(lender: Lender, ind: Individual, approved_shg_ids: set[int]) -> bool:
    if ind.shg_id is not None:
        if ind.shg_id not in approved_shg_ids:
            return False
    elif not lender.serves_independents:
        return False
    score_row = ind.latest_score
    if score_row is None:
        return False
    return score_row.score >= lender.min_score_threshold


def eligible_lenders_for_individual(db: Session, individual: Individual) -> list[Lender]:
    """Which lenders would currently see a request from this borrower --
    shown to the borrower so "I requested a loan and nothing happened" isn't
    a silent dead end."""
    score_row = individual.latest_score
    if score_row is None:
        return []
    results = []
    for lender in db.query(Lender).all():
        if individual.shg_id is not None:
            approved = (
                db.query(SHGLenderLink)
                .filter(
                    SHGLenderLink.shg_id == individual.shg_id,
                    SHGLenderLink.lender_id == lender.id,
                    SHGLenderLink.status == "Approved",
                )
                .first()
            )
            if approved is None:
                continue
        elif not lender.serves_independents:
            continue
        if score_row.score < lender.min_score_threshold:
            continue
        results.append(lender)
    return results


def create_request(db: Session, individual_id: int, principal: float, tenure: int,
                    purpose: str | None = None) -> LoanRequest:
    ind = db.get(Individual, individual_id)
    if ind is None:
        raise LoanRequestError(f"Individual {individual_id} not found")
    if principal <= 0:
        raise LoanRequestError("Requested principal must be positive")
    if tenure <= 0:
        raise LoanRequestError("Requested tenure (months) must be positive")
    if ind.latest_score is None:
        raise LoanRequestError("This borrower hasn't been scored yet -- recompute their score before requesting a loan")

    req = LoanRequest(
        individual_id=individual_id, requested_principal=principal,
        requested_tenure=tenure, purpose=purpose, status="Pending",
        created_date=datetime.utcnow(),
    )
    db.add(req)
    db.flush()
    return req


def withdraw_request(db: Session, request_id: int) -> LoanRequest:
    req = db.get(LoanRequest, request_id)
    if req is None:
        raise LoanRequestError(f"Loan request {request_id} not found")
    if req.status != "Pending":
        raise LoanRequestError(f"Loan request {request_id} already decided (status={req.status}) -- can't withdraw")
    req.status = "Withdrawn"
    db.flush()
    return req


def decline_request(db: Session, request_id: int, lender_id: int) -> LoanRequest:
    req = db.get(LoanRequest, request_id)
    lender = db.get(Lender, lender_id)
    if req is None:
        raise LoanRequestError(f"Loan request {request_id} not found")
    if lender is None:
        raise LoanRequestError(f"Lender {lender_id} not found")
    if req.status != "Pending":
        raise LoanRequestError(f"Loan request {request_id} already decided (status={req.status})")

    existing = (
        db.query(LoanRequestDecline)
        .filter(LoanRequestDecline.request_id == request_id, LoanRequestDecline.lender_id == lender_id)
        .first()
    )
    if existing is None:
        db.add(LoanRequestDecline(request_id=request_id, lender_id=lender_id))
        db.flush()
    return req


def approve_request(db: Session, request_id: int, lender_id: int, rate: float) -> LoanRequest:
    req = db.get(LoanRequest, request_id)
    lender = db.get(Lender, lender_id)
    if req is None:
        raise LoanRequestError(f"Loan request {request_id} not found")
    if lender is None:
        raise LoanRequestError(f"Lender {lender_id} not found")
    if req.status != "Pending":
        raise LoanRequestError(f"Loan request {request_id} already decided (status={req.status})")
    if req.requested_principal > lender.max_loan_amount:
        raise LoanRequestError(
            f"Requested principal {req.requested_principal} exceeds lender's max_loan_amount {lender.max_loan_amount}"
        )

    ind = req.individual
    approved_shg_ids = set()
    if ind.shg_id is not None:
        approved_shg_ids = {
            row.shg_id for row in db.query(SHGLenderLink.shg_id)
            .filter(SHGLenderLink.lender_id == lender_id, SHGLenderLink.status == "Approved")
            .all()
        }
    if not _lender_eligible_for_individual(lender, ind, approved_shg_ids):
        raise LoanRequestError(
            f"Lender {lender_id} is not currently eligible to fund individual {ind.id} "
            "(no approved SHG link / doesn't serve independents / score below threshold)"
        )

    req.status = "Approved"
    req.decided_date = datetime.utcnow()
    req.decided_by_lender_id = lender_id
    db.flush()

    loan = Loan(
        individual_id=ind.id, lender_id=lender_id,
        principal_amount=req.requested_principal, interest_rate=rate,
        tenure_months=req.requested_tenure, disbursement_date=datetime.utcnow().date(),
        outstanding_balance=req.requested_principal, status="Active",
        purpose=req.purpose or "Borrower-requested loan",
    )
    db.add(loan)
    db.flush()

    req.resulting_loan_id = loan.id
    db.flush()
    return req


def requests_for_lender(db: Session, lender_id: int) -> list[LoanRequest]:
    """Everything this lender can act on right now (Pending, eligible, not
    already declined by them) plus their own past decisions on requests --
    the same "queue + history" shape the existing Offers table already has."""
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise LoanRequestError(f"Lender {lender_id} not found")

    declined_ids = {
        row.request_id for row in db.query(LoanRequestDecline.request_id)
        .filter(LoanRequestDecline.lender_id == lender_id).all()
    }
    approved_shg_ids = {
        row.shg_id for row in db.query(SHGLenderLink.shg_id)
        .filter(SHGLenderLink.lender_id == lender_id, SHGLenderLink.status == "Approved").all()
    }

    results = []
    for req in db.query(LoanRequest).order_by(LoanRequest.id.desc()).all():
        if req.status == "Pending":
            if req.id in declined_ids:
                continue
            if not _lender_eligible_for_individual(lender, req.individual, approved_shg_ids):
                continue
            results.append(req)
        elif req.decided_by_lender_id == lender_id:
            results.append(req)
    return results
