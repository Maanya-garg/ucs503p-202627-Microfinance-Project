"""
Runtime scoring service: wires the trained Stage-2 model into the Stage-3
cold-start bootstrap, and is the single place that writes CreditScore +
ScoreExplanation rows. Every route that needs a score (borrower dashboard,
lender matching, recompute-after-repayment) calls `compute_and_store_score`
rather than re-implementing any of this.

Cold-start blending (Stage 3):
  - 0 repayment events  -> pure bootstrap prior, model isn't even called
    (there's nothing for it to look at yet).
  - 1..HISTORY_MATURITY_EVENTS events -> linear blend of the bootstrap prior
    and the model's output, weight shifting toward the model as real history
    accumulates.
  - >= HISTORY_MATURITY_EVENTS events -> model output only.

The bootstrap prior itself branches on `is_shg_linked`:
  - SHG-linked: a weighted share of the SHG's *peer* on-time rate (everyone
    in the group except this individual -- using the individual's own events
    here would let their own behaviour leak into their own starting point)
    blended with a neutral prior, per SHG_BOOTSTRAP_WEIGHT.
  - Independent: a flat, lower INDEPENDENT_BASE_SCORE. No group signal to
    draw on -- that's the literal cost of not having an SHG connection, and
    it's the only place in this pipeline where that cost is applied.

Explanation points: each ScoreExplanation row's `shap_contribution` is
denominated in *score points* and rows for a given score sum (approximately,
modulo rounding) to `score - SCORE_MIN`, so the borrower dashboard can render
a "starting floor + what added points" waterfall. For the model's own
features this is an approximation -- SHAP values from a binary XGBoost model
are additive in log-odds (margin) space, not in the nonlinearly-transformed
score space, so each feature's margin-space SHAP value is allocated a share
of the model's score-point budget proportional to its share of the total
signed SHAP output. That preserves correct sign and relative ranking (which
is what a "why this score" explanation needs) without claiming decimal-exact
point attribution.
"""
import json
import math
from datetime import datetime

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from app.config import (
    ARTIFACTS_DIR, HISTORY_MATURITY_EVENTS, INDEPENDENT_BASE_SCORE,
    NEUTRAL_PRIOR_SCORE, SCORE_MAX, SCORE_MIN, SHG_BOOTSTRAP_WEIGHT,
)
from app.models import CreditScore, ScoreExplanation
from app.services.features import FEATURE_COLUMNS, compute_raw_features

MODEL_PATH = ARTIFACTS_DIR / "scoring_model.json"
META_PATH = ARTIFACTS_DIR / "scoring_meta.json"

_model = None
_meta = None
_explainer = None


class ModelNotTrainedError(RuntimeError):
    pass


def _load():
    global _model, _meta, _explainer
    if _model is not None:
        return
    if not MODEL_PATH.exists() or not META_PATH.exists():
        raise ModelNotTrainedError(
            "Scoring model artifacts not found. Run `python -m app.ml.train_scoring_model` first."
        )
    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_PATH))
    _meta = json.loads(META_PATH.read_text())
    globals()["_meta"] = _meta
    globals()["_model"] = model
    globals()["_explainer"] = shap.TreeExplainer(model)


def _features_to_row(raw: dict) -> pd.DataFrame:
    _load()
    row = {col: raw.get(col, np.nan) for col in FEATURE_COLUMNS}
    df = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    medians = _meta["impute_medians"]
    for col in FEATURE_COLUMNS:
        if pd.isna(df.at[0, col]):
            df.at[0, col] = medians.get(col, 0)
    return df.astype(float)


def risk_category_for_score(score: int) -> str:
    if score >= 800:
        return "Very Low"
    if score >= 700:
        return "Low"
    if score >= 550:
        return "Medium"
    if score >= 450:
        return "High"
    return "Very High"


def probability_to_score(p_good: float) -> int:
    """p_good = P(no default). Linear map onto [SCORE_MIN, SCORE_MAX]."""
    p_good = min(max(p_good, 0.0), 1.0)
    return int(round(SCORE_MIN + p_good * (SCORE_MAX - SCORE_MIN)))


def model_score_and_shap(raw_features: dict):
    """Returns (score:int, {feature_name: margin_shap_value}, base_model_score:int).

    base_model_score is what the model would predict for a "typical" training
    population member (the SHAP expected_value, i.e. the average prediction,
    mapped onto the score scale). It's the anchor the per-feature
    explanation is built around -- see compute_and_store_score for why."""
    _load()
    X = _features_to_row(raw_features)
    p_default = float(_model.predict_proba(X)[0, 1])
    score = probability_to_score(1 - p_default)
    shap_row = _explainer.shap_values(X)
    if isinstance(shap_row, list):  # some SHAP versions return a list for the binary case
        shap_row = shap_row[-1]
    shap_row = np.asarray(shap_row).reshape(-1)
    shap_dict = {col: float(v) for col, v in zip(FEATURE_COLUMNS, shap_row)}

    base_margin = _meta["shap_expected_value"]
    base_p_default = 1 / (1 + math.exp(-base_margin))
    base_model_score = probability_to_score(1 - base_p_default)

    return score, shap_dict, base_model_score


def bootstrap_prior(individual, raw_features: dict):
    """Stage 3 cold-start prior. Returns (prior_score: float, component: str)."""
    if individual.shg_id is not None:
        peer_rate = raw_features.get("shg_peer_repayment_rate")
        if peer_rate is None or (isinstance(peer_rate, float) and np.isnan(peer_rate)):
            shg_score = NEUTRAL_PRIOR_SCORE  # brand-new SHG, no peer track record yet either
        else:
            shg_score = SCORE_MIN + peer_rate * (SCORE_MAX - SCORE_MIN)
        prior = SHG_BOOTSTRAP_WEIGHT * shg_score + (1 - SHG_BOOTSTRAP_WEIGHT) * NEUTRAL_PRIOR_SCORE
        return prior, "shg_bootstrap"
    return float(INDEPENDENT_BASE_SCORE), "independent_bootstrap"


def compute_and_store_score(db, individual, notes: str | None = None) -> CreditScore:
    """Single entry point for scoring. Computes the blended score, writes a
    CreditScore row plus its ScoreExplanation rows, and returns the new
    CreditScore (added + flushed, not committed -- caller commits so this can
    be batched across many individuals in one transaction)."""
    raw = compute_raw_features(individual)
    n_events = raw["n_repayment_events"]
    prior_score, component = bootstrap_prior(individual, raw)
    floor = SCORE_MIN

    explanation_rows = []  # (feature_name, feature_value_str, points)

    if n_events == 0:
        final_score = prior_score
        label = "SHG group track record" if component == "shg_bootstrap" else "Independent starting score (no SHG link)"
        explanation_rows.append((label, f"base component = {component}, no repayment history yet", final_score - floor))
    else:
        model_score, shap_dict, base_model_score = model_score_and_shap(raw)
        w_model = min(1.0, n_events / HISTORY_MATURITY_EVENTS)
        w_prior = 1.0 - w_model

        final_score = w_prior * prior_score + w_model * model_score

        if w_prior > 0.02:
            prior_label = "SHG group track record" if component == "shg_bootstrap" else "Independent starting score"
            explanation_rows.append((
                prior_label,
                f"{w_prior:.0%} weight -- only {n_events} repayment event(s) so far",
                w_prior * (prior_score - floor),
            ))
        else:
            component = "model"

        # Split the model's score-points budget into two pieces:
        #  (a) where a typical population member would land (the baseline), and
        #  (b) how THIS individual's specific feature values moved them away
        #      from that baseline -- positive or negative.
        # (b) is what gets distributed across features. Anchoring on the
        # baseline instead of the floor is what lets a high-risk individual
        # (whose final score sits near the floor) still get a legible,
        # negative-valued explanation -- anchoring on the floor would give
        # them almost no points to distribute and the explanation would look
        # empty exactly when it matters most.
        explanation_rows.append((
            "Typical borrower baseline",
            "average prediction across the training population",
            w_model * (base_model_score - floor),
        ))

        feature_pot = w_model * (model_score - base_model_score)
        signed_sum = sum(shap_dict.values())
        if abs(signed_sum) < 1e-9:
            share = {k: 1.0 / len(shap_dict) for k in shap_dict}
        else:
            share = {k: v / signed_sum for k, v in shap_dict.items()}

        for feat, shap_val in shap_dict.items():
            points = share[feat] * feature_pot
            if abs(points) < 0.5:
                continue  # skip near-zero contributors -- keeps the explanation readable
            raw_val = raw.get(feat)
            val_str = "n/a" if raw_val is None or (isinstance(raw_val, float) and np.isnan(raw_val)) else f"{raw_val:.3g}"
            explanation_rows.append((feat, val_str, points))

    final_score = int(max(SCORE_MIN, min(SCORE_MAX, round(final_score))))
    risk = risk_category_for_score(final_score)

    score_row = CreditScore(
        individual_id=individual.id, score=final_score, risk_category=risk,
        base_component=component, model_version="v1",
        calculated_date=datetime.utcnow(), notes=notes,
    )
    db.add(score_row)
    db.flush()

    for feat, val_str, points in explanation_rows:
        db.add(ScoreExplanation(
            score_id=score_row.id, feature_name=feat,
            feature_value=val_str, shap_contribution=round(points, 2),
        ))

    return score_row
