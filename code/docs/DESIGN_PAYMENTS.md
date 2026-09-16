# CreditSetu — Lender Picker & Demo Payment Gateway: UX Spec

Component-level UX spec for two borrower-facing additions: (1) a lender picker on the loan request form, (2)
a dummy payment gateway modal reached from "Repay" on the borrower dashboard. Builds directly on
`docs/DESIGN_SYSTEM.md` and the variables already live in `frontend/src/index.css` — no new tokens are
introduced. Written for Agent 4 (frontend) to implement without further design decisions. Does not cover
backend/API contracts (see `docs/REQUIREMENTS_PAYMENTS.md`, written in parallel by Agent 1) and is not
application code.

---

## 1. Research basis (light)

Patterns observed across common consumer payment/bill-pay UIs (UPI apps such as Google Pay/PhonePe, bank
bill-pay flows) and standard sandbox/test-mode payment conventions:

1. **Bill-pay confirmation screen** — a near-universal layout: payee/purpose line at top, a large prominent
   amount-due figure, a secondary "balance available" line directly below or beside it, one primary CTA
   ("Pay ₹X"), and if funds are short, the CTA either disables with inline helper text or the tap produces
   an immediate red banner explaining the shortfall in rupees ("You need ₹Y more"). Amount-due is never
   editable on a bill-pay (as opposed to a peer-transfer) screen — it's fixed by what's owed.
2. **Sandbox/test-mode labelling** — payment sandboxes (Stripe test mode, Razorpay test mode, UPI simulator
   apps) consistently use a persistent, high-visibility badge (banner strip or corner ribbon, not a small
   caption) reading something like "TEST MODE" / "NO REAL MONEY", repeated at the top of every screen of the
   flow including the success screen, in a color distinct from both brand and status-success colors so it
   reads as a mode indicator rather than a status. This is the pattern to adapt here.
3. **Multi-bill selection when funds are short** — bill-pay apps (utility aggregators, EMI apps) that show
   multiple dues typically list each due as a row with a checkbox/amount, a running "selected total" vs.
   "available balance" comparator pinned above the CTA, and grey out or flag rows that would push the
   selection over balance rather than silently allowing an over-limit submission.

**Recommendation:** adapt pattern (1) directly for the modal's ready/blocked states, and pattern (2) for the
demo-mode badge (a persistent strip, not a caption). Pattern (3) is not built as a full multi-select UI here
(the borrower still clicks "Repay" on one loan), but its *comparison logic* — total owed across all active
loans this cycle vs. wallet balance — is what gates the insufficient-funds state, and the modal surfaces that
context (see §3.3) so the borrower understands why a single-loan repayment can still be blocked.

---

## 2. Lender picker (loan request form)

### 2.1 Placement

Insert as a new section in the existing loan request form, between the amount/tenure/purpose fields and the
submit button. Section uses `.section-subheading` ("Choose a Lender") per existing form conventions.

### 2.2 Structure

Two-option toggle at the top of the section, then a conditional list:

```
[Radio] Broadcast to all eligible lenders  (default, preselected — preserves current behavior)
[Radio] Choose a specific lender
```

Use native `input[type=radio]` styled per existing `input`/`.field-label` rules (no new control needed —
this is exactly the existing form input styling, just radios instead of text/select).

When "Choose a specific lender" is selected, reveal a list of eligible lenders below it:

- Container: reuse `.card` styling but nested (no drop-shadow duplication — apply `border: 1px solid
  var(--border); border-radius: var(--radius); background: var(--surface-2);` directly rather than stacking
  `.card` inside `.card`) with `padding: 12px`.
- Each eligible lender is a row, **not a free-floating card** — per §3.4 of the design system, lists of
  records default to table/row treatment. Use a bordered row list:
  ```html
  <label class="lender-row">
    <input type="radio" name="lender" />
    <div class="lender-row-main">
      <span class="lender-name">SHG Trust Cooperative</span>
      <span class="muted small">Interest 12% p.a. · Max ₹50,000 · 24 loans funded</span>
    </div>
    <span class="status-chip status-chip-approved">● ELIGIBLE</span>
  </label>
  ```
- `.lender-row`: `display:flex; align-items:center; gap:12px; padding:10px 12px; border-bottom:1px solid
  var(--gridline); cursor:pointer;` — last row `border-bottom:none`. Hover: `background: var(--primary-tint)`
  (matches `tr.clickable:hover`). Selected state: `background: var(--primary-tint); border-left: 3px solid
  var(--primary);` (add `padding-left: 9px` to compensate so content doesn't shift).
- `.lender-name`: `font-weight:600; font-size: var(--fs-base); color: var(--text-primary);` block-level, with
  the metadata line below it using the existing `.muted.small` classes already defined in `index.css`.
- The "ELIGIBLE" chip reuses `.status-chip.status-chip-approved` verbatim — do not invent a new chip variant
  for this; eligibility is functionally the same "good standing" semantic as loan-approved status elsewhere.
- Empty state (no eligible lenders returned): render a `.notice-banner`-style strip (reuse `.notice-banner`
  class, `border-left: 4px solid var(--status-flagged); background: var(--status-flagged-bg);`) reading
  "No lenders currently meet the eligibility criteria for this request. You can still broadcast to all
  eligible lenders — matches may appear as your request is reviewed." and auto-revert the toggle to the
  broadcast option (disable the "choose specific lender" radio in this case, with `title` explaining why).

### 2.3 Validation / submit

- If "Choose a specific lender" is selected, require a lender radio to be checked before enabling `.btn.primary`
  submit (same disabled-state pattern already used elsewhere: `.btn:disabled { opacity:.5; cursor:not-allowed }`).
- Field-level error, if the user tries to submit without selecting a row, uses the existing `.error-banner`
  class, not a new inline error style.

---

## 3. Payment gateway modal ("Repay")

### 3.1 Trigger & shell

- Triggered by a `.btn.primary` "Repay" button on each active-loan row/card of the borrower dashboard.
- Modal shell: centered overlay, `max-width: 480px`, uses `.card` styling for the panel itself
  (`background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius); box-shadow:
  0 1px 2px rgba(0,0,0,0.06)` is too flat for an overlay context — add a stronger overlay-only shadow, e.g.
  `box-shadow: 0 8px 24px rgba(0,0,0,0.18)`, kept local to the modal component, not merged into the base
  `.card` rule). Backdrop: `background: rgba(20,24,28,0.5)` (derived from `--text-primary` at low alpha,
  consistent with the app's dark neutral rather than a generic black).
- Modal header row: title ("Repay Loan"), close button (✕) top-right using the existing icon-button/plain
  button convention (no new icon set — reuse `.utility-link`-style plain button treatment: `background:none;
  border:none; cursor:pointer; color: var(--text-secondary); font-size: var(--fs-lg);`).

### 3.2 Demo-mode badge (persistent, all states)

Directly under the header, on **every** state of the modal including success: a full-width strip, not a
small caption —

```html
<div class="demo-payment-badge">DEMO PAYMENT — NO REAL MONEY MOVES</div>
```

```css
.demo-payment-badge {
  background: var(--accent-tint);
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  font-size: var(--fs-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  text-align: center;
  padding: 6px 10px;
  margin-bottom: 14px;
}
```
`--accent` (saffron-derived, currently muted gold in the live palette) is deliberately used here rather than
`--status-info` or `--primary`: it is not a brand color and not a status color, so it reads as a distinct
"mode" indicator per the sandbox-labelling research in §1.2, and avoids implying this is an official/branded
payment rail — consistent with the anti-impersonation stance in `DESIGN_SYSTEM.md` §5.

### 3.3 States

**A. Loading** (fetching wallet balance / dues)
Reuse the existing `.loading` class ("Loading…" centered text) inside the modal body while balance/dues are
fetched. No skeleton components exist elsewhere in the app, so don't introduce one here.

**B. Ready to pay (sufficient funds)**
Body layout, top to bottom, each row `display:flex; justify-content:space-between; padding:8px 0;
border-bottom:1px solid var(--gridline)`:
- Lender / loan purpose (e.g. "SHG Trust Cooperative · Crop input loan") — `.muted`.
- "Amount Due This Cycle" — label `.field-label` style, value in `--fs-xl` bold `--text-primary`, tabular-nums
  (same treatment as `.stat-tile .value`, scaled down).
- "Wallet Balance" — same row style, value in `--fs-md` `--text-secondary`.
- Below the rows, if the borrower has other active loans also due, one line of `.muted.small`: "You have
  ₹Z due across N other active loans this cycle." — this is the surfacing of the §1.3 multi-bill context;
  it does not need its own list UI, just this disclosure line, so the borrower understands the gate in
  state C isn't a bug.
- CTA: `.btn.primary`, full-width, "Confirm Payment of ₹X".

**C. Blocked — insufficient funds**
Triggered when wallet balance < sum of amounts due across **all** the borrower's active loans this cycle
(not just the clicked loan) — this is the key rule from the brief.
- Replace the CTA row with a `.error-banner`-styled block (reuse class as-is) containing:
  - Bold first line: "Insufficient balance to complete this payment."
  - Explanation line: "Your wallet balance (₹{balance}) is less than the ₹{total_due} due across your
    {n} active loan(s) this cycle. Add funds or reduce the amount before retrying." — the total_due here is
    the all-loans total, not the single loan's due, so the copy must say so explicitly to avoid confusing
    the borrower ("why can't I pay this ₹500 loan when I have ₹500?").
  - The "Confirm Payment" button renders `disabled` (per §3.3's `.btn:disabled` convention) rather than being
    hidden — per the bill-pay research in §1.1, a disabled CTA with adjacent explanation is the clearer
    pattern than letting the user tap and then erroring, since the shortfall is already known at modal-open
    time (balance and all-dues are both fetched before state B/C is decided).
  - A secondary, non-primary `.btn` "Close" button remains available.

**D. Payment succeeded**
- Header area: `.status-chip.status-chip-approved` ("✓ PAYMENT RECORDED") in place of the amount-due block.
- A small "Score Impact" panel reusing the "assessment report" card convention from `DESIGN_SYSTEM.md` §4.4
  (bordered mini-table, not a floating stat): two rows, "Previous Score" and "Updated Score", each with the
  value in tabular-nums, and the updated row using `--status-approved` color if the score moved up (color
  paired with a ▲ glyph per the app's existing "never color alone" rule, or ▼ / no change accordingly).
- Primary action: `.btn.primary` "Done" (closes modal, triggers dashboard refresh).
- The demo-mode badge (§3.2) still renders above this state — success screens are exactly where real
  sandboxes are most often mistaken for production, so it must not be dropped here.

### 3.4 Visual states summary table

| State | Key element | Class reuse |
|---|---|---|
| Loading | centered spinner/text | `.loading` |
| Ready | amount/balance rows + enabled CTA | `.card` rows, `.btn.primary` |
| Blocked | error block + disabled CTA | `.error-banner`, `.btn:disabled` |
| Success | status chip + score panel | `.status-chip-approved`, report-card pattern (§4.4 of DESIGN_SYSTEM.md) |

---

## 4. Accessibility notes (modal-specific)

Consistent with the app's existing GIGW/WCAG-AA commitments (`DESIGN_SYSTEM.md` §0/§5):

- **Role & labelling**: modal root `role="dialog"` `aria-modal="true"` `aria-labelledby="repay-modal-title"`
  pointing at the header text ("Repay Loan"). The demo-mode badge text should also be reachable by screen
  readers as part of normal reading order (not `aria-hidden`) since it's safety-relevant information, not
  decoration.
- **Focus trap**: on open, move focus to the modal's first focusable element (close button or, if state is
  already "ready", the CTA) — do not use `autofocus` on a state that may not yet be determined (avoid
  focusing a button that's about to become disabled once the balance fetch resolves). Trap Tab/Shift+Tab
  cycling within the modal's focusable elements; restore focus to the triggering "Repay" button on close.
- **Keyboard close**: `Escape` closes the modal from any state (equivalent to the "Close" button), except
  optionally suppress it for a brief in-flight "submitting payment" sub-state if one is implemented, so a
  stray Escape can't abandon a request that's already been sent — otherwise it should always be available.
- **Focus-visible**: all modal interactive elements inherit the existing global `a:focus-visible,
  button:focus-visible, input:focus-visible` outline rule already in `index.css` — do not override it inside
  the modal.
- **Live region for state changes**: wrap the body content area in `aria-live="polite"` so a screen-reader
  user is told when the modal moves from Loading → Ready/Blocked, and from Ready → Success, without needing
  to re-navigate the dialog.
- **Color-independent status**: the blocked state must not rely on the red `.error-banner` color alone — it
  already pairs with bold explanatory text per §3.3, and the success chip already carries a ✓ glyph per the
  existing `.status-chip` convention; keep both as specified rather than simplifying to color-only treatments.
- **Backdrop click**: clicking the backdrop closes the modal (equivalent to Escape/Close) but must not be the
  *only* close mechanism — the visible ✕ button and Escape key are both required for users who can't easily
  target a click outside the panel.
