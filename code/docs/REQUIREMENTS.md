# CreditSetu — Role-Gated Redesign: Requirements Spec

Author: Agent 1 (Research). Consumers: Agent 2 (design system), Agent 3
(consolidation), Agent 4 (frontend), Agent 5 (backend), Agent 6 (QA/verify).
This document is the single source of truth for *what* to build; it does not
prescribe component code or pixel layout (that's Agent 2/4's job) and it does
not write endpoint code (Agent 5's job) — but every data field, query, and
access rule referenced by those agents should trace back to a line here.

## 0. Current-state summary (context for the rest of this doc)

Today literally everything is open. The only auth that exists is borrower
"My Score" (`Individual` + `IndividualSession`, plain PBKDF2 + bearer token,
`app/services/auth_service.py`, `app/routers/auth.py`) and it **doesn't gate
anything** — `/api/individuals/{id}` etc. are wide open regardless of login.
`Lender` and `SHG` models have **no credential columns at all** today.

Existing routers or note in `app/routers/`: `auth.py`, `individuals.py`,
`shgs.py`, `lenders.py`, `links.py`, `offers.py`, `loan_requests.py`,
`geo.py`, `anomalies.py`, `dashboard.py`. Existing frontend pages in
`frontend/src/pages/`: `HomeView.jsx`, `BorrowerView.jsx` (open search over
all individuals), `MyScoreView.jsx` (borrower self-service, existing —
mostly keep), `ShgLenderView.jsx` (combined SHG+lender tabs, open), `BankView.jsx`
(open portfolio dashboard). This redesign **removes** `BorrowerView.jsx`
(open borrower search) and splits `ShgLenderView.jsx` into two independently
login-gated pages; `MyScoreView.jsx` becomes the borrower's dashboard (kept
largely as-is, just renamed/re-routed); `BankView.jsx` becomes the read-only
admin page behind admin login.

---

## 1. Role definitions & data-access matrix

Four roles, each with its own login and its own dedicated post-login view.
No shared "browse everything" page survives. "Own" always means scoped by
the logged-in row's own foreign keys — never a client-supplied id that isn't
cross-checked against the session.

| Data category | Borrower | Lender | SHG | Admin |
|---|---|---|---|---|
| Own credit score + full history | ALLOW (own) | n/a | n/a | ALLOW (all, read-only) |
| Own SHAP explanation / improvement tips | ALLOW (own) | DENY | DENY | ALLOW (all, read-only) |
| Other individuals' scores/details | DENY | ALLOW only for members of SHGs linked to this lender, or independents if `serves_independents` (summary fields only, not full SHAP) | ALLOW only for own SHG's members (summary) | ALLOW (all, read-only) |
| Full population borrower search | DENY | DENY (scoped list only, see §2) | DENY | ALLOW (read-only) |
| Suggested/eligible lenders for self | ALLOW (own eligibility) | n/a | n/a | n/a |
| Full lender directory (read-only) | ALLOW | ALLOW (self + others, directory) | ALLOW | ALLOW |
| Own SHG info (group name, district, aggregate stats) | ALLOW (own SHG only, aggregate — not other members' individual rows beyond name+score already shown in existing member list pattern) | DENY (only via "linked SHGs" scoped list) | ALLOW (own, full: members, stats, links) | ALLOW (all, read-only) |
| Other SHGs' info | DENY | ALLOW (browse by district — summary only, per §Lender pages) | DENY | ALLOW (all) |
| Own loan requests/offers | ALLOW (own, existing flow, keep) | ALLOW (requests directed at them / offers they made) | DENY (SHGs don't hold loans, individuals do) | ALLOW (all, read-only) |
| SHG-lender link management (request/approve/reject) | DENY | ALLOW (approve/reject **incoming** requests to itself; a lender does not "request" a link to an SHG in the current linkage_service model without also updating that service — see Open Questions §6) | ALLOW (request links to lenders, see own link statuses) | ALLOW (view all links, read-only) |
| Anomaly flags | DENY | DENY | DENY (unless flag belongs to own member — out of scope this pass, see §6) | ALLOW (all) |
| District/geo clustering, model health, scoring-run metadata | DENY | DENY | DENY | ALLOW |
| Lender reputation score | ALLOW (visible on "suggested lenders" as a ranking signal, not raw admin detail) | ALLOW (own, plus how it compares — see §4) | DENY (not needed this pass) | ALLOW (all, read-only) |

Row-level enforcement principle for Agent 5: every scoped endpoint must
derive the "own" id from the authenticated session (borrower token →
individual_id; lender token → lender_id; SHG token → shg_id), **never** trust
a client-supplied id parameter for authorization — only use a supplied id to
select *which* related-but-visible-to-you resource to fetch (e.g. lender
viewing SHG X's members is fine only if SHG X is in that lender's approved
or pending link set).

---

## 2. Page inventory per role

### 2.1 Borrower (`/borrower/login` → `/borrower`)
One dashboard, replaces today's `MyScoreView.jsx` content, mounted at the
primary borrower route (old `/my-score`; old `/borrower` open-search route is
deleted). Sections:
1. Login form (phone + password) — reuse `POST /api/auth/login`, `auth_service.py`, unchanged.
2. Score card: current score, risk badge, base_component, hero figure — existing `_summary`/`_score_summary` shape, unchanged.
3. Score history chart — existing `GET /api/individuals/{id}/score-history`, unchanged, but must be re-scoped so a borrower token can only call it for their own id (currently open to any id — needs the `get_current_individual` dependency added, see §3).
4. "Why you got this score" SHAP waterfall — existing `score_explanation` array, unchanged data shape.
5. **NEW**: "Ways to improve your score" — derived client-side or server-side from `score_explanation`: take features with negative `shap_contribution`, map each to a canned improvement sentence (see feature→tip table below), sorted by |contribution| descending, top 3-5 shown.
6. **NEW**: "Suggested lenders for you" — ranked list of lenders the borrower is currently eligible for (reuses `loan_requests.eligible_lenders_for_individual` eligibility logic), ranked by effective rate (lowest `base_interest_rate` first) as the default, with lender reputation score (§4) shown as a secondary badge.
7. **NEW**: "All lenders" read-only directory — `GET /api/lenders`, unchanged, but presented without any other-borrower data alongside it.
8. **NEW**: "Your SHG" card (only rendered if `is_shg_linked`) — group name, district, `aggregate_repayment_rate`, `aggregate_attendance_rate`, member count — i.e. the existing `SHG._summary` fields minus the full `members` array (that stays SHG/Admin-only).
9. Loan requests / loan offers — existing tables and accept/reject/withdraw actions, unchanged.

Feature → improvement tip mapping (server-computed suggestion strings, keyed
by `feature_name` exactly as emitted by `features.py`/SHAP, used only when
`shap_contribution < 0`):
- `on_time_rate` low / `late_rate`, `missed_rate`, `partial_rate` high → "Pay your installments on time — missed or late payments are currently lowering your score the most."
- `avg_days_late` high → "When a payment is late, pay it as soon as possible — the number of days late matters, not just that it was late."
- `savings_regularity` / `savings_consistency` → "Save your expected amount consistently each month — irregular savings is pulling your score down."
- `attendance_rate` (SHG members only) → "Attend more of your SHG's meetings — your attendance record factors into your score."
- `shg_peer_repayment_rate` → "Your SHG group's overall repayment record affects your bootstrap score — encourage fellow members to stay current."
- `n_repayment_events` / `n_loans` low → "You don't have much repayment history yet — each on-time repayment you make going forward will move your score more."
- `has_bank_account` = 0 → "Linking a bank account is a positive signal lenders look for."
- fallback (any other negative feature) → generic "This factor is currently working against your score" wording using the raw feature name, humanized.

### 2.2 Lender (`/lender/login` → `/lender`)
New login (no prior lender auth existed). Dashboard replaces the "Lender
view" tab of today's `ShgLenderView.jsx`. Sections:
1. Login form (username + password — see §3 for credential scheme).
2. Own lender profile card (existing `_summary` fields + reputation score, §4).
3. "Browse SHGs by district" — `GET /api/shgs?district_id=`, existing endpoint, unchanged; lender can browse to decide who to request a link with (addresses "SHGs in different areas/districts").
4. "Your linked SHGs" — SHGs with an Approved (or Pending, shown separately) `SHGLenderLink` to this lender — reuse `approved_shgs_for_lender`, extend to also return Pending for a "requests awaiting your decision" sub-list, and add a pending-links-to-decide action using `POST /api/links/{id}/decide` scoped to `link.lender_id == current lender`.
5. "Eligible borrowers" — existing `GET /api/lenders/{id}/eligible-borrowers` (scoped server-side already, since eligibility inherently follows this lender's own links + `serves_independents`), capped top-25 pattern kept, propose-offer action kept.
6. "Loan requests directed at you" — existing `GET /api/loan-requests?lender_id=`, existing accept/reject actions, kept as-is but scoped so `lender_id` must equal the session's lender.
7. "Your offers" — existing `GET /api/offers?lender_id=`, unchanged, scoped to session.
8. **NEW**: Reputation/credit score panel — see §4 for formula; shown with a one-line explanation of how it's computed and where this lender ranks among all lenders (e.g. "3rd of 6, based on your rate relative to the platform average").

### 2.3 SHG (`/shg/login` → `/shg`)
New login. Dashboard replaces the "SHG view" tab of today's
`ShgLenderView.jsx`, scoped to exactly one SHG (the logged-in one — no SHG
picker). Sections:
1. Login form (username + password — see §3).
2. Own group card — existing `SHG._summary` fields (name, village, district, formed_date, total_members, n_members_actual, avg_member_score, aggregate_repayment_rate, aggregate_attendance_rate).
3. Members table — existing `shg.members` list (id, name, score, risk_category) from `GET /api/shgs/{id}` — same shape already returned, just scoped so the id must equal the session's own shg_id.
4. Linked lenders — existing `GET /api/shgs/{id}/lenders`, unchanged shape, scoped to own id.
5. Request a new lender link — existing `POST /api/shgs/{id}/link-lender`, scoped to own id — reuses `linkage_service.request_link`.
6. Approve/reject a lender-initiated pending link — same `POST /api/links/{id}/decide` action used by lenders today (currently unauthenticated and callable by anyone); needs to be split by *who initiated* so the SHG can decide links a lender proactively requested (see Open Question in §6 — today `request_link` doesn't record which side initiated).

### 2.4 Admin (`/admin/login` → `/admin`)
New login. Platform-wide **read-only** oversight, no account or moderation
actions this pass (confirmed by product owner). Content = today's
`BankView.jsx` plus additions:
1. Login form (username + password — see §3).
2. Portfolio overview — existing `GET /api/dashboard/summary`, unchanged.
3. Loan status chart, district trust heatmap (`GET /api/geo/districts`) — unchanged.
4. Anomaly flags — existing `GET /api/anomalies`, `POST /api/anomalies/run` (this is a compute action, not a data-mutation-of-record action, so it stays available to admin; it's the one exception to "read-only" and is already how the existing BankView works).
5. **NEW**: All-borrowers / all-SHGs / all-lenders browse — this is where the *old* open `BorrowerView.jsx` search and the *old* open `ShgLenderView.jsx` browse lists move to. Reuses the exact same existing endpoints (`GET /api/individuals?search=`, `GET /api/shgs`, `GET /api/lenders`) — nothing new server-side, just now gated behind admin auth instead of being open to the world.
6. **NEW**: Model/scoring health — number of individuals scored vs total population (`COUNT(DISTINCT credit_scores.individual_id)` vs `COUNT(individuals.id)`), score distribution (histogram from `credit_scores` latest-per-individual, reuse the dashboard's `latest_scores_sql` CTE pattern), and last-training-run metadata read from `artifacts/scoring_meta.json` (Agent 5: confirm this file's exact schema when implementing — inspect `app/ml/train_scoring_model.py`'s save step; not read by this agent in full, flagged in §6).

---

## 3. Auth / credential design for all four roles

All four roles share the same mechanism family already proven for borrowers
— plain PBKDF2-HMAC-SHA256 password hashing (`auth_service.hash_password` /
`verify_password`, 200k iterations, no new dependency) and an opaque
bearer-token session row per role, 7-day TTL (`IndividualSession` pattern).
**Do not introduce JWT or a third-party auth library** — stay consistent
with the documented "deliberately minimal" demo-auth philosophy in
`auth_service.py`'s own docstring.

### 3.1 Borrower — unchanged
Login = phone number, password = `password123` for every seeded individual.
`POST /api/auth/login`, `IndividualSession`, `get_current_individual` — all
reused verbatim. **New requirement**: every endpoint returning individual-
specific data (`/api/individuals/{id}`, `/score-history`, `/loan-requests`
filtered by `individual_id`, `/offers` filtered by `individual_id`) must,
when called with a borrower's bearer token, refuse to serve an id other than
the token's own `individual_id` — today these are open by id. Public,
role-agnostic reads (full lender directory) stay open.

### 3.2 Lender — new
**Schema migration** (additive only, no data loss, no fabricated business
data — satisfies "no need to create new data"):
```python
class Lender(Base):
    ...
    username = Column(String(100), nullable=True, unique=True)   # NEW
    password_hash = Column(String(150), nullable=True)            # NEW
```
Add a `LenderSession` table, identical shape to `IndividualSession`
(`id`, `lender_id` FK, `token`, `created_at`, `expires_at`).

**Credential seeding** (one-off script, e.g. `app/ml/seed_role_credentials.py`,
run once after `data_gen`/before first login — does not touch `data_gen.py`'s
synthetic-data generation, only adds credentials to rows that already exist):
- `username` = slugified lender name, lowercased, spaces→hyphens, e.g.
  `"Bharat Rural Bank"` → `bharat-rural-bank`. If a collision occurs (won't
  happen with 6 lenders but guard anyway), append `-{id}`.
- `password` = same demo convention as borrowers: `password123`, hashed with
  the existing `auth_service.hash_password`.
- Idempotent: skip any lender that already has a `password_hash` set, so
  re-running the script after a partial run or after `data_gen` reseeds does
  the right thing without duplicating work.

New endpoints: `POST /api/auth/lender/login` (username+password →
`{token, lender_id, name}`), `GET /api/auth/lender/me`, `POST
/api/auth/lender/logout` — same shapes as the borrower auth trio, parallel
`get_current_lender` dependency reading a `Lender-Session`-style bearer token
(reuse `authorization: Bearer <token>` header convention).

### 3.3 SHG — new
Same pattern as lender:
```python
class SHG(Base):
    ...
    username = Column(String(100), nullable=True, unique=True)   # NEW
    password_hash = Column(String(150), nullable=True)            # NEW
```
New `SHGSession` table (same shape). Seeding script (same script as §3.2,
one pass over both tables): `username` = slugified SHG name + a short
disambiguator since SHG names are generated as `"{first_name} {suffix}
Group"` and could collide across 51 rows — use `slug(name)-{district_id}` or
just `slug(name)-{id}` to guarantee uniqueness (51 SHGs, collisions on first
name + suffix combo are plausible with `fake.first_name()`). Password =
`password123`, same hashing. Idempotent skip-if-already-set, same as lenders.

Endpoints: `POST /api/auth/shg/login`, `GET /api/auth/shg/me`, `POST
/api/auth/shg/logout` — parallel to the above.

### 3.4 Admin — new
No natural "row" to attach credentials to (admin isn't a business entity in
the schema) — simplest honest option for a demo: a small **hardcoded/env-
configured** single admin credential, not a database row, since inventing an
`Admin` table with fabricated staff would violate "no new fabricated data"
more than a single demo login would. Concretely:
- `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` (or a single `ADMIN_PASSWORD`
  hashed at process start) read from environment variables in `app/config.py`,
  defaulting to `admin` / `admin123` for the demo (documented in README, same
  spirit as the borrower demo password).
- A lightweight in-memory or DB-light `AdminSession` table (same shape as the
  others, for consistency and so restart doesn't silently invalidate an
  active demo session across a `--reload`) — Agent 5 may instead choose a
  short-lived signed cookie if that's materially simpler; either is
  acceptable, this is the one role where the "no fabricated data" constraint
  doesn't apply (there's no admin business entity to seed).
- Endpoints: `POST /api/auth/admin/login`, `GET /api/auth/admin/me`, `POST
  /api/auth/admin/logout`.

### 3.5 Summary of new tables/columns for Agent 5
- `lenders.username` (new, nullable, unique), `lenders.password_hash` (new, nullable)
- `shgs.username` (new, nullable, unique), `shgs.password_hash` (new, nullable)
- `lender_sessions` (new table, mirrors `individual_sessions`)
- `shg_sessions` (new table, mirrors `individual_sessions`)
- `admin_sessions` (new table, mirrors `individual_sessions`) — or cookie, per above
- One seeding script that populates the two new username/password_hash column pairs on existing rows only (no new business rows), run after `data_gen`.

---

## 4. Lender reputation/credit score — spec

**Real-world analogue** (for Agent 3/stakeholders to cite): India's priority-
sector-lending (PSL) and co-lending-scheme frameworks give banks/NBFCs
regulatory and reputational credit for lending on favorable terms to
under-served borrowers — RBI's PSL shortfall mechanism and the co-lending
model (RBI circular on co-lending arrangements, 2020) both effectively
reward the lending institution (via priority classification, or via the
originating NBFC's ability to attract bank co-lending partners) for offering
credit at *competitive, below-market rates* to the priority segment rather
than purely maximizing yield. Credit Guarantee Fund Trust for Micro and
Small Enterprises (CGTMSE) similarly extends better guarantee cover to
lenders who price responsibly. In fintech/marketplace platforms, this
pattern is commonly reproduced as a **"lender reputation" or "trust" score**
gamifying rate competitiveness and responsiveness (seen in P2P lending
marketplaces like Prosper/LendingClub-style investor-facing "activity"
scores, and in B2B marketplace "seller score" patterns) — same idea, no
external data needed, purely a function of the platform's own observed
pricing behavior.

**Formula (computable from existing schema only — no new tables of fake
data, one small computed/cached number per lender):**

Let `pop_avg_rate` = average `base_interest_rate` across all lenders (or, for
a sharper signal, average `rate_offer` across all `LoanOffer` rows actually
made platform-wide, since that reflects real pricing behavior, not just
listed base rate — prefer this when there is enough offer volume, fall back
to `base_interest_rate` average if a lender has made zero offers).

For lender L:
```
rate_component = (pop_avg_rate - L.base_interest_rate) / pop_avg_rate
# positive when L is cheaper than the population average, negative when pricier
# clip to [-1, 1] to bound the effect of an extreme outlier

actual_offer_component = 0
if L has >=1 LoanOffer:
    L_avg_offer_rate = avg(rate_offer for offers where lender_id = L.id)
    actual_offer_component = (pop_avg_rate - L_avg_offer_rate) / pop_avg_rate  # clipped to [-1,1]

activity_component = min(1.0, n_offers_by_L / max_offers_by_any_lender)
# rewards lenders who actually participate in the marketplace, not just list a low rate and do nothing

reach_component = 1 if L.serves_independents else 0
# small bonus for extending credit to the harder-to-score, unlinked population — mirrors PSL's
# "credit to under-served segments" incentive

reputation_raw = (
    0.45 * rate_component
    + 0.25 * actual_offer_component
    + 0.20 * activity_component
    + 0.10 * reach_component
)
reputation_score = round(50 + 50 * reputation_raw)   # rescale to a 0-100 display band, 50 = population-average pricing
reputation_score = clip(reputation_score, 0, 100)
```
All inputs (`base_interest_rate`, `rate_offer`, `serves_independents`, offer
counts) already exist on `Lender` / `LoanOffer`. This can be computed on
read (6 lenders, cheap) or cached — Agent 5's call; no migration is strictly
required, but if cached, add a nullable `lenders.reputation_score` column
and recompute it whenever an offer is created/decided (simplest: recompute
on every read of the lender list/detail endpoint given the tiny lender
count — avoids a stale-cache class of bugs for a 6-row table).

Display: show as a 0-100 badge ("Lender reputation: 78/100 — rates below the
platform average, active in the marketplace") on the lender's own dashboard
(§2.2) and as a secondary sort/ranking signal on the borrower's "suggested
lenders" list (§2.1).

---

## 5. Front-page redesign — content plan

All content below is generated from real rows in `data/microfin.db` at
request time (or cached at startup) — no fabricated names, districts, or
numbers. Backend: add these as new fields on `GET /api/dashboard/summary`
(or a new `GET /api/dashboard/home-highlights` endpoint — Agent 5's choice,
recommend the latter to avoid bloating the existing summary payload every
caller pays for).

### 5.1 "Real borrower" improvement stories (2-4 cards)
Query: for each individual with >= 3 `credit_scores` rows, compute
`score_delta = latest.score - earliest.score` ordered by `calculated_date`.
Rank all individuals by `score_delta` descending, take the top 4 with
`score_delta > 0`, biased toward diversity (pick from different districts if
possible — simple approach: iterate the ranked list and skip a district
already used, until 4 are picked or the list is exhausted).
```sql
WITH ranked AS (
  SELECT individual_id,
         MIN(calculated_date) AS first_date, MAX(calculated_date) AS last_date,
         COUNT(*) AS n_scores
  FROM credit_scores GROUP BY individual_id HAVING COUNT(*) >= 3
),
first_last AS (
  SELECT r.individual_id,
    (SELECT score FROM credit_scores cs WHERE cs.individual_id = r.individual_id
       ORDER BY calculated_date ASC LIMIT 1) AS first_score,
    (SELECT score FROM credit_scores cs WHERE cs.individual_id = r.individual_id
       ORDER BY calculated_date DESC LIMIT 1) AS last_score
  FROM ranked r
)
SELECT i.id, i.name, i.district_id, d.name AS district, i.shg_id, s.name AS shg_name,
       fl.first_score, fl.last_score, (fl.last_score - fl.first_score) AS delta
FROM first_last fl
JOIN individuals i ON i.id = fl.individual_id
JOIN districts d ON d.id = i.district_id
LEFT JOIN shgs s ON s.id = i.shg_id
WHERE fl.last_score > fl.first_score
ORDER BY delta DESC
LIMIT 20;  -- overfetch, then diversify by district in Python, slice to 4
```
Narrative template (fill with real values only): *"{name}, {district}
{', a member of ' + shg_name if shg_linked else '(independent borrower)'} ,
raised their credit score from {first_score} to {last_score} — a {delta}-point
improvement — by staying current on repayments."* (Do not claim a specific
behavioral cause beyond what `score_explanation`'s top positive feature for
their latest score actually says — Agent 5 should join `score_explanations`
for the latest `credit_scores` row of each selected individual and cite the
single highest positive `shap_contribution` feature name, humanized, instead
of a generic "staying current" if a stronger real signal exists, e.g.
savings regularity.)

### 5.2 SHG spotlights
```sql
SELECT s.id, s.name, s.village, d.name AS district, s.total_members
FROM shgs s JOIN districts d ON d.id = s.district_id
WHERE s.status = 'Active';
-- then rank in Python by SHG.aggregate_repayment_rate (a computed @property,
-- not a column -- cannot ORDER BY it in SQL directly; either compute it for
-- all active SHGs in Python and sort, or replicate the aggregate as a raw
-- SQL aggregate over repayment_events joined through loans/individuals)
```
Equivalent raw-SQL aggregate version (for a single query instead of N+1
property access):
```sql
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
HAVING COUNT(re.id) >= 10   -- avoid spotlighting a group with 1-2 data points
ORDER BY repayment_rate DESC
LIMIT 3;
```
Show: group name, village/district, member count, repayment rate as a %.

### 5.3 Lender spotlights
Rank by activity (existing schema, no property needed):
```sql
SELECT l.id, l.name, l.type, l.base_interest_rate,
       COUNT(DISTINCT lo.id) AS n_offers,
       COUNT(DISTINCT sl.id) AS n_shg_links
FROM lenders l
LEFT JOIN loan_offers lo ON lo.lender_id = l.id
LEFT JOIN shg_lender_links sl ON sl.lender_id = l.id AND sl.status = 'Approved'
GROUP BY l.id
ORDER BY (n_offers + n_shg_links) DESC
LIMIT 3;
```
Show: lender name, type, number of active SHG partnerships, number of
offers made, and reputation score (§4) as the highlighted stat.

### 5.4 District-level improvement stats
Average score delta per district, using the same first/last-score logic as
§5.1 but grouped by district instead of picked individually:
```sql
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
ORDER BY avg_delta DESC;
```
(SQLite supports window functions since 3.25 — fine here since the project
already uses SQLite 3.x via SQLAlchemy; if Agent 5 hits a version issue,
equivalent MIN/MAX-by-date correlated subqueries per district work too, same
pattern as §5.1.) Show as a small bar/table: top 3-5 districts by average
score improvement, each with borrower count so a 2-person district doesn't
look falsely impressive (require `n >= 5` before including a district, same
"don't spotlight noise" principle as §5.2's `HAVING COUNT(re.id) >= 10`).

### 5.5 UI sections for Agent 4 (HomeView.jsx redesign)
Keep the existing hero + "How the scoring works" 4-step section (still
accurate) and the stat tiles. Replace the current `EXPLORE_CARDS` (which
link to now-removed/regated pages) with four cards linking to
`/borrower/login`, `/lender/login`, `/shg/login`, `/admin/login`. Add three
new sections below, each backed by §5.1-5.4:
1. "Real stories, real progress" — 2-4 cards from §5.1.
2. "This month's standouts" — two side-by-side lists, SHG spotlights (§5.2) and lender spotlights (§5.3).
3. "Where trust is growing" — small table or bar chart of district-level average score improvement (§5.4), reusing the existing `DistrictHeatmap`-style component pattern already in the codebase (`frontend/src/components/DistrictHeatmap.jsx`) rather than inventing a new chart primitive.

---

## 6. Open questions / risks for Agent 3 to resolve

1. **Link initiation side is not tracked today.** `SHGLenderLink` has no
   `initiated_by` field — `request_link()` can be called by either an SHG or
   (once lender auth exists) a lender, but the row looks identical either
   way. For §2.3 item 6 and §2.2 item 4 to correctly show "awaiting *your*
   decision" vs "you're waiting on them," either (a) add an
   `initiated_by_role` enum column (`'shg'` / `'lender'`) to
   `SHGLenderLink`, or (b) adopt a simpler convention: whichever side did
   *not* call `POST /api/shgs/{id}/link-lender` (SHG-initiated, existing
   endpoint) must be the one to decide — meaning `POST /api/links` (the
   generic, currently-unauthenticated creation endpoint in `links.py`) should
   become the lender-initiated path once lender auth exists, and `decide`
   should be restricted to the *other* role from whichever created it. Agent
   3 must pick one and hand Agent 5 an unambiguous rule.
2. **`min_score_threshold` gate on loan requests.** `loan_request_service`
   was not read in full by this agent (out of scope for the login redesign)
   — Agent 5 should re-verify its eligibility logic matches §2.1 item 6/7
   and §2.2 item 6 scoping assumptions before wiring the UI.
3. **Admin has no natural schema-backed identity.** §3.4 proposes an
   env-var/config credential rather than a DB row. Confirm with the product
   owner this is acceptable, or decide whether a minimal `admin_users` table
   (still not "business data," just one operator row) is preferred for
   consistency with the other three roles' session-table pattern.
4. **`artifacts/scoring_meta.json` schema** referenced in §2.4 item 6 was
   not inspected by this agent — Agent 5 must open
   `app/ml/train_scoring_model.py`'s save step to confirm exact field names
   (e.g. training date, model version, feature list) before wiring the
   "last training run" admin panel.
5. **SHG/Lender username collisions.** With only 51 SHGs and 6 lenders,
   collisions are unlikely but not impossible given `fake.first_name()`
   reuse in SHG names (`app/ml/data_gen.py` line ~153) — the seeding script
   must handle the collision case (append `-{id}`) rather than fail the
   whole seeding run.
6. **CORS / frontend routing.** `app/main.py` currently allows `*` origins
   — fine for the demo, but Agent 5 should confirm this stays acceptable
   once four separate login flows exist (no change recommended here, just
   flagging it's unchanged).
7. **Existing `/api/individuals`, `/api/shgs/{id}`, etc. staying reachable
   without auth for Admin's browse pages (§2.4.5) vs. needing to be locked
   down for Borrower/Lender/SHG contexts** creates a tension: the same
   endpoint must be either (a) left open and *only* the frontend routes
   gated (weak — anyone can still hit the API directly), or (b) made to
   require *some* valid session (any of the four roles) plus per-role
   filtering logic inside the handler. This spec assumes (b) — real access
   control at the API layer, matching the README's own "Next steps" call to
   fix this — Agent 3/5 should confirm this is the intended bar rather than
   a purely cosmetic frontend-only gate, since the product owner's stated
   goal ("four separate, role-gated views") reads as a real security
   requirement, not just a UX reorganization.
8. **Anomaly flags and SHG/lender visibility** — the matrix in §1 denies
   SHG/Lender access to anomaly flags this pass since the product owner only
   confirmed admin-level exposure; if a later pass wants an SHG to see
   flags on its own members, that's a new endpoint (`GET
   /api/shgs/{id}/anomalies`, filtering `AnomalyFlag.individual_id IN (shg
   member ids)`) — not built now, flagged for later.
9. **Reputation score caching** — §4 recommends compute-on-read given the
   tiny lender count (6); if the population of lenders is later scaled up
   this should move to a stored, periodically-recomputed column. Not a
   blocker now.
