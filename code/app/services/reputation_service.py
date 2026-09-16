"""Lender reputation/credit score -- formula adopted verbatim from
docs/REQUIREMENTS.md §4 / docs/SPEC.md §7. Compute-on-read, no caching
column (only 6 lenders exist today, cheap to recompute every time)."""
from sqlalchemy.orm import Session

from app.models import Lender, LoanOffer


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_reputation(db: Session, lender: Lender, all_lenders: list[Lender] | None = None) -> dict:
    if all_lenders is None:
        all_lenders = db.query(Lender).all()

    if not all_lenders:
        return {"reputation_score": 50, "explanation": "No lenders on the platform yet."}

    pop_avg_rate = sum(l.base_interest_rate for l in all_lenders) / len(all_lenders)
    if pop_avg_rate <= 0:
        pop_avg_rate = 1e-9

    rate_component = _clip((pop_avg_rate - lender.base_interest_rate) / pop_avg_rate, -1.0, 1.0)

    lender_offers = db.query(LoanOffer).filter(LoanOffer.lender_id == lender.id).all()
    actual_offer_component = 0.0
    if lender_offers:
        avg_offer_rate = sum(o.rate_offer for o in lender_offers) / len(lender_offers)
        actual_offer_component = _clip((pop_avg_rate - avg_offer_rate) / pop_avg_rate, -1.0, 1.0)

    offer_counts = {}
    for l in all_lenders:
        offer_counts[l.id] = db.query(LoanOffer).filter(LoanOffer.lender_id == l.id).count()
    max_offers = max(offer_counts.values()) if offer_counts else 0
    n_offers_by_lender = offer_counts.get(lender.id, len(lender_offers))
    activity_component = min(1.0, n_offers_by_lender / max_offers) if max_offers > 0 else 0.0

    reach_component = 1.0 if lender.serves_independents else 0.0

    reputation_raw = (
        0.45 * rate_component
        + 0.25 * actual_offer_component
        + 0.20 * activity_component
        + 0.10 * reach_component
    )
    reputation_score = int(round(50 + 50 * reputation_raw))
    reputation_score = int(_clip(reputation_score, 0, 100))

    if rate_component > 0.05:
        pricing_note = "rates below the platform average"
    elif rate_component < -0.05:
        pricing_note = "rates above the platform average"
    else:
        pricing_note = "rates near the platform average"
    activity_note = "active in the marketplace" if activity_component > 0.3 else "limited marketplace activity so far"

    return {
        "reputation_score": reputation_score,
        "explanation": f"{pricing_note}, {activity_note}.",
    }


def compute_reputation_with_rank(db: Session, lender_id: int) -> dict | None:
    lender = db.get(Lender, lender_id)
    if lender is None:
        return None
    all_lenders = db.query(Lender).order_by(Lender.id).all()
    scored = [(l, compute_reputation(db, l, all_lenders)) for l in all_lenders]
    scored.sort(key=lambda pair: -pair[1]["reputation_score"])
    rank = next(i for i, (l, _) in enumerate(scored, start=1) if l.id == lender_id)
    this = next(r for l, r in scored if l.id == lender_id)
    n = len(all_lenders)
    ordinal = _ordinal(rank)
    explanation = (
        f"{ordinal} of {n}, based on your rate relative to the platform average and your marketplace activity."
    )
    return {
        "lender_id": lender_id,
        "reputation_score": this["reputation_score"],
        "rank": rank,
        "n_lenders": n,
        "explanation": explanation,
    }


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
