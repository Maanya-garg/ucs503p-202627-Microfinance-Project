# CreditSetu -- Dual-Path Microfinance Credit Scoring

An individual credit-scoring system for microfinance lending in India. The core idea:
every borrower builds their **own** credit score from their own repayment history, but
someone who belongs to a Self-Help Group (SHG) gets a head start — a bootstrap score
derived from their group's track record — while an independent borrower starts lower
and builds purely from scratch. Lenders formally partner with specific SHGs (an
approve/reject linkage, not open lending to anyone), and a scoring engine
(XGBoost + SHAP) explains *why* each score is what it is, not just what it is.

This is a from-scratch rebuild. An earlier version of this project (`Sahara MFI`, a
Node/Express + MySQL app) is on GitHub at `shreesh1802/microfinance_project` — it had
SHG-only scoring via a hand-written SQL formula, no independent-borrower path, no ML,
and no lender marketplace. This build keeps none of that schema (the dual-path design
needed a different one — see "Why a fresh schema" below) but the general shape of the
domain (SHGs, loans, repayments, credit scores) carries over.

## Architecture

```
app/
  models.py              SQLAlchemy schema (13 tables, see below)
  config.py               DB URL + scoring knobs (bootstrap weights, score range)
  db.py                    Engine/session setup (SQLite by default, Postgres via env var)
  schemas.py              Pydantic request bodies for the write endpoints
  main.py                  FastAPI app, wires up all routers

  ml/                      Offline scripts (run from the command line, not imported by the API)
    data_gen.py              Stage 1: synthetic population + loans + repayments + lenders
    train_scoring_model.py   Stage 2: trains the XGBoost model, saves it + SHAP metadata
    score_all.py             Batch-scores every individual (populates credit_scores)
    clustering.py             Stage 7: k-means district clustering (called live by the API)
    anomaly.py                Stage 8: isolation-forest outlier detection

  services/                Business logic the API routes call into
    features.py               Feature engineering shared between training and serving
    scoring_service.py        Stage 2 model + Stage 3 cold-start bootstrap blending
    linkage_service.py        Stage 4: SHG <-> lender approve/reject
    matching_service.py       Stage 5: eligible-borrower filtering + loan offers

  routers/                  FastAPI endpoints, one file per resource

frontend/                 React (Vite) app, five routed views: Home / Borrower / My Score / SHG-Lender / Bank
```

### Data model

Thirteen tables: `districts`, `shgs`, `individuals` (the dual-path pivot —
`shg_id` is nullable; NULL means independent), `shg_attendance_records`,
`savings_records`, `lenders`, `shg_lender_links` (the Stage-4 approve/reject
table), `loans`, `repayment_events`, `credit_scores` (append-only history, not
a single mutable column), `score_explanations` (per-feature SHAP contribution
per score, in score points), `loan_offers` (the Stage-5 marketplace flow), and
`anomaly_flags`.

**Why a fresh schema instead of extending the old one:** the old schema had no
independent-borrower path, no lender entity, and no SHG-lender linkage table —
all three are core to this design, and retrofitting them onto MySQL-specific
PL/SQL triggers/procedures that don't fit a Python scoring engine wasn't worth it.

### Scoring pipeline (Stages 2-3)

1. **Feature engineering** (`services/features.py`) turns one individual's loans,
   repayments, savings, and SHG attendance into ~16 features — repayment rates,
   savings regularity, SHG tenure, peer repayment rate, etc. NaN means "no data",
   never a silent zero.
2. **Training** (`ml/train_scoring_model.py`) fits an XGBoost classifier on
   SHG-linked individuals with >=3 repayment events, predicting "does this person
   have a defaulted loan." SHAP (`TreeExplainer`) explains every prediction.
3. **Cold-start bootstrap** (`services/scoring_service.py`): with 0 repayment
   events, score = pure prior (SHG peer track record, or a flat lower base for
   independents — no model call, there's nothing to look at yet). Between 1 and
   `HISTORY_MATURITY_EVENTS` (6) events, it's a linear blend of the prior and the
   model's output. Past that, it's the model alone.
4. **Explanation**: each `ScoreExplanation` row is denominated in *score points*
   and sums to `score - SCORE_MIN`, so the frontend renders a "starting floor +
   what added points" waterfall — anchored on the model's own baseline
   prediction (not the floor), so a high-risk borrower's explanation stays
   legible instead of collapsing to near-zero (see "Bugs found & fixed" below).

## Borrower login ("My Score")

Every seeded individual can log in on the "My Score" page to see their own current
score, score history, and SHAP explanation without needing to search themselves up
in the Borrower view. Log in with any individual's phone number (visible in the
Borrower search table) and the password `password123` -- every synthetic borrower
gets that same demo password when `data_gen` seeds the database (see
`app/services/auth_service.py`).

This is a plain bearer-token session (`individual_sessions` table), not JWT --
deliberately, so logging into a demo dataset doesn't require adding a new
dependency.

## Lender / SHG / Admin login (role-gated redesign)

Every endpoint now requires a valid bearer token for the right role --
`Authorization: Bearer <token>` -- verified server-side, not just hidden in
the UI (see `docs/SPEC.md` / `docs/API_CONTRACT.md`). Four separate logins,
same PBKDF2 + opaque-token pattern as the borrower login above:

- **Borrower**: phone number + `password123` (unchanged, see above).
- **Lender**: username = slug of the lender's name (e.g. `gramin-sahakari-bank`
  for "Gramin Sahakari Bank"), password `password123`. `POST /api/auth/lender/login`.
- **SHG**: username = slug of the SHG's name (e.g. `isaac-vikas-group`),
  password `password123`. `POST /api/auth/shg/login`.
- **Admin**: username `admin`, password `admin123` (override with the
  `ADMIN_USERNAME`/`ADMIN_PASSWORD` env vars) -- admin has no DB row, this is
  a config credential, not a fabricated business entity. `POST /api/auth/admin/login`.

Lender/SHG credentials are seeded onto the existing rows by the one-off,
idempotent `python -m app.ml.migrate_auth` (also adds the new columns/tables
this redesign needs) -- run once against `data/microfin.db`, safe to re-run.

From My Score, a borrower can also request a loan directly (principal, tenure,
purpose) instead of only waiting to be matched. The request is broadcast to
every lender they're currently eligible for (an approved SHG link, or a
lender that serves independents) and any one of those lenders can approve it,
which creates the loan immediately -- one lender declining doesn't close the
request for the others. Lenders see and act on these from the same SHG/Lender
page they already use for eligible-borrowers and offers ("Loan requests"
card). My Score also now shows the borrower's own pending/past offers
(lender-initiated) and requests (borrower-initiated) with accept/reject/
withdraw actions, since previously that whole marketplace flow only had
buttons on the *lender's* screen -- a borrower had no way to see or act on an
offer made to them at all.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

## Running it

Order matters — each step depends on the previous one's output:

```bash
source .venv/bin/activate

python -m app.ml.data_gen              # 1. wipes + reseeds the DB with synthetic data
python -m app.ml.train_scoring_model   # 2. trains the model, saves to artifacts/
python -m app.ml.score_all             # 3. scores every individual (populates credit_scores)
python -m app.ml.anomaly               # 4. (optional) runs anomaly detection once up front

uvicorn app.main:app --reload          # 5. API at http://localhost:8000, docs at /docs
```

In a second terminal:

```bash
cd frontend
npm run dev                            # frontend at http://localhost:5173, proxies /api to :8000
```

Re-run `data_gen` any time you want a fresh population (it wipes the DB), and
`train_scoring_model` + `score_all` after — a stale model against fresh data
(or vice versa) will give nonsensical scores.

## What's built vs. stretch

All 8 stages from the project plan are implemented and were exercised end-to-end
(not just written — see verification below): synthetic data generation, the
XGBoost+SHAP scoring engine, cold-start bootstrap for both borrower paths,
SHG-lender linkage, lender matching + loan offers, all three frontend
dashboards, k-means geo-clustering, and isolation-forest anomaly detection.

**Deliberately out of scope** (not in the original 8-stage plan, and skipped to
keep this a scoring/marketplace system rather than a full loan-servicing
platform): an EMI due-date schedule / field-agent collections workflow (the old
repo had this — `RepaymentEvent` rows here represent realized history only, not
upcoming due dates), authentication/authorization, and a persisted
geo-clustering results table (it's cheap enough — 10 districts — to recompute
on every request instead).

## Bugs found & fixed during the build

Worth knowing about because they shaped design decisions, not just because they
were bugs:

1. **Synthetic default rule was a hard cliff.** Loans only flipped to `Defaulted`
   at a deterministic `missed_fraction > 0.4` threshold. With 1-3 loans per
   person, that made "defaulted" a near coin-flip right at the boundary — label
   noise, not signal. Replaced with a probabilistic rule where default risk rises
   smoothly with a weighted mix of missed/late/partial behavior. Verified: default
   rate now climbs cleanly from 7% to 100% across the missed-rate range instead of
   jumping off a cliff.
2. **SHAP explanation collapsed for risky borrowers.** Points were originally
   allocated as a share of `(score - floor)`. Anyone scoring near the floor —
   exactly the people who most need "why is my score low" — had almost no budget
   to distribute, so the explanation silently went blank. Fixed by anchoring on
   the model's own baseline prediction instead.
3. **SHG-lender link dates could land in the future.** `requested_date` was
   `formed_date + random(30, 800 days)`, which for a recently-formed SHG could
   exceed today. Capped at `TODAY`.
4. **k-means cluster labels were inverted.** "High Trust" was being assigned to
   the lowest-scoring cluster and vice versa — an off-by-reversed-order bug in
   how cluster rank mapped to label text, not in the clustering itself.
5. **Missing indexes on every foreign key** (SQLite/Postgres don't auto-index
   the referencing side of an FK) and **missing `__init__.py`** in three
   subpackages — both would only have surfaced once the dataset or router
   imports grew, so worth fixing before they did.
6. **Unbounded eligible-borrowers table.** One lender had 351 eligible
   borrowers, rendered as one HTML table with no cap — an 18,000px-tall page.
   Capped at 25 with a "showing top N of M" note, same pattern as borrower search.
7. **Frontend/backend pagination mismatch.** The borrower search UI requested
   `limit=1000`; the API caps `limit` at 500 — every request 422'd. Also, the
   original client-side-filter-over-one-page search design meant roughly half
   the population (whichever didn't fit in the first page) was unreachable by
   search regardless of the limit fix — replaced with real server-side search
   (`?search=`) rather than just raising the limit.
8. **`GET /api/shgs` was an N+1 query dressed as a model property.**
   `SHG.aggregate_repayment_rate`/`.aggregate_attendance_rate` walk
   `members -> loans -> repayment_events` in Python; called once per SHG in
   the list endpoint, that's ~25,000+ `RepaymentEvent` ORM objects
   materialized on every request against the real dataset (51 SHGs, 1,079
   individuals) — measured at 1,101–1,322ms median. Replaced with three
   `GROUP BY` SQL aggregates computed once and joined back by id: 14.5–26.7ms
   median, ~75x faster, byte-for-byte identical response content verified
   before/after.

All of the above were caught by actually running the pipeline end-to-end
(training on real data, scoring real individuals, hitting the live API,
screenshotting the live frontend with Playwright and checking for console/network
errors) rather than by reading the code.

## API

Full interactive docs at `/docs` once the server is running. Key endpoints:

- `GET /api/individuals`, `/api/individuals/{id}`, `/api/individuals/{id}/score-history`
- `POST /api/individuals/{id}/recompute-score`
- `GET /api/shgs`, `/api/shgs/{id}`, `/api/shgs/{id}/lenders`
- `POST /api/shgs/{id}/link-lender`
- `GET /api/lenders`, `/api/lenders/{id}/eligible-borrowers`
- `POST /api/links`, `POST /api/links/{id}/decide`
- `POST /api/offers`, `POST /api/offers/{id}/decide`
- `GET /api/geo/districts` (k-means clusters)
- `GET /api/anomalies`, `POST /api/anomalies/run`
- `GET /api/dashboard/summary`
- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `POST /api/loan-requests`, `GET /api/loan-requests`, `POST /api/loan-requests/{id}/decide`,
  `POST /api/loan-requests/{id}/withdraw`, `GET /api/loan-requests/eligible-lenders`

## Next steps if you keep building this

- Swap SQLite for Postgres (`DATABASE_URL` env var, no code changes needed) once
  more than one process needs to write concurrently.
- The model is trained once on a static synthetic snapshot; a real version would
  retrain periodically as new repayment data comes in, and would want a proper
  train/holdout split by *time* (predict future behavior from past behavior)
  rather than a random split, to better mirror production.
- Auth is now enforced on every endpoint (borrower/lender/SHG/admin, see
  "Lender / SHG / Admin login" above and `docs/API_CONTRACT.md`). A real
  deployment would still want a real password-hashing
  library and short-lived signed tokens instead of the deliberately-minimal
  bearer-token scheme used here.
- The independent-vs-SHG score gap (`INDEPENDENT_BASE_SCORE` vs the SHG bootstrap
  formula in `app/config.py`) is a policy choice, not something the data derived —
  worth stating explicitly in any report as a deliberate design parameter, and a
  good candidate for a sensitivity analysis (how much does this weight matter to
  the fairness story between the two borrower paths?).
