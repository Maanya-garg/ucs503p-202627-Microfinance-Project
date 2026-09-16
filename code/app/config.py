"""
Central configuration. Everything reads DATABASE_URL from here so swapping
SQLite (local dev) for Postgres (production) is a one-line env var change --
no code in models/services needs to know which database it's talking to.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

DATA_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Default: local SQLite file. Set DATABASE_URL env var to point at Postgres
# instead, e.g. postgresql+psycopg2://user:pass@host:5432/microfin
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'microfin.db'}")

# --- Scoring engine knobs (kept here so they're easy to tune / cite in the report) ---
SCORE_MIN = 300
SCORE_MAX = 900

# Cold-start bootstrap weights (Stage 3)
# An SHG-linked individual's starting score is a blend of the SHG's aggregate
# track record and a neutral prior. Independent individuals get no SHG boost --
# they start at a flat, lower base and everything after that is earned.
SHG_BOOTSTRAP_WEIGHT = 0.6          # how much of the SHG aggregate carries over
INDEPENDENT_BASE_SCORE = 450        # flat starting point, no SHG connection
NEUTRAL_PRIOR_SCORE = 500           # "unknown individual" prior blended with SHG score

# Number of repayment events after which an individual's own history starts
# dominating the SHG prior in the blended model (see services/bootstrap.py)
HISTORY_MATURITY_EVENTS = 6

# --- Admin auth (Stage 9 role-gated redesign) ---
# Admin isn't a business entity in this schema (no "staff" table), so its
# credential is env-configured rather than a DB row -- see docs/SPEC.md §6.
# Defaults are demo-only, same spirit as the borrower DEMO_PASSWORD.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
