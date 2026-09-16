"""
Stage 5: lender-matching + loan offer flow. Standard filtering + CRUD on top
of the scoring engine (Stage 2/3) and linkage table (Stage 4) -- no novel
modelling here, which is deliberate: this is where the project plan says
complexity should be low relative to the scoring engine.

Eligibility rule: a lender can see (and offer to) an individual if either
  (a) the individual is in an SHG that has an Approved link with this lender, or
  (b) the individual is independent (no SHG) and this lender.serves_independents.
On top of that, the individual's latest score must clear the lender's
min_score_threshold. Individuals with no score yet (score never computed) are
excluded -- they need to be scored before a lender can consider them, not
silently treated as either eligible or ineligible.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Individual, Lender, LoanOffer, Loan, SHGLenderLink


class MatchingError(ValueError):
    pass


def eligible_borrowers(db: Session, lender_id: int) -> list[dict]:
    lender = db.get(Lender, lender_id)
    if lender is None:
        raise MatchingError(f"Lender {lender_id} not found")

    approved_shg_ids = {
        row.shg_id for row in db.query(SHGLenderLink.shg_id)
        .filter(SHGLenderLink.lender_id == lender_id, SHGLenderLink.status == "Approved")
        .all()
    }

    results = []
    for ind in db.query(Individual).filter(Individual.status == "Active").all():
        if ind.shg_id is not None:
            if ind.shg_id not in approved_shg_ids:
                continue
        else:
            if not lender.serves_independents:
                continue

        score_row = ind.latest_score
        if score_row is None:
            continue
        if score_row.score < lender.min_score_threshold:
            continue

        results.append({
            "individual_id": ind.id,
            "name": ind.name,
            "district": ind.district.name if ind.district else None,
            "is_shg_linked": ind.is_shg_linked,
            "shg_name": ind.shg.name if ind.shg else None,
            "score": score_row.score,
            "risk_category": score_row.risk_category,
        })

    results.sort(key=lambda r: -r["score"])
    return results


def propose_offer(db: Session, lender_id: int, individual_id: int,
                   principal: float, rate: float, tenure: int) -> LoanOffer:
    lender = db.get(Lender, lender_id)
    individual = db.get(Individual, individual_id)
    if lender is None:
        raise MatchingError(f"Lender {lender_id} not found")
    if individual is None:
        raise MatchingError(f"Individual {individual_id} not found")

    eligible_ids = {row["individual_id"] for row in eligible_borrowers(db, lender_id)}
    if individual_id not in eligible_ids:
        raise MatchingError(
            f"Individual {individual_id} is not eligible for lender {lender_id} "
            "(no approved SHG link / doesn't serve independents / score below threshold / not yet scored)"
        )
    if principal > lender.max_loan_amount:
        raise MatchingError(f"Principal {principal} exceeds lender's max_loan_amount {lender.max_loan_amount}")

    offer = LoanOffer(
        lender_id=lender_id, individual_id=individual_id,
        principal_offer=principal, rate_offer=rate, tenure_offer=tenure,
        status="Proposed", created_date=datetime.utcnow(),
    )
    db.add(offer)
    db.flush()
    return offer


def decide_offer(db: Session, offer_id: int, accept: bool) -> LoanOffer:
    offer = db.get(LoanOffer, offer_id)
    if offer is None:
        raise MatchingError(f"Offer {offer_id} not found")
    if offer.status != "Proposed":
        raise MatchingError(f"Offer {offer_id} already decided (status={offer.status})")

    offer.status = "Accepted" if accept else "Rejected"
    offer.decided_date = datetime.utcnow()
    db.flush()

    if accept:
        loan = Loan(
            individual_id=offer.individual_id, lender_id=offer.lender_id,
            principal_amount=offer.principal_offer, interest_rate=offer.rate_offer,
            tenure_months=offer.tenure_offer, disbursement_date=datetime.utcnow().date(),
            outstanding_balance=offer.principal_offer, status="Active",
            purpose="Marketplace offer",
        )
        db.add(loan)
        db.flush()

    return offer
