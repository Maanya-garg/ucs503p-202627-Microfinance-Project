"""
Stage 8 (stretch): anomaly detection over repayment patterns, to flag
individuals whose behaviour looks like possible gaming of the scoring system
(e.g. suspiciously flawless timing patterns, or savings/repayment
inconsistent with each other) rather than genuine creditworthiness. This is
explicitly a *flag for human review*, not an automatic penalty -- it never
touches CreditScore directly, it only writes to AnomalyFlag.

IsolationForest, not a supervised model: there's no "gamed the system" label
in the synthetic data to train against (nor would there be in reality until
someone's caught), so this is unsupervised outlier detection over the same
behavioural feature space the scoring model uses.

Run with:  python -m app.ml.anomaly
"""
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models import AnomalyFlag, Individual
from app.services.features import compute_raw_features

ANOMALY_FEATURES = [
    "on_time_rate", "late_rate", "partial_rate", "missed_rate",
    "avg_days_late", "savings_regularity", "savings_consistency",
]
MIN_EVENTS_FOR_ANOMALY_CHECK = 5
CONTAMINATION = 0.05  # expect ~5% of the checked population to be flagged


def _reason_for(row: pd.Series) -> str:
    reasons = []
    if row["on_time_rate"] >= 0.98 and row["savings_consistency"] is not None and row["savings_consistency"] > 0.4:
        reasons.append("near-perfect repayment timing alongside highly erratic savings behaviour")
    if row["missed_rate"] > 0.3 and row["savings_regularity"] > 0.9:
        reasons.append("frequent missed repayments despite very regular savings -- inconsistent financial behaviour")
    if row["avg_days_late"] > 15:
        reasons.append("unusually large average lateness when late")
    if not reasons:
        reasons.append("behavioural pattern statistically unusual relative to peers (see feature values)")
    return "; ".join(reasons)


def run_anomaly_detection(db: Session, contamination: float = CONTAMINATION) -> list[dict]:
    individuals = db.query(Individual).all()
    rows = []
    for ind in individuals:
        raw = compute_raw_features(ind)
        if raw["n_repayment_events"] < MIN_EVENTS_FOR_ANOMALY_CHECK:
            continue
        raw["individual_id"] = ind.id
        rows.append(raw)

    if len(rows) < 10:
        return []  # not enough data for a meaningful unsupervised fit

    df = pd.DataFrame(rows)
    X = df[ANOMALY_FEATURES].copy()
    for col in ANOMALY_FEATURES:
        X[col] = X[col].fillna(X[col].median())

    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    model.fit(X)
    df["anomaly_score"] = model.decision_function(X)  # lower = more anomalous
    df["is_anomaly"] = model.predict(X) == -1

    # Clear previous flags before writing this run's -- flags are a point-in-time
    # snapshot, not an append-only history (unlike credit scores).
    db.query(AnomalyFlag).delete()

    flagged = df[df["is_anomaly"]].sort_values("anomaly_score")
    results = []
    for _, row in flagged.iterrows():
        reason = _reason_for(row)
        db.add(AnomalyFlag(
            individual_id=int(row["individual_id"]),
            anomaly_score=float(row["anomaly_score"]),
            reason=reason,
            flagged_date=datetime.utcnow(),
        ))
        results.append({
            "individual_id": int(row["individual_id"]),
            "anomaly_score": round(float(row["anomaly_score"]), 4),
            "reason": reason,
        })
    db.flush()
    return results


def run():
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        results = run_anomaly_detection(db)
        db.commit()
        print(f"Flagged {len(results)} individuals as anomalous.")
        for r in results[:10]:
            print(f"  individual={r['individual_id']} score={r['anomaly_score']} reason={r['reason']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
