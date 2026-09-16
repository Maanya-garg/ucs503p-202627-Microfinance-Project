# CreditSetu — Payments & Targeted Requests Requirements (Agent 1 research)

Author: Agent 1 (research/spec only, no application code written). Companion
to `docs/SPEC.md` + `docs/API_CONTRACT.md` (unchanged by this doc — Agent 3
will merge the relevant pieces of this file into those two). Do not confuse
this file with `docs/REQUIREMENTS.md` (the original Agent 1 doc from the
4-role redesign) — this is a separate, additive feature set.

Scope: three product-owner-requested features —
1. Targeted (single-lender) loan requests, alongside existing broadcast.
2. A real borrower-initiated repayment action.
3. A dummy payment-gateway modal with a wallet balance and insufficient-funds
   gating rule across all of a borrower's active loans.

Everything below was checked directly against `app/models.py`,
`app/services/loan_request_service.py`, `app/routers/loan_requests.py`,
`app/routers/individuals.py`, `app/ml/data_gen.py`, `app/ml/migrate_auth.py`,
`app/schemas.py`, `frontend/src/pages/dashboards/BorrowerDashboard.jsx`, and
`frontend/src/components/ScoreHistoryChart.jsx`.

---

## 1. Schema changes

### 1.1 `Individual.wallet_balance`

```python
# app/models.py, class Individual
wallet_balance = Column(Float, nullable=True)
```

Nullable so existing rows don't need an immediate value (mirrors
`password_hash`'s own nullable-then-backfilled pattern in this codebase).
Treat `NULL` as `0.0` everywhere it's read (`ind.wallet_balance or 0.0`), so
no code path needs a hard NOT NULL migration/backfill-before-use ordering.

**Seeding rule (non-arbitrary, tied to `monthly_income`):**

```
wallet_balance = round(monthly_income * 1.5, 2)
```

Rationale: `monthly_income` already exists on every `Individual` row (used
today as a scoring feature and shown on the borrower card). One and a half
months of income is a defensible "what a borrower plausibly has on hand/in a
linked bank-like wallet right now" figure — big enough that most borrowers
can clear at least one EMI cycle (EMIs are a fraction of monthly income by
construction in `data_gen.py`'s loan sizing), small enough that the
insufficient-funds state in feature 3 is still reachable for borrowers with
multiple simultaneous active loans, which is what makes that UI state worth
building. Do not use a random/unexplained constant — this multiple must be
called out here specifically because the product owner's constraint said so.

Rows with `monthly_income IS NULL` (possible per the nullable column) seed to
`0.0` — an unknown-income borrower gets a conservative empty wallet rather
than a fabricated guess.

### 1.2 Migration script

New file `app/ml/migrate_payments.py`, same idempotent pattern as
`app/ml/migrate_auth.py` (raw `sqlite3` ALTER, guarded by `PRAGMA
table_info` check, safe to re-run):

```python
def add_wallet_column():
    con = sqlite3.connect(_sqlite_path())
    cur = con.cursor()
    if not _column_exists(cur, "individuals", "wallet_balance"):
        cur.execute("ALTER TABLE individuals ADD COLUMN wallet_balance FLOAT")
        print("  + individuals.wallet_balance")
    con.commit()
    con.close()

def seed_wallet_balances():
    """Only rows where wallet_balance IS NULL -- safe to re-run, never
    overwrites a balance that's already moved from a real payment."""
    db = SessionLocal()
    n = 0
    for ind in db.query(Individual).filter(Individual.wallet_balance.is_(None)).all():
        income = ind.monthly_income or 0.0
        ind.wallet_balance = round(income * 1.5, 2)
        n += 1
    db.commit()
    print(f"  seeded wallet_balance for {n} individual(s)")
```

Run with `python -m app.ml.migrate_payments`, documented in README next to
the existing `migrate_auth` invocation. **Critical idempotency note for
Agent 5**: the `IS NULL` filter is what makes this safe to re-run after
borrowers have already made live payments — a second run must never reset a
wallet balance back to `1.5 * monthly_income` and wipe out real payment
history. This is why seeding is gated on `IS NULL`, not "always set."

### 1.3 No other schema changes

Repayment recording reuses the existing `RepaymentEvent` table as-is (no new
columns) — see §2. Loan state reuses `Loan.outstanding_balance` and
`Loan.status` as-is.

---

## 2. "Amount due this cycle" formula and On_Time/Late rule

### 2.1 Problem

`RepaymentEvent` rows today only come from `app/ml/data_gen.py`'s synthetic
generator, which computes a real EMI and walks calendar months from
`disbursement_date` (`data_gen.py` lines ~241, ~258-261):

```python
emi = round(principal * (1 + rate / 100 * tenure / 12) / tenure, 2)
...
for emi_no in range(1, tenure + 1):
    due = disb + timedelta(days=30 * emi_no)
    if due > TODAY:
        break  # future EMI, not due yet -- no event row
```

That "skip if not due yet" behavior is correct for offline synthetic
generation but is exactly what must **not** gate a live demo action — a real
demo user hitting "repay" on a loan disbursed five minutes ago must be able
to pay something right now, per the product owner's explicit requirement.

### 2.2 EMI formula (reused, not reinvented)

Reuse `data_gen.py`'s own EMI formula verbatim, computed on demand from the
loan's own columns (no dependency on calendar elapsed time):

```
emi = round(
    loan.principal_amount * (1 + loan.interest_rate / 100 * loan.tenure_months / 12)
    / loan.tenure_months,
    2,
)
```

This is simple-interest-amortized, matches what the synthetic history
already used, and is trivially computable for a loan disbursed today.

### 2.3 "This cycle" = the next unpaid installment number

```
n_paid = count of RepaymentEvent rows for this loan with status in
         ("On_Time", "Late") — i.e. events that resulted from a real or
         synthetic completed payment (excludes "Missed"/"Partial", see §2.5)
cycle_number = n_paid + 1          # 1-indexed, the next EMI due
amount_due_this_cycle = emi        # flat EMI amount (see note below)
```

Using `count of existing repayment_events` (as the constraint requires) as
the cycle pointer means "this cycle" is always well-defined regardless of
real calendar time — a loan disbursed today with 0 repayment events has
`cycle_number = 1` and is immediately payable; a loan with 3 prior synthetic
`On_Time` events has `cycle_number = 4`. This satisfies "always computable
and payable on demand."

If `cycle_number > tenure_months` (all installments already covered — should
coincide with `Loan.status == "Closed"`, see §2.6), the loan is not payable;
the payment-due endpoint (§3.2) omits it from the payable list.

**Note on partial-payment carry-forward (kept simple, flagged as an open
question in §5):** this cycle's `amount_due` is always the flat `emi`, not
`emi` minus any prior partial shortfall — the existing `RepaymentEvent`
schema has no running-shortfall concept and none is invented here. A
borrower who under-pays (see §3.3, not offered by this UI at all — payments
in this feature are always for the full EMI, see §4.3) is out of scope for
"partial" in this pass; the live payment endpoint only ever creates
`On_Time`/`Late` events for the full EMI amount.

### 2.4 Theoretical due date (for On_Time/Late only, not for gating payability)

```
theoretical_due_date = loan.disbursement_date + timedelta(days=30 * cycle_number)
```

Same 30-day-per-installment convention as `data_gen.py`, so a live loan's
"cycle 1 due date" lines up with what the synthetic generator would have
produced if it had walked forward that far. This date is used **only** to
classify the resulting `RepaymentEvent.status`, never to block the payment
itself (see §2.2's "on demand" requirement) — a borrower can always pay
today, but paying after `theoretical_due_date` has passed records as `Late`.

### 2.5 On_Time / Late decision rule

```
today = date.today()
if today <= theoretical_due_date:
    status = "On_Time"
    days_late = 0
else:
    status = "Late"
    days_late = (today - theoretical_due_date).days
```

`payment_date = today`, `amount_paid = emi`, `amount_due = emi`. This is the
same two-way split `data_gen.py` uses for its non-missed events (it also
generates `"Partial"`/`"Missed"` for pure synthetic-history realism, but a
live user-initiated payment action is always a completed payment for the
full EMI by construction of this feature, so only `On_Time`/`Late` are ever
written by the live path — `Partial`/`Missed` remain generator-only).

### 2.6 Loan state updates on a successful payment

```
loan.outstanding_balance = max(0.0, loan.outstanding_balance - emi)
if cycle_number >= loan.tenure_months:   # this was the final installment
    loan.status = "Closed"
```

`outstanding_balance` is decremented by the flat EMI each payment (consistent
with how `data_gen.py` never actually decrements `outstanding_balance` per
event today — inspect confirmed it sets `outstanding_balance =
principal_amount` at loan creation and never updates it from repayment
events; this feature introduces the first real decrement logic, which is a
genuine behavior addition Agent 5 should be aware of, not a bug to match).
Only `"Active"` loans are payable; `"Closed"/"Defaulted"/"Written_Off"` loans
are excluded from the payment-due summary (§3.2).

### 2.7 Score recompute after payment

Immediately after a successful payment, call the existing
`compute_and_store_score(db, individual, notes="Recomputed after live repayment")`
from `app/services/scoring_service.py` (same function
`POST /api/individuals/{id}/recompute-score` already uses) on the paying
borrower, in the **same transaction/commit** as the payment, so the borrower
dashboard's next fetch of `GET /api/individuals/{id}` already reflects the
new score — no separate "please recompute" step, per the product owner's
"visibly move the credit score afterward" requirement.

---

## 3. New/changed API endpoints

All three new endpoints live in a new router file `app/routers/payments.py`
(`prefix="/api/payments"`), registered in `app/main.py` alongside the
existing routers. Auth follows the established `get_current_individual` /
`get_current_actor` pattern from `app/routers/auth.py` — never a
client-supplied individual id for authorization.

### 3.1 (a) Targeted loan request

**`POST /api/loan-requests`** (existing endpoint, extended — not replaced).

Request body (extend `LoanRequestIn` in `app/schemas.py`):

```python
class LoanRequestIn(BaseModel):
    individual_id: int
    principal: float
    tenure: int
    purpose: str | None = None
    target_lender_id: int | None = None   # NEW, optional
```

Schema change for `LoanRequest` (`app/models.py`):

```python
target_lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=True, index=True)
```

Migration: add via the same `app/ml/migrate_payments.py` script (§1.2),
nullable, no backfill needed (every existing row is a broadcast request by
definition, `NULL` is the correct historical value).

**Behavior:**
- `target_lender_id is None` (default) → existing broadcast behavior,
  unchanged, visible to every eligible lender via `requests_for_lender`.
- `target_lender_id` set → `loan_request_service.create_request` must
  validate that lender is currently in
  `eligible_lenders_for_individual(db, individual)` (the same list the
  borrower is shown by `GET /api/loan-requests/eligible-lenders` — reuse
  that function, don't reimplement eligibility) — if not eligible, raise
  `LoanRequestError` → `400`, message e.g. "That lender isn't currently
  eligible for you — pick from your eligible-lenders list." Store the id on
  the new `LoanRequest.target_lender_id` column.

**Visibility/decision change** (`loan_request_service.requests_for_lender`
and `.decide`/`approve_request`/`decline_request`):
- In `requests_for_lender`, a `Pending` request with `target_lender_id` set
  is only included in a lender's queue if `target_lender_id ==
  lender_id` (in addition to the existing eligibility/decline-list checks
  already there) — other eligible lenders never see it at all, not even in a
  read-only way, matching "direct the request at just that lender."
- `approve_request` / `decline_request`: no change needed beyond the above
  filtering — the existing eligibility re-check in `approve_request`
  (`_lender_eligible_for_individual`) already re-validates at decide-time
  regardless of targeting, which is correct defense-in-depth (an SHG link
  could be revoked between request and decision).
- `_summary()` in `app/routers/loan_requests.py` gains `target_lender_id`
  and `target_lender_name` fields (mirrors the existing
  `decided_by_lender_id`/`decided_by_lender_name` pair).

**Response** (`_summary(req)`): unchanged shape plus the two new fields
above.

### 3.2 (b) Borrower's payment-due summary

**`GET /api/payments/due-summary`** (NEW)

Auth: borrower (own) or admin, same `get_current_actor` pattern used by
`GET /api/loan-requests/eligible-lenders`. Query param
`individual_id` (must equal `actor.individual.id` for a borrower token, 403
otherwise; free for admin).

Response:

```json
{
  "individual_id": 42,
  "wallet_balance": 18500.0,
  "total_due_this_cycle": 7200.0,
  "sufficient_funds": true,
  "loans": [
    {
      "loan_id": 101,
      "principal_amount": 30000.0,
      "interest_rate": 14.0,
      "tenure_months": 12,
      "outstanding_balance": 22500.0,
      "cycle_number": 4,
      "tenure_months_total": 12,
      "amount_due_this_cycle": 2700.0,
      "theoretical_due_date": "2026-09-10",
      "will_be_late": true
    }
  ]
}
```

- `loans`: every `Active` loan belonging to this individual, each carrying
  its own `amount_due_this_cycle` per §2.2–2.4 (computed fresh on read, not
  stored).
- `total_due_this_cycle` = sum of every loan's `amount_due_this_cycle`.
- `sufficient_funds` = `wallet_balance >= total_due_this_cycle` — computed
  once, across **all** active loans, exactly the rule the product owner
  specified ("if wallet balance is less than the TOTAL amount due across all
  active loans ... should not be able to pay ANY of their loans"). The
  frontend gateway modal (§4.3) reads this single flag to decide whether to
  show the insufficient-funds state or the loan-picker state — no per-loan
  affordability flag is exposed, deliberately, so the frontend can't
  accidentally let one loan through when the aggregate is short.
- `will_be_late`: `today > theoretical_due_date` for that loan, so the
  frontend can show "paying now will record as Late" before the borrower
  confirms.

This endpoint is what the payment-gateway modal calls **first**, before any
payment, to render wallet balance + amount due + the loan picker.

### 3.3 (c) Make a payment on one loan

**`POST /api/payments/pay`** (NEW)

Auth: borrower only (`get_current_individual`), same as `POST
/api/loan-requests`.

Request:

```json
{ "loan_id": 101 }
```

(No amount field — a live payment is always the full computed
`amount_due_this_cycle` for that loan, per §2.3/§2.5. Keeping the amount
server-computed, not client-supplied, prevents a borrower from paying an
arbitrary amount that desyncs `outstanding_balance`/EMI math.)

**Server logic (must be done inside one DB transaction):**
1. Load the loan; 404 if missing; **403 if `loan.individual_id !=
   current.id`** (server-side ownership check — a borrower must only be able
   to pay their own loans, per the access-control constraint carried over
   from the 4-role retrofit).
2. 400 if `loan.status != "Active"`.
3. Recompute `due-summary` for **all** of this borrower's active loans
   server-side (never trust a client-cached `sufficient_funds` flag) and
   re-check `wallet_balance >= total_due_this_cycle` across all of them. If
   insufficient → `400` with a body shaped like:
   ```json
   { "error": "insufficient_funds", "wallet_balance": 5000.0, "total_due_this_cycle": 7200.0 }
   ```
   This blocks payment of **this** loan (and, by the same rule, every other
   active loan too — the frontend should treat this 400 as "nothing is
   payable right now," not just "this one loan failed") even if the
   borrower clicked "repay" on only one of several loans.
4. Compute `emi`, `cycle_number`, `theoretical_due_date`, `status`,
   `days_late` per §2.2–2.5.
5. Insert new `RepaymentEvent` row.
6. Deduct: `individual.wallet_balance -= emi`.
7. Update `loan.outstanding_balance` / `loan.status` per §2.6.
8. Call `compute_and_store_score(db, individual, notes="Recomputed after live repayment")`.
9. `db.commit()`.

**Response:**

```json
{
  "loan_id": 101,
  "amount_paid": 2700.0,
  "status": "On_Time",
  "days_late": 0,
  "new_outstanding_balance": 19800.0,
  "loan_status": "Active",
  "new_wallet_balance": 15800.0,
  "new_score": { "score": 662, "risk_category": "Low" }
}
```

`new_score` lets the frontend show the score movement immediately without a
second round-trip.

---

## 4. UI flow spec (borrower dashboard)

Both features attach to `frontend/src/pages/dashboards/BorrowerDashboard.jsx`
and its existing card layout/pattern (plain `<div className="card">`, `btn
primary`/`critical`/`good` button classes, `useApi` hook, `api` client
module) — no new visual system needed, reuse `docs/DESIGN_SYSTEM.md` as-is.

### 4.1 Targeted-lender picker on the loan request form

Extend `RequestLoanForm` (currently lines 34-82 of
`BorrowerDashboard.jsx`). It already fetches `eligibility` via
`api.eligibleLendersFor(individualId, token)` and lists eligible lender
names in a sentence. Add:

- A `<select>` under the existing principal/tenure/purpose row, options
  built from `eligibility.lenders` (`{id, name}` — already returned today),
  first option `"Broadcast to all eligible lenders (default)"` with value
  `""`/`null`.
- On submit, pass `target_lender_id: selectedLenderId || undefined` into
  `api.createLoanRequest(...)`.
- When a specific lender is chosen, change the helper sentence above the
  form from "N lenders would currently see a request from you" to "Only
  <lender name> will see this request" so the borrower isn't misled by the
  broadcast-count text while a targeted pick is selected.
- `RequestsTable` (lines 84-109) gains a `Target` column showing
  `r.target_lender_name || 'Any eligible lender'`.

### 4.2 "Repay" button on the borrower's loan list

Extend `LoansTable` (lines 11-32). Add a `Repay` column: for rows where
`l.status === 'Active'`, render `<button className="btn primary"
onClick={() => openGateway(l.id)}>Repay</button>`; for non-active rows,
render nothing (matches the existing pattern of conditionally rendering
action buttons only for actionable rows, e.g. `RequestsTable`'s Withdraw
button).

`openGateway` opens the new payment-gateway modal (§4.3), which itself fetches
the due-summary (§3.2) fresh — it does not need to know which loan was
clicked beyond which row to pre-highlight/scroll to, since the modal always
shows **all** active loans and the aggregate gate (per the product owner's
"blocks ALL loans, not just the one clicked" requirement) — clicking Repay
on loan 101 opens the same modal a click on loan 205 would, just optionally
scrolled/highlighted to 101's row.

### 4.3 Payment gateway modal

New component `frontend/src/components/PaymentGatewayModal.jsx`. Opens as an
overlay (reuse whatever modal/overlay primitive `docs/DESIGN_SYSTEM.md`
already defines for e.g. offer decision confirmations, if one exists —
otherwise a simple fixed-position overlay `div` consistent with the rest of
the card styling, since this codebase currently has no true modal component
per the file scan; Agent 4 should check `frontend/src/components/` for any
existing dialog primitive before adding a bespoke one).

**On open:** call `GET /api/payments/due-summary?individual_id={id}`.

**State A — loading:** `<div className="loading">Loading payment
details...</div>` (matches existing loading text style).

**State B — sufficient funds** (`sufficient_funds: true`):
- Header: "Wallet balance: Rs. {wallet_balance}".
- A row per active loan: principal, "EMI #{cycle_number} of
  {tenure_months_total}", `amount_due_this_cycle`, a "Late" badge
  (`StatusChip`-style) if `will_be_late`, and a `Pay this loan` button.
- Clicking `Pay this loan` on a row calls `POST /api/payments/pay {loan_id}`
  immediately (§3.3 defines amount server-side — no separate confirm-amount
  step needed since it's always the fixed EMI), then:
  - On success → **State D** for that row inline (shows new balance/new
    score), and **re-fetches due-summary** so remaining rows' totals/gate
    reflect the reduced wallet balance live (a second payment in the same
    modal session must re-check the aggregate rule against the new,
    lower balance).
  - On `400 insufficient_funds` (can happen mid-session if an earlier
    payment in the same modal visit dropped the wallet below what's needed
    for the rest) → drop the whole modal into **State C**.

**State C — insufficient funds** (`sufficient_funds: false`, or a live 400
from `/pay`):
- Replace the loan-row list with a single clear banner: "Your wallet
  balance (Rs. {wallet_balance}) is less than the total due this cycle
  across all your active loans (Rs. {total_due_this_cycle}). You can't pay
  any loan right now." (`className="error-banner"`, matching the existing
  error-banner convention used elsewhere in this file).
- No `Pay` buttons render at all in this state — every loan row is shown
  read-only (principal/EMI/due, no button), so the borrower can still see
  what they owe without being able to act.

**State D — payment success (per-row, inline)**: after a successful
`/pay` call for a given loan, replace that row's button with a small success
strip: "Paid Rs. {amount_paid} — {status === 'Late' ? 'recorded as Late' :
'On time'}. New score: {new_score.score} ({new_score.risk_category})" —
this is the "visibly move the credit score" requirement; the score bump is
shown right where the action happened, not just on dashboard reload.
Additionally, on modal close, trigger the same `reload()` /
`reloadRequests()` pattern `BorrowerDashboard.jsx` already uses after other
mutating actions (`handleDecideOffer`, `handleWithdrawRequest`), so the
score badge / history chart / loans table on the underlying dashboard page
refresh without a manual browser reload.

---

## 5. Open questions / risks for Agent 3

1. **Partial payments are out of scope this pass** (§2.3) — the live payment
   path only ever pays the full EMI. If the product owner later wants a
   "pay less than EMI" option, `RepaymentEvent.status = "Partial"` already
   exists in the enum but nothing in this spec writes it from the live path
   — that would need a shortfall-carry-forward design this doc deliberately
   doesn't invent.
2. **Modal primitive**: confirmed by file listing that
   `frontend/src/components/` has no existing modal/dialog/overlay
   component today (only cards, chips, badges, tables). Agent 4 will need to
   build a minimal one for `PaymentGatewayModal` — flagged here so it isn't
   a surprise mid-implementation; keep it minimal (overlay + card), don't
   over-build a generic modal system for one use case.
3. **Race condition, accepted as out of scope**: two browser tabs paying
   the same borrower's loans simultaneously could both read a
   pre-deduction `wallet_balance` and both pass the sufficiency check before
   either commits. Given this is a single-demo-user-at-a-time app with no
   existing transaction-isolation handling anywhere else in the codebase
   (confirmed — no `SELECT ... FOR UPDATE` / row locking pattern exists in
   any service today), this is accepted as a known, unaddressed risk
   consistent with the rest of the app's concurrency posture, not something
   Agent 5 needs to solve net-new.
4. **`target_lender_id` and score-based eligibility drift**: if a borrower's
   score changes (e.g. from a live repayment on a *different* loan) between
   creating a targeted request and the target lender deciding it,
   `approve_request`'s existing re-check (`_lender_eligible_for_individual`
   at decide-time) already handles this correctly — no new code needed, just
   confirming the existing defense-in-depth still covers the new targeted
   path.
5. **Known bug, unrelated to this feature, flagged for Agent 4 to fix in
   passing**: `frontend/src/components/ScoreHistoryChart.jsx`'s `<YAxis>`
   (lines 43-49) is rendered with `width={36}` while the parent `<LineChart>`
   has `margin={{ ..., left: -18, ... }}` — the negative left margin
   combined with the fixed axis width is the likely cause of the
   garbled/clipped Y-axis labels observed live on the borrower dashboard.
   Since Agent 4 will already be editing this exact borrower-dashboard
   family of files for the repay button, fix this in the same pass (e.g.
   drop the negative `left` margin, or widen the axis) rather than opening a
   separate change.
6. **Wallet balance is borrower-only** — lenders/SHGs/admin have no wallet
   concept in this spec; `wallet_balance` lives only on `Individual`. If a
   future pass wants lenders to "fund" disbursements from a balance too,
   that's a separate schema addition, not covered here.
