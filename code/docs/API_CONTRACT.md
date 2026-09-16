# CreditSetu — API Contract (binding for Agent 4 & Agent 5)

Companion to `docs/SPEC.md` (read that first for the *why*). This file is
the exact REST surface: every endpoint, its auth requirement, and its
request/response shape. Existing endpoints not listed as "CHANGED" or "NEW"
keep their current implementation and shape exactly as in
`app/routers/*.py` today — only their **auth requirement** may be added.

## Conventions

- Auth header: `Authorization: Bearer <token>` on every non-public endpoint.
- 4 session tables, one per role: `individual_sessions` (exists),
  `lender_sessions`, `shg_sessions`, `admin_sessions` (new — all mirror
  `individual_sessions`: `id`, `<role>_id` FK, `token` unique indexed,
  `created_at`, `expires_at`, 7-day TTL).
- 4 FastAPI dependencies, parallel to the existing `get_current_individual`
  in `app/routers/auth.py`: `get_current_lender`, `get_current_shg`,
  `get_current_admin`, each raising `401` on missing/invalid/expired token.
- A 5th dependency, `get_current_actor`, returns whichever of the four
  matches the token (role name + id) for endpoints reachable by any
  logged-in role (e.g. `GET /api/lenders`) — raises `401` if none match.
- **403** = valid token, but not authorized for *this* resource (wrong role,
  or an id outside the session's own scope). Never silently substitute the
  session's own id for a mismatched URL id — return 403.
- Response shapes for endpoints marked "unchanged" are exactly what
  `app/routers/*.py` already returns today (see that file for the literal
  dict shape) — not repeated here to avoid drift.

---

## 1. Auth endpoints

### 1.1 Borrower — unchanged
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/login` | public | `{phone, password}` → `{token, individual_id, name}` |
| POST | `/api/auth/logout` | borrower | unchanged |
| GET | `/api/auth/me` | borrower | unchanged (`_summary(individual)`) |

### 1.2 Lender — NEW
| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/auth/lender/login` | public | `{username, password}` | `{token, lender_id, name}` |
| POST | `/api/auth/lender/logout` | lender | — | `{ok: true}` |
| GET | `/api/auth/lender/me` | lender | — | lender `_summary()` shape |

### 1.3 SHG — NEW
| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/auth/shg/login` | public | `{username, password}` | `{token, shg_id, name}` |
| POST | `/api/auth/shg/logout` | shg | — | `{ok: true}` |
| GET | `/api/auth/shg/me` | shg | — | SHG `_summary()` shape |

### 1.4 Admin — NEW
| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| POST | `/api/auth/admin/login` | public | `{username, password}` (checked against `ADMIN_USERNAME`/`ADMIN_PASSWORD` env, default `admin`/`admin123`) | `{token, name: "Admin"}` |
| POST | `/api/auth/admin/logout` | admin | — | `{ok: true}` |
| GET | `/api/auth/admin/me` | admin | — | `{name: "Admin"}` |

---

## 2. Individuals (`app/routers/individuals.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/individuals` | **admin only** (CHANGED — was open) | unchanged query params/shape, now 401/403 for non-admin |
| GET | `/api/individuals/{id}` | **any role, scoped** (CHANGED — was open) | see scoping table below |
| GET | `/api/individuals/{id}/score-history` | **borrower (own) or admin** (CHANGED — was open) | 403 if borrower token's `individual_id != id` |
| POST | `/api/individuals/{id}/recompute-score` | **admin only** (CHANGED — was open) | ops action, per SPEC.md §10 |
| GET | `/api/individuals/{id}/suggested-lenders` | **NEW**, borrower (own) or admin | see below |

**`GET /api/individuals/{id}` scoping:**
- Borrower token: only if `id == session.individual_id`; full response
  (existing shape: summary + `score_explanation` + `loans` + counts) **plus
  new field** `improvement_tips: string[]` (see §6 mapping table).
- Admin token: any `id`; full response, same as above minus `improvement_tips`
  (admin doesn't need the tip strings, but including them is harmless —
  Agent 5's call).
- Lender token: only if `id`'s individual is SHG-linked to an SHG with an
  **Approved** `SHGLenderLink` to this lender, OR is independent
  (`shg_id IS NULL`) and `lender.serves_independents`; else 403. Response is
  **summary only**: `{id, name, district, village, shg_id, shg_name,
  latest_score: {score, risk_category}}` — no `phone`, `monthly_income`,
  `score_explanation`, `loans`, or `improvement_tips`.
- SHG token: only if `id`'s individual has `shg_id == session.shg_id`; else
  403. Same summary-only shape as the lender case above, no `phone`/`monthly_income`.

**`GET /api/individuals/{id}/suggested-lenders` (NEW):**
- Auth: borrower (own id only) or admin.
- Reuses `loan_request_service.eligible_lenders_for_individual`, then for
  each eligible lender computes `reputation_score` (§4) and sorts by
  `base_interest_rate` ascending.
- Response: `{count, lenders: [{id, name, type, base_interest_rate, max_loan_amount, serves_independents, reputation_score}]}`.

---

## 3. SHGs (`app/routers/shgs.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/shgs` | **any role** (CHANGED — was open, now requires *some* valid session) | unchanged shape (list of summaries, no members) — same for every role, this is the district-browse list |
| GET | `/api/shgs/{id}` | **scoped by role** (CHANGED — was open) | see below |
| GET | `/api/shgs/{id}/lenders` | **SHG (own) or admin** (CHANGED — was open) | 403 for lender/borrower tokens |
| POST | `/api/shgs/{id}/link-lender` | **SHG (own)** (CHANGED — was open) | body `shg_id` must match URL **and** session; sets `initiated_by_role="shg"` |

**`GET /api/shgs/{id}` scoping:**
- Admin: full, any id, including `members`.
- SHG token: full incl. `members`, only if `id == session.shg_id`.
- Lender token: full incl. `members`, only if `SHGLenderLink(shg_id=id, lender_id=session.lender_id, status='Approved')` exists; else 403.
- Borrower token: only if `id == session.individual's shg_id`; response is
  **summary only, no `members` array** — `{id, name, village, district,
  formed_date, total_members, n_members_actual, avg_member_score,
  aggregate_repayment_rate, aggregate_attendance_rate}` (matches SPEC.md §3
  item — borrower's "Your SHG" card).

---

## 4. Lenders (`app/routers/lenders.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/lenders` | **any role** (CHANGED — was open) | unchanged shape |
| GET | `/api/lenders/{id}` | **any role** (CHANGED — was open) | `approved_shgs` sub-list included only for admin/lender(own)/shg tokens; borrower gets base `_summary()` only, no `approved_shgs` |
| GET | `/api/lenders/{id}/eligible-borrowers` | **lender (own) or admin** (CHANGED — was open) | 403 for other lenders/roles |
| GET | `/api/lenders/{id}/reputation` | **NEW**, any role | see §5 below |
| GET | `/api/lenders/{id}/links` | **NEW**, lender (own) or admin | replaces plan to extend `approved_shgs_for_lender` in place — see below |

**`GET /api/lenders/{id}/reputation` (NEW):**
- Response: `{lender_id, reputation_score, rank, n_lenders, explanation}`
  e.g. `explanation: "3rd of 6, based on your rate relative to the platform average and your marketplace activity."`

**`GET /api/lenders/{id}/links` (NEW):**
- Response: `{approved: [...], pending_incoming: [...]}` where
  `pending_incoming` = `Pending` links with `initiated_by_role == "shg"`
  (i.e. awaiting *this lender's* decision — `can_decide: true`), and
  `approved` = `Approved` links. A third bucket, `pending_outgoing`
  (`initiated_by_role == "lender"`, awaiting the SHG), is included too, each
  item shaped like `links.py`'s existing `_summary(link)`.

---

## 5. Links (`app/routers/links.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/links` | **admin only** (CHANGED — was open) | unchanged shape |
| POST | `/api/links` | **lender only** (CHANGED — was open) | `lender_id` in body is ignored/validated against `session.lender_id`; sets `initiated_by_role="lender"` — this is now the **lender-initiated** link-request path |
| POST | `/api/links/{id}/decide` | **role determined by `initiated_by_role`** (CHANGED — was open) | see decision table below |

**`POST /api/links/{id}/decide` authorization:**
| `link.initiated_by_role` | Who may decide |
|---|---|
| `"shg"` | lender token, `session.lender_id == link.lender_id` |
| `"lender"` | SHG token, `session.shg_id == link.shg_id` |

Admin: 403 on this endpoint (read-only scope — admin can `GET` links but
not decide them, per SPEC.md §4).

**Schema addition**: `shg_lender_links.initiated_by_role` — `Enum("shg",
"lender")`, `nullable=False`, `default="shg"`. Migration backfills all
existing rows to `"shg"` (accurate: every existing row was created through
the SHG-only flow, since lender auth didn't exist before this pass).

---

## 6. Offers (`app/routers/offers.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/offers` | **borrower (own), lender (own), or admin** (CHANGED — was open) | `individual_id`/`lender_id` query params, if present, must match the session's own id for borrower/lender tokens (403 if not); admin may pass either freely |
| POST | `/api/offers` | **lender only** (CHANGED — was open) | `lender_id` in body ignored/validated against `session.lender_id` |
| POST | `/api/offers/{id}/decide` | **borrower only** (CHANGED — was open) | must own the offer (`offer.individual_id == session.individual_id`), else 403 |

---

## 7. Loan requests (`app/routers/loan_requests.py`)

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/loan-requests` | **borrower (own), lender (own), or admin** (CHANGED — was open) | same forced-scope rule as offers above |
| GET | `/api/loan-requests/eligible-lenders` | **borrower (own) or admin** (CHANGED — was open) | `individual_id` query param must match session for borrower token |
| POST | `/api/loan-requests` | **borrower only** (CHANGED — was open) | `individual_id` in body ignored/validated against session |
| POST | `/api/loan-requests/{id}/withdraw` | **borrower only** (CHANGED — was open) | must own the request, else 403 |
| POST | `/api/loan-requests/{id}/decide` | **lender only** (CHANGED — was open) | `lender_id` in body ignored/validated against session; existing eligibility checks in `loan_request_service.approve_request` unchanged |

---

## 8. Geo, anomalies, dashboard — admin-only lockdown

| Method | Path | Auth | Behavior change |
|---|---|---|---|
| GET | `/api/geo/districts` | **admin only** (CHANGED — was open) | unchanged shape |
| GET | `/api/anomalies` | **admin only** (CHANGED — was open) | unchanged shape |
| POST | `/api/anomalies/run` | **admin only** (CHANGED — was open) | unchanged; compute action, admin's one non-read-only exception |
| GET | `/api/dashboard/summary` | **admin only** (CHANGED — was open) | unchanged shape |
| GET | `/api/dashboard/home-highlights` | **NEW, public, no auth** | see §9 below |
| GET | `/api/admin/model-health` | **NEW, admin only** | see §10 below |

---

## 9. `GET /api/dashboard/home-highlights` (NEW, public)

No auth. Backs `HomeView.jsx`'s new sections per `SPEC.md` §9 /
`REQUIREMENTS.md` §5. Response:

```json
{
  "borrower_stories": [
    {"individual_id": 1, "name": "...", "district": "...", "shg_name": "..." /* or null if independent */,
     "first_score": 512, "last_score": 640, "delta": 128,
     "top_positive_feature": "savings_regularity"}
  ],
  "shg_spotlights": [
    {"shg_id": 1, "name": "...", "village": "...", "district": "...", "n_members": 12, "repayment_rate": 0.94}
  ],
  "lender_spotlights": [
    {"lender_id": 1, "name": "...", "type": "Bank", "n_offers": 14, "n_shg_links": 5, "reputation_score": 78}
  ],
  "district_improvement": [
    {"district": "...", "avg_delta": 42.3, "n": 18}
  ]
}
```
Queries: exactly the SQL in `REQUIREMENTS.md` §5.1–5.4, unchanged. Cache at
process start or compute on each request — Agent 5's call given the tiny
dataset size; no correctness requirement either way.

---

## 10. `GET /api/admin/model-health` (NEW, admin only)

```json
{
  "n_scored": 480,
  "n_total": 500,
  "score_distribution": [{"bucket": "300-399", "count": 12}, "..."],
  "model_version": "v1",
  "last_computed": "2026-08-30",
  "n_training_rows": 474,
  "holdout_accuracy": 0.884,
  "holdout_auc": 0.910,
  "trained_on_shg_linked_only": true,
  "feature_columns": ["monthly_income", "..."]
}
```
- `n_scored`/`n_total`: `COUNT(DISTINCT credit_scores.individual_id)` vs
  `COUNT(individuals.id)`.
- `score_distribution`: histogram over latest-per-individual score, reuse
  `dashboard.py`'s `latest_scores_sql` CTE pattern, bucketed in 100-point
  bands (`SCORE_MIN`..`SCORE_MAX` from `app/config.py`).
- `model_version`: `CreditScore.model_version` from the most recent
  `calculated_date` row.
- `last_computed`: `os.path.getmtime("artifacts/scoring_meta.json")`,
  ISO-formatted — **not** a field read from inside the JSON (it doesn't have
  one; see SPEC.md §8).
- Remaining fields: read verbatim from `artifacts/scoring_meta.json`.

---

## 11. Summary of schema changes for Agent 5

1. `lenders.username` — `String(100)`, nullable, unique.
2. `lenders.password_hash` — `String(150)`, nullable.
3. `shgs.username` — `String(100)`, nullable, unique.
4. `shgs.password_hash` — `String(150)`, nullable.
5. `shg_lender_links.initiated_by_role` — `Enum("shg","lender")`, not null,
   default `"shg"` (backfilled).
6. New table `lender_sessions` (mirror `individual_sessions`, FK `lender_id`).
7. New table `shg_sessions` (mirror `individual_sessions`, FK `shg_id`).
8. New table `admin_sessions` (mirror `individual_sessions`, no FK — just
   `id`, `token`, `created_at`, `expires_at`).
9. `app/config.py`: add `ADMIN_USERNAME` / `ADMIN_PASSWORD` env-configurable
   settings, defaults `admin` / `admin123`.
10. New script `app/ml/seed_role_credentials.py` (idempotent, run after
    `data_gen`), populating items 1–4 above on existing rows only.

No other tables, no new business rows, no fabricated individuals/loans/scores.
