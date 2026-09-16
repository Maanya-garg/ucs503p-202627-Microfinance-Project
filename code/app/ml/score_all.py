"""
Batch-scores every individual in the DB. Run this once after training the
model (and again any time you want fresh scores after more repayment/savings
data comes in) -- it's what actually populates the credit_scores /
score_explanations tables so the API and frontend have real data to show
instead of an empty scoring engine nobody has invoked yet.

Run with:  python -m app.ml.score_all
"""
from app.db import SessionLocal
from app.models import Individual
from app.services.scoring_service import compute_and_store_score


def run():
    db = SessionLocal()
    try:
        individuals = db.query(Individual).all()
        for i, ind in enumerate(individuals, start=1):
            compute_and_store_score(db, ind, notes="Batch scoring run")
            if i % 200 == 0:
                db.commit()
                print(f"  scored {i}/{len(individuals)}...")
        db.commit()
        print(f"Done. Scored {len(individuals)} individuals.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
