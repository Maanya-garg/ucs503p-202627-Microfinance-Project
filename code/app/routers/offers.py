from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LoanOffer
from app.routers.auth import get_current_actor, get_current_individual, get_current_lender
from app.schemas import OfferDecisionIn, OfferProposeIn
from app.services.matching_service import MatchingError, decide_offer, propose_offer

router = APIRouter(prefix="/api/offers", tags=["offers"])


def _summary(o: LoanOffer):
    return {
        "id": o.id, "lender_id": o.lender_id, "lender_name": o.lender.name,
        "individual_id": o.individual_id, "individual_name": o.individual.name,
        "principal_offer": o.principal_offer, "rate_offer": o.rate_offer, "tenure_offer": o.tenure_offer,
        "status": o.status,
        "created_date": o.created_date.isoformat() if o.created_date else None,
        "decided_date": o.decided_date.isoformat() if o.decided_date else None,
    }


@router.get("")
def list_offers(db: Session = Depends(get_db), individual_id: int | None = None,
                 lender_id: int | None = None, status: str | None = None,
                 actor=Depends(get_current_actor)):
    """Borrower (own), lender (own), or admin (docs/API_CONTRACT.md §6)."""
    if actor.role == "admin":
        pass
    elif actor.role == "individual":
        if individual_id is not None and individual_id != actor.individual.id:
            raise HTTPException(403, "You can only view your own offers.")
        individual_id = actor.individual.id
    elif actor.role == "lender":
        if lender_id is not None and lender_id != actor.lender.id:
            raise HTTPException(403, "You can only view your own offers.")
        lender_id = actor.lender.id
    else:
        raise HTTPException(403, "Not authorized for this resource.")

    q = db.query(LoanOffer)
    if individual_id is not None:
        q = q.filter(LoanOffer.individual_id == individual_id)
    if lender_id is not None:
        q = q.filter(LoanOffer.lender_id == lender_id)
    if status is not None:
        q = q.filter(LoanOffer.status == status)
    return [_summary(o) for o in q.order_by(LoanOffer.id.desc()).limit(200).all()]


@router.post("")
def create_offer(body: OfferProposeIn, db: Session = Depends(get_db),
                  current=Depends(get_current_lender)):
    """Lender only -- lender_id in body ignored/validated against session."""
    try:
        offer = propose_offer(db, lender_id=current.id, individual_id=body.individual_id,
                               principal=body.principal, rate=body.rate, tenure=body.tenure)
        db.commit()
    except MatchingError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(offer)


@router.post("/{offer_id}/decide")
def decide(offer_id: int, body: OfferDecisionIn, db: Session = Depends(get_db),
           current=Depends(get_current_individual)):
    """Borrower only -- must own the offer."""
    offer = db.get(LoanOffer, offer_id)
    if offer is None:
        raise HTTPException(404, f"Offer {offer_id} not found")
    if offer.individual_id != current.id:
        raise HTTPException(403, "You can only decide on offers made to you.")
    try:
        offer = decide_offer(db, offer_id=offer_id, accept=body.accept)
        db.commit()
    except MatchingError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    return _summary(offer)
