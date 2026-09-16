from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CreditScore, District, Individual, Lender, Loan, SHG
from app.routers.auth import AdminActor, get_current_admin

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), admin: AdminActor = Depends(get_current_admin)):
    """Admin only (docs/API_CONTRACT.md §8)."""
    n_individuals = db.query(func.count(Individual.id)).scalar()
    n_shg_linked = db.query(func.count(Individual.id)).filter(Individual.shg_id.isnot(None)).scalar()
    n_independent = n_individuals - n_shg_linked
    n_shgs = db.query(func.count(SHG.id)).scalar()
    n_lenders = db.query(func.count(Lender.id)).scalar()
    n_districts = db.query(func.count(District.id)).scalar()

    n_loans = db.query(func.count(Loan.id)).scalar()
    n_defaulted = db.query(func.count(Loan.id)).filter(Loan.status == "Defaulted").scalar()
    n_active = db.query(func.count(Loan.id)).filter(Loan.status == "Active").scalar()
    n_closed = db.query(func.count(Loan.id)).filter(Loan.status == "Closed").scalar()

    # latest score per individual, averaged -- and split by SHG-linked vs independent
    latest_scores_sql = """
        select i.shg_id is not null as linked, cs.score
        from credit_scores cs
        join individuals i on i.id = cs.individual_id
        join (
            select individual_id, max(calculated_date) as max_date
            from credit_scores group by individual_id
        ) latest on latest.individual_id = cs.individual_id and latest.max_date = cs.calculated_date
    """
    rows = db.execute(text(latest_scores_sql)).all()
    linked_scores = [r[1] for r in rows if r[0]]
    indep_scores = [r[1] for r in rows if not r[0]]

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    return {
        "n_individuals": n_individuals, "n_shg_linked": n_shg_linked, "n_independent": n_independent,
        "n_shgs": n_shgs, "n_lenders": n_lenders, "n_districts": n_districts,
        "n_loans": n_loans, "n_loans_defaulted": n_defaulted, "n_loans_active": n_active, "n_loans_closed": n_closed,
        "default_rate": round(n_defaulted / n_loans, 4) if n_loans else None,
        "avg_score_shg_linked": avg(linked_scores),
        "avg_score_independent": avg(indep_scores),
        "n_scored": len(rows),
    }


@router.get("/home-highlights")
def home_highlights(db: Session = Depends(get_db)):
    """NEW, public, no auth -- the one deliberate exception (docs/SPEC.md §5,
    §9; docs/REQUIREMENTS.md §5). Curated aggregate/top-N feed for the home
    page, not a searchable directory."""
    borrower_stories = _borrower_stories(db)
    shg_spotlights = _shg_spotlights(db)
    lender_spotlights = _lender_spotlights(db)
    district_improvement = _district_improvement(db)
    return {
        "borrower_stories": borrower_stories,
        "shg_spotlights": shg_spotlights,
        "lender_spotlights": lender_spotlights,
        "district_improvement": district_improvement,
    }


def _borrower_stories(db: Session, limit: int = 4):
    sql = """
        WITH ranked AS (
          SELECT individual_id, COUNT(*) AS n_scores
          FROM credit_scores GROUP BY individual_id HAVING COUNT(*) >= 3
        ),
        first_last AS (
          SELECT r.individual_id,
            (SELECT score FROM credit_scores cs WHERE cs.individual_id = r.individual_id
               ORDER BY calculated_date ASC LIMIT 1) AS first_score,
            (SELECT score FROM credit_scores cs WHERE cs.individual_id = r.individual_id
               ORDER BY calculated_date DESC LIMIT 1) AS last_score,
            (SELECT id FROM credit_scores cs WHERE cs.individual_id = r.individual_id
               ORDER BY calculated_date DESC LIMIT 1) AS latest_score_id
          FROM ranked r
        )
        SELECT i.id, i.name, d.name AS district, s.name AS shg_name,
               fl.first_score, fl.last_score, (fl.last_score - fl.first_score) AS delta,
               fl.latest_score_id
        FROM first_last fl
        JOIN individuals i ON i.id = fl.individual_id
        JOIN districts d ON d.id = i.district_id
        LEFT JOIN shgs s ON s.id = i.shg_id
        WHERE fl.last_score > fl.first_score
        ORDER BY delta DESC
        LIMIT 20
    """
    rows = db.execute(text(sql)).all()

    picked = []
    picked_ids = set()
    used_districts = set()
    # First pass: diversify by district.
    for r in rows:
        if r.district not in used_districts:
            picked.append(r)
            picked_ids.add(r.id)
            used_districts.add(r.district)
        if len(picked) >= limit:
            break
    # Backfill if fewer than `limit` districts were available.
    if len(picked) < limit:
        for r in rows:
            if r.id in picked_ids:
                continue
            picked.append(r)
            picked_ids.add(r.id)
            if len(picked) >= limit:
                break

    stories = []
    for r in picked:
        top_feature = db.execute(
            text(
                "SELECT feature_name FROM score_explanations WHERE score_id = :sid "
                "ORDER BY shap_contribution DESC LIMIT 1"
            ),
            {"sid": r.latest_score_id},
        ).scalar()
        stories.append({
            "individual_id": r.id, "name": r.name, "district": r.district,
            "shg_name": r.shg_name,
            "first_score": r.first_score, "last_score": r.last_score, "delta": r.delta,
            "top_positive_feature": top_feature,
        })
    return stories


def _shg_spotlights(db: Session, limit: int = 3):
    sql = """
        SELECT s.id, s.name, s.village, d.name AS district,
               SUM(CASE WHEN re.status = 'On_Time' THEN 1 ELSE 0 END) * 1.0 / COUNT(re.id) AS repayment_rate,
               COUNT(DISTINCT i.id) AS n_members
        FROM shgs s
        JOIN districts d ON d.id = s.district_id
        JOIN individuals i ON i.shg_id = s.id
        JOIN loans l ON l.individual_id = i.id
        JOIN repayment_events re ON re.loan_id = l.id
        WHERE s.status = 'Active'
        GROUP BY s.id
        HAVING COUNT(re.id) >= 10
        ORDER BY repayment_rate DESC
        LIMIT :limit
    """
    rows = db.execute(text(sql), {"limit": limit}).all()
    return [
        {"shg_id": r.id, "name": r.name, "village": r.village, "district": r.district,
         "n_members": r.n_members, "repayment_rate": round(r.repayment_rate, 4)}
        for r in rows
    ]


def _lender_spotlights(db: Session, limit: int = 3):
    from app.services.reputation_service import compute_reputation

    sql = """
        SELECT l.id, l.name, l.type,
               COUNT(DISTINCT lo.id) AS n_offers,
               COUNT(DISTINCT sl.id) AS n_shg_links
        FROM lenders l
        LEFT JOIN loan_offers lo ON lo.lender_id = l.id
        LEFT JOIN shg_lender_links sl ON sl.lender_id = l.id AND sl.status = 'Approved'
        GROUP BY l.id
        ORDER BY (n_offers + n_shg_links) DESC
        LIMIT :limit
    """
    rows = db.execute(text(sql), {"limit": limit}).all()
    all_lenders = db.query(Lender).all()
    result = []
    for r in rows:
        lender = db.get(Lender, r.id)
        rep = compute_reputation(db, lender, all_lenders)
        result.append({
            "lender_id": r.id, "name": r.name, "type": r.type,
            "n_offers": r.n_offers, "n_shg_links": r.n_shg_links,
            "reputation_score": rep["reputation_score"],
        })
    return result


def _district_improvement(db: Session, min_n: int = 5, limit: int = 5):
    sql = """
        WITH first_last AS (
          SELECT i.district_id,
            cs.individual_id,
            FIRST_VALUE(cs.score) OVER (PARTITION BY cs.individual_id ORDER BY cs.calculated_date ASC)  AS first_score,
            FIRST_VALUE(cs.score) OVER (PARTITION BY cs.individual_id ORDER BY cs.calculated_date DESC) AS last_score
          FROM credit_scores cs
          JOIN individuals i ON i.id = cs.individual_id
        )
        SELECT d.name AS district, AVG(fl.last_score - fl.first_score) AS avg_delta, COUNT(DISTINCT fl.individual_id) AS n
        FROM (SELECT DISTINCT district_id, individual_id, first_score, last_score FROM first_last) fl
        JOIN districts d ON d.id = fl.district_id
        GROUP BY d.id
        HAVING COUNT(DISTINCT fl.individual_id) >= :min_n
        ORDER BY avg_delta DESC
        LIMIT :limit
    """
    rows = db.execute(text(sql), {"min_n": min_n, "limit": limit}).all()
    return [{"district": r.district, "avg_delta": round(r.avg_delta, 1), "n": r.n} for r in rows]
