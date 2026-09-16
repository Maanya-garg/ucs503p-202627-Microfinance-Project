# CreditSetu — Consolidated Spec (SINGLE SOURCE OF TRUTH)

Author: Agent 3 (QA/consolidation), superseding `docs/REQUIREMENTS.md` (Agent 1)
and layering on `docs/DESIGN_SYSTEM.md` (Agent 2, still authoritative for
visual design — unchanged, not reproduced here). Agent 4 (frontend) and
Agent 5 (backend) should build directly from this file + `docs/API_CONTRACT.md`
+ `docs/DESIGN_SYSTEM.md` and should not need to re-derive anything from
Agent 1's original doc, which is now historical context only.

Ground truth product-owner requirement (verbatim): four separate role-gated
logins (borrower / lender / SHG / admin), never a combined interface;
borrower sees own credit history + improvement tips + suggested lenders +
lender directory + own SHG and nothing else; lenders see SHGs by area, their
members, can accept/reject loan requests, and earn a reputation/credit boost
for offering better rates; SHGs get their own page; admin gets read-only
platform oversight; home page gets real borrower stories, SHG/lender
spotlights, and district improvement stats, using only real existing data —
no new fabricated data. **Core complaint being fixed: "everyone can access
and see anyone else's information" — this requires real server-side
authorization, not just hiding UI.**

---

## 1. Verdict on Agent 1 and Agent 2's docs

Both docs are architecturally sound and are adopted with the following
corrections/resolutions (all binding on Agent 4/5):

- Agent 1's role/data-access matrix (§1 of REQUIREMENTS.md) is correct and is
  restated below with one addition: the `SHGLenderLink.initiated_by_role`
  gap is resolved by a **schema addition**, not a convention (see §4).
- Agent 1's auth design (§3) is adopted as-is: PBKDF2 + opaque bearer
  tokens, no JWT, one session table per role, admin as env-var credential
  (not a fabricated DB entity). This is confirmed correct given the schema.
- Agent 1's reputation formula (§4/REQUIREMENTS) is adopted **unchanged** —
  it's computable entirely from existing `Lender`/`LoanOffer` columns.
- Agent 1's home-page content plan (§5/REQUIREMENTS) is adopted **unchanged**
  — all four queries were checked against `app/models.py` and are valid
  (SQLite ≥3.25 window functions confirmed available; `SHG.aggregate_repayment_rate`
  is a Python `@property`, not a SQL column, exactly as Agent 1 flagged, so
  the raw-SQL aggregate version must be used for the spotlight, not the ORM
  property, to avoid N+1 queries).
- Design System doc (Agent 2) requires no changes — it is purely visual and
  applies uniformly to all four dashboards + home page as written. One
  clarification for Agent 4: the "Approve Partnership" / "Reject Partnership"
  button pattern (DESIGN_SYSTEM §4.4) applies on **both** the lender's
  "pending links awaiting you" list and the SHG's "pending links awaiting
  you" list — which list shows the buttons for a given link is now
  determined by `initiated_by_role` (§4 below), not by which role's page
  you're on.
- One infeasibility found and fixed: Agent 1's admin "last training run"
  panel (REQUIREMENTS §2.4 item 6) assumed `artifacts/scoring_meta.json`
  contains a training-date/model-version field. It does not — inspected
  directly, its keys are `feature_columns`, `impute_medians`,
  `shap_expected_value`, `trained_on_shg_linked_only`, `min_repayment_events`,
  `n_training_rows`, `holdout_accuracy`, `holdout_auc`. Fixed in §7 below:
  use the file's own filesystem mtime (real, not fabricated) as "last
  computed," and `CreditScore.model_version` (already a column, e.g. `"v1"`)
  for model version, instead of inventing fields that don't exist.

---

## 2. Role definitions & data-access matrix (final)

| Data category | Borrower | Lender | SHG | Admin |
|---|---|---|---|---|
| Own credit score + full history | ALLOW (own) | n/a | n/a | ALLOW (all, read-only) |
| Own SHAP explanation / improvement tips | ALLOW (own) | DENY | DENY | ALLOW (all, read-only) |
| Other individuals' scores/details | DENY | ALLOW, **summary only** (name, score, risk_category, village/district — no phone, income, or SHAP) — only for members of SHGs with an **Approved** link to this lender, or independents if `serves_independents` | ALLOW, **summary only** — only for own SHG's members | ALLOW (all, full, read-only) |
| Full population borrower search/browse | DENY | DENY | DENY | ALLOW (read-only) |
| Suggested/eligible lenders for self | ALLOW (own eligibility, ranked) | n/a | n/a | n/a |
| Full lender directory (read-only) | ALLOW | ALLOW | ALLOW | ALLOW |
| Own SHG info (aggregate stats) | ALLOW (own SHG only, aggregate fields — no `members` array) | DENY (only via linked-SHG detail, see below) | ALLOW (own, full incl. `members`) | ALLOW (all, read-only) |
| Other SHGs' info | DENY | ALLOW to browse **summary list** (name/village/district/member count) by district; ALLOW full detail incl. `members` **only** for SHGs with an Approved link to this lender | DENY | ALLOW (all, full) |
| Own loan requests/offers | ALLOW (own) | ALLOW (requests directed at them / offers they made) | DENY | ALLOW (all, read-only) |
| SHG-lender link management | DENY | ALLOW: create a lender-initiated link; decide (approve/reject) any link where `initiated_by_role = 'shg'` and `lender_id` = self | ALLOW: create an SHG-initiated link (own `shg_id`); decide any link where `initiated_by_role = 'lender'` and `shg_id` = self | ALLOW (view all, read-only — no decide action, per confirmed read-only scope) |
| Anomaly flags | DENY | DENY | DENY | ALLOW (all) |
| District/geo clustering, model health, scoring-run metadata | DENY | DENY | DENY | ALLOW |
| Lender reputation score | ALLOW (own eligible lenders' scores, as a ranking badge) | ALLOW (own + platform ranking position) | DENY | ALLOW (all, read-only) |

**Row-level enforcement principle (binding on Agent 5):** every scoped
endpoint derives the "own" id from the authenticated session
(`individual_id` / `lender_id` / `shg_id` from the session row looked up by
bearer token) — **never** a client-supplied id. A client-supplied id is only
ever used to pick *which* related resource to fetch, and every such pick
must be checked against the session's own scope server-side before the row
is returned (e.g., a lender viewing SHG X's members is valid only if
`SHGLenderLink(shg_id=X, lender_id=session.lender_id, status='Approved')`
exists — checked in the handler, not assumed from the URL).

---

## 3. Page inventory per role — adopted from REQUIREMENTS.md §2 verbatim

Agent 1's per-role page inventory (REQUIREMENTS.md §2.1–2.4: borrower
dashboard sections 1–9, lender dashboard sections 1–8, SHG dashboard
sections 1–6, admin dashboard sections 1–6, plus the feature→improvement-tip
table) is **adopted without changes** — every page/section/endpoint
reference in that section was cross-checked against the actual routers in
`app/routers/*.py` during this consolidation pass and is accurate. Agent 4
should read REQUIREMENTS.md §2 directly for the full page-by-page content
list; this file does not repeat it verbatim to avoid drift between two
copies. The **only** amendments to that section are:

1. **Borrower §2.1 item 6 ("Suggested lenders for you")**: backed by a
   **new** endpoint `GET /api/individuals/{id}/suggested-lenders` (not the
   bare `eligible-lenders` endpoint, which only returns id/name) — see
   `API_CONTRACT.md`. Returns lenders ranked by `base_interest_rate` asc,
   each annotated with `reputation_score`.
2. **Borrower §2.1 item 5 ("Ways to improve your score")**: computed
   **server-side** (not client-side — Agent 1 left this open) and returned
   as an `improvement_tips` array inside `GET /api/individuals/{id}`'s
   response when called by the owning borrower (or admin). The feature→tip
   mapping table in REQUIREMENTS.md §2.1 is adopted verbatim as the mapping
   table Agent 5 implements.
3. **Lender §2.2 item 4 ("Your linked SHGs")**: backed by a **new** endpoint
   `GET /api/lenders/{id}/links` (own id, Approved + Pending, with a
   `can_decide` boolean per row computed from `initiated_by_role` — see §4),
   replacing the plan to only extend `approved_shgs_for_lender`.
4. **SHG §2.3 item 6 ("Approve/reject a lender-initiated pending link")**:
   the ambiguity Agent 1 flagged is resolved — see §4.
5. **Admin §2.4 item 6 ("Model/scoring health")**: field list corrected —
   see §7 below and `API_CONTRACT.md`'s `GET /api/admin/model-health`. Drop
   any expectation of a training-date field from `scoring_meta.json` itself;
   use file mtime instead.

---

## 4. RESOLVED: link initiation side (Open Question #1)

**Decision: add a real column, not a convention.** Agent 1's option (b)
("infer initiator from which endpoint was called") does not actually work,
because `SHGLenderLink` rows are read back later by the `decide` endpoint
with no memory of which endpoint created them — the authorization check at
decide-time needs a persisted fact, not a call-site inference. So:

**Schema change** (additive, one nullable-then-backfilled column, no
fabricated business data — this is workflow metadata, not a new business
fact):
```python
class SHGLenderLink(Base):
    ...
    initiated_by_role = Column(Enum("shg", "lender", name="link_initiator"), nullable=False, default="shg")
```
Existing rows (all created via the SHG-only `request_link` flow to date)
backfill to `"shg"` — this is accurate, not fabricated: today only SHGs can
create links (lenders had no auth to do so), so every existing row genuinely
was SHG-initiated.

**Behavior:**
- `POST /api/shgs/{id}/link-lender` (existing endpoint, SHG-authenticated,
  own id) → creates link with `initiated_by_role="shg"`.
- `POST /api/links` (existing generic endpoint, currently open) → becomes
  **lender-authenticated only**, `lender_id` forced from session → creates
  link with `initiated_by_role="lender"`.
- `POST /api/links/{id}/decide`:
  - if `link.initiated_by_role == "shg"` → only the **lender** session whose
    `lender_id == link.lender_id` may decide.
  - if `link.initiated_by_role == "lender"` → only the **SHG** session whose
    `shg_id == link.shg_id` may decide.
  - Admin: DENY (read-only scope, no moderation actions this pass — matches
    the confirmed admin scope; admin can still `GET /api/links` to view
    everything).
- Frontend consequence (Agent 4): a link row's "Approve/Reject" buttons
  render on the SHG dashboard only when `initiated_by_role == "lender"`, and
  on the lender dashboard only when `initiated_by_role == "shg"`. The other
  side sees the same row as "Awaiting their decision" (no buttons).

---

## 5. RESOLVED: server-side auth enforcement (Open Question #7)

**Decision: full server-side enforcement (Agent 1's option (b)), mandatory,
not optional.** The product owner's complaint — "everyone can access and see
anyone else's information" — is about the actual API being open, which a
frontend-only gate does not fix (anyone can `curl` the endpoints directly,
exactly as they can today). Concretely, for every router in
`app/routers/*.py`:

- Every endpoint that returns or mutates a specific individual's, SHG's, or
  lender's private data now requires a valid bearer token for an
  appropriate role (`Authorization: Bearer <token>`), verified against that
  role's session table server-side, **in addition to** any frontend route
  gating.
- Endpoints scoped to "your own X" ignore/override any client-supplied id
  for the *authorization* decision — they use the id resolved from the
  session. Where a client-supplied id already exists in the URL (e.g.
  `/api/individuals/{id}`) for routing convenience, the handler still
  validates it against the session's own id (or the session's *visibility*
  into that id, e.g. a lender viewing a linked SHG) and returns 403 if it
  doesn't match/isn't visible — never silently substitutes the session id
  for the URL id, so a mismatched request fails loudly instead of a lender
  guessing IDs and getting a filtered result that looks like success.
- 401 = no/invalid/expired token. 403 = valid token, wrong role or
  out-of-scope id. Both are distinguished so the frontend can show
  "please log in" vs. "you don't have access to this."
- The one deliberately-public endpoint is the new home-page highlights
  endpoint (§7 in REQUIREMENTS.md, §6 below) — anonymous visitors must be
  able to see it before logging in at all, per the product owner's explicit
  ask for home-page stories. This is a curated, small, aggregate/top-N feed
  (2-4 names + district + score delta, 3 SHG spotlights, 3 lender
  spotlights, district averages) — not a searchable directory, and is the
  one accepted exception to "no open data," directly authorized by the
  product owner's own requirement text ("add personal stories of
  borrowers... worth mentioning on front page").
- Full endpoint-by-endpoint auth requirement is enumerated in
  `docs/API_CONTRACT.md` — that table is binding, this section is the
  rationale.

---

## 6. Auth / credential design — adopted from REQUIREMENTS.md §3, confirmed feasible

Confirmed against `app/models.py` and `app/services/auth_service.py`:
PBKDF2-HMAC-SHA256 (200k iterations, stdlib `hashlib`, no new dependency),
opaque `secrets.token_urlsafe(32)` bearer tokens, 7-day TTL session rows —
this pattern is real, already running for borrowers, and trivially
replicable for lender/SHG. Adopted verbatim:

- **Migration is minimal and non-fabricating, confirmed**: `lenders.username`
  (nullable unique), `lenders.password_hash` (nullable), `shgs.username`
  (nullable unique), `shgs.password_hash` (nullable), plus 3 new session
  tables (`lender_sessions`, `shg_sessions`, `admin_sessions` — mirroring
  `individual_sessions` exactly) and the one `shg_lender_links.initiated_by_role`
  column from §4. No new business rows, no synthetic people/loans/scores.
  This is the smallest change that makes 4-way login possible.
- **Credential seeding**: one idempotent script (e.g.
  `app/ml/seed_role_credentials.py`), run once after `data_gen`, populating
  `username`/`password_hash` on existing `Lender`/`SHG` rows only. Username =
  slug of the entity's existing `name` column, lowercased, spaces→hyphens;
  on collision append `-{id}` (guaranteed unique since `id` is a primary
  key). Password = `password123` for every seeded row (same convention as
  borrowers, hashed with the existing `auth_service.hash_password`). Skip
  rows that already have a `password_hash` set, so reruns are safe.
- **Admin**: env-var credential (`ADMIN_USERNAME` / `ADMIN_PASSWORD`,
  default `admin` / `admin123`, documented in README same as the borrower
  demo password), hashed at process start via the same `hash_password`
  function, **not** a DB row — confirmed correct per REQUIREMENTS.md §3.4's
  own reasoning (no real "admin" business entity exists to attach a row to;
  inventing an `admin_users` table with a fabricated staff member would
  itself violate "no new fabricated data" more than a config-based single
  demo login). Use a real `AdminSession` DB table (not a signed cookie) for
  consistency with the other three roles and so the bearer-token pattern
  (and its 401/403 semantics) is uniform across all four `get_current_*`
  dependencies for Agent 5 to implement.
- **New endpoints**, one trio per role, shape identical to the existing
  borrower trio: `POST /api/auth/{role}/login`, `GET /api/auth/{role}/me`,
  `POST /api/auth/{role}/logout` for `role` in `{lender, shg, admin}`. Full
  request/response shapes in `docs/API_CONTRACT.md`.
- **CORS**: `app/main.py`'s `allow_origins=["*"]` stays unchanged. This is
  safe with the bearer-token pattern (no cookies, no `credentials: include`
  needed), and Agent 1's flag to "confirm this is still acceptable" is
  resolved: yes, no change needed — wildcard CORS + header-based bearer
  tokens (not cookie sessions) doesn't reintroduce a CSRF-style risk the way
  wildcard CORS + cookies would.
- **Username collision handling** (Open Question #5): confirmed the
  `-{id}` suffix is sufficient since `id` is always unique; no further
  design needed.

---

## 7. Lender reputation score — adopted unchanged from REQUIREMENTS.md §4

Formula, weights (`0.45 rate_component + 0.25 actual_offer_component + 0.20
activity_component + 0.10 reach_component`, rescaled to a 0-100 band around
50 = population average), and real-world framing (PSL/co-lending analogue)
are adopted **verbatim** — every input (`base_interest_rate`, `rate_offer`,
`serves_independents`, offer counts) is confirmed present on `Lender` /
`LoanOffer` in `app/models.py`. **Compute-on-read**, no caching column, per
Agent 1's recommendation — confirmed correct given only 6 lenders exist
today (Open Question #9, not a blocker). Exposed via
`GET /api/lenders/{id}/reputation` and embedded in
`GET /api/individuals/{id}/suggested-lenders` (§3 item 1 above).

---

## 8. Admin model/scoring health — corrected field list (fixes Open Question #4)

`artifacts/scoring_meta.json` was inspected directly (Agent 1 had flagged
this as unread). Its actual keys: `feature_columns` (list),
`impute_medians` (dict), `shap_expected_value` (float),
`trained_on_shg_linked_only` (bool), `min_repayment_events` (int),
`n_training_rows` (int), `holdout_accuracy` (float), `holdout_auc` (float).
**There is no training-date or model-version field in this file** — Agent
1's assumption that one existed was wrong; fixed here so Agent 5 doesn't
have to discover this mid-implementation:

- **Model version**: read from `CreditScore.model_version` (existing column,
  currently always `"v1"` per `data_gen`/`scoring_service`) — take the value
  from the most recently `calculated_date` row across all `credit_scores` as
  "current model version in production."
- **"Last computed" timestamp**: use `artifacts/scoring_meta.json`'s own
  filesystem `mtime` (`os.path.getmtime`, formatted as ISO date) — this is
  real filesystem metadata, not fabricated, and is an honest proxy for "when
  the model was last trained" given no field carries that explicitly.
- **Everything else** (`n_training_rows`, `holdout_accuracy`, `holdout_auc`,
  `trained_on_shg_linked_only`, `feature_columns`) is read straight from the
  file as-is.
- Combined with: `COUNT(DISTINCT credit_scores.individual_id)` vs
  `COUNT(individuals.id)` (scored vs total population) and a score
  distribution histogram (bucket the latest score per individual, reuse the
  `latest_scores_sql` CTE pattern already in `app/routers/dashboard.py`).
- Full response shape: `docs/API_CONTRACT.md` → `GET /api/admin/model-health`.

---

## 9. Front-page content plan — adopted unchanged from REQUIREMENTS.md §5

All four queries (borrower improvement stories, SHG spotlights, lender
spotlights, district-level improvement stats) were re-checked against
`app/models.py` during this pass and are valid as written, including the
correction Agent 1 already made themselves (use the raw-SQL repayment-rate
aggregate for SHG spotlights, not the `aggregate_repayment_rate` Python
`@property`, to avoid N+1 queries over 51 SHGs × their members × loans).
Adopted verbatim — see REQUIREMENTS.md §5.1–5.5 for the exact SQL and
narrative templates. Backing endpoint: `GET /api/dashboard/home-highlights`
(public, no auth — see §5 above for why this is the one accepted
exception).

**Privacy note for Agent 4/5 (not a REQUIREMENTS.md gap, just worth stating
explicitly given the "no PII exposure" spirit of this whole redesign):** the
home-page borrower stories show first+last `name`, `district`, and score
delta for up to 4 top-performing individuals. This is real data and is the
one place in the redesign where an individual's name is shown outside their
own login — it is intentional and explicitly requested by the product owner
("personal stories of borrowers"), not an oversight. No phone number,
income, loan amounts, or SHAP detail is exposed on the home page — only
name, district, SHG name (if linked), and the score delta narrative.

---

## 10. Remaining open items carried forward (not blockers, documented for Agent 5)

- **`min_score_threshold` gate** (Open Question #2): re-verified directly
  against `app/services/loan_request_service.py` and `matching_service.py`
  during this pass (not left to Agent 5) — `_lender_eligible_for_individual`
  and `eligible_lenders_for_individual` both correctly gate on SHG-link
  approval / `serves_independents` / `min_score_threshold`, consistent with
  §3 item 1's "suggested lenders" and §2.2 item 6's "eligible borrowers."
  No change needed; Agent 5 can build directly on these existing functions.
- **Anomaly flags stay admin-only this pass** (Open Question #8) — confirmed,
  no SHG/lender-scoped anomaly endpoint is built now. A future
  `GET /api/shgs/{id}/anomalies` is explicitly out of scope.
- **`POST /api/individuals/{id}/recompute-score`** (existing endpoint, not
  covered by Agent 1's matrix at all): this is a scoring-engine operation,
  not a role-owned business action. Resolved here: **admin-only**, since no
  other role should be able to trigger a recompute for an arbitrary
  individual, and it fits admin's one carved-out non-read-only exception
  (alongside `POST /api/anomalies/run`) as a compute/ops action rather than
  a data-mutation-of-record action.
