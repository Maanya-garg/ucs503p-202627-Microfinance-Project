# W1: Role-based redesign, payments, and CI/CD debugging

## Starting point

CreditSetu already had a working scoring pipeline (XGBoost + SHAP,
cold-start bootstrap for SHG vs. independent borrowers) and a single
combined frontend where every role could see every other role's data --
no login gate except an optional borrower self-service view. This week's
work replaced that with proper role separation and added a live
repayment flow.

## Problem: everyone could see everyone else's data

There was no access control. A borrower, a lender, and an SHG all hit
the same open API and the same combined UI.

**Fix:** four separate login-gated roles -- Borrower, Lender, SHG,
Admin -- each with its own dashboard and its own bearer-token session
table, modelled on the existing borrower "My Score" auth pattern (PBKDF2
hashing, opaque tokens, no JWT). Critically, authorization is enforced
**server-side** on every endpoint (401 for no/bad token, 403 for
wrong-role or out-of-scope access), not just hidden in the UI --
verified this by hitting the API directly with a borrower's token trying
to fetch another borrower's record and confirming a 403.

Lenders and SHGs didn't have credentials at all before this, so I added
`username`/`password_hash` columns to both tables and a migration script
that seeds demo credentials (slug-of-name + `password123`, same pattern
as borrowers) without touching any of the existing seeded business data.

## Feature: lender reputation

The product ask was "lenders should get some benefit for offering better
interest rates -- check if anything like this exists in the real world."
Landed on RBI's priority-sector-lending / co-lending incentive structure
as the real-world analogue, and implemented a reputation score computed
from each lender's own `base_interest_rate` relative to the platform
average, plus their actual marketplace activity -- entirely derived from
existing schema fields, no new fabricated data.

## Feature: targeted loan requests + a live repayment flow

Two gaps reported after the first role-based pass went live:

1. A borrower's loan request always broadcast to every eligible lender;
   there was no way to target one specific lender from the suggested
   list. Added an optional `target_lender_id` on the request, plus a
   `retarget` endpoint so a declined targeted request isn't a dead end.
2. There was no way to actually repay a loan -- the dashboard showed
   loan status but repayment history only ever came from the offline
   synthetic data generator, never from a live borrower action.

The second one needed a real design decision: what does "amount due this
cycle" mean for a loan that might have been disbursed seconds ago, with
no due-date/collections engine in the app at all? Solved it by deriving
the cycle number from the *count* of existing repayment events on that
loan rather than elapsed calendar time, so a brand-new loan is payable
immediately -- this is what makes the feature usable by a live demo
user, not just replayable against backdated data.

Added a `wallet_balance` per borrower (seeded as a multiple of their
existing `monthly_income`, not an arbitrary number) and a payment
endpoint that: re-fetches the balance inside the same transaction right
before deducting (a minimal guard against a real race condition, since
this codebase has no row-locking anywhere else either), blocks payment
of *any* loan if the wallet can't cover the borrower's *total* dues this
cycle (not just the one loan clicked -- this was an explicit product
requirement, not my own interpretation), and recomputes the credit score
in the same commit so the impact is visible immediately.

Verified end to end with a real account: requested a loan, approved it
from a lender login, paid it through the new flow, and watched the score
move from 596 (Medium risk) to 886 (Very Low risk) after enough on-time
history accumulated -- entirely through the live API, no manual database
edits.

## Bug found: risk labels read backwards

"Very Low" risk was being shown bare under a borrower's own score --
technically correct (very low risk of default) but reads as if the
*score* is bad. Relabelled to the same Excellent/Good/Fair/Poor/Very
Poor language real credit bureaus use, as a pure display-layer mapping
in the shared score-badge component (no backend/schema change).

## Bug found: link approve/reject was silently broken

While checking the SHG and Admin dashboards, found that the "Approve
Partnership" / "Reject Partnership" buttons on the lender dashboard
referenced `l.link_id`, but the actual API field is `id`. Every click
was calling the decide endpoint with `undefined` -- this wasn't just a
React key-prop console warning (which is what first drew my attention to
it), it meant lenders could never actually approve or reject an SHG
link through the UI. Fixed all three occurrences plus the matching one
on the admin links table, and confirmed live that approving a real
pending link now correctly moves it to Approved.

## CI/CD: the docs site wasn't actually deploying

Added `docs/summary.md` so `mkdocs-literate-nav` had something to build
a sidebar from (it never existed, inherited gap from the upstream
template). That alone didn't fix it, though -- the deployed site was
still rendering via GitHub's default Jekyll README fallback, not the
repo's own `mkdocs` GitHub Actions workflow. Root cause: GitHub disables
workflow files by default on a fork that already contained them at fork
time, so the `mkdocs` workflow had never run once, ever, despite being
correctly written and correctly triggering on push. Fixed by enabling
workflows on the fork (Actions tab banner, not the general permissions
settings), then pointing GitHub Pages' source at the `gh-pages` branch
the workflow produces instead of `master`. Also found and fixed a
same-story 404 on every page for `javascript/arithmatex.js`, referenced
in `mkdocs.yml` for KaTeX math rendering but never created -- added it
as a documented no-op stub since nothing in the docs actually uses math
notation yet.

## What I'd flag for next week

- Prototype Stage report template is still marked TBA on the course
  site -- nothing to fill in there until it's released.
- Score-history "improvement over time" features (home page stories,
  district trend stats) are real but sparse right now, since the scoring
  pipeline has only been run a handful of times -- they'll fill in
  naturally as more scoring runs happen, not something to force with
  fake history.
