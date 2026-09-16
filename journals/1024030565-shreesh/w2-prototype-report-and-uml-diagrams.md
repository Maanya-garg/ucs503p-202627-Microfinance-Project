# W2: Prototype Stage report, UML diagrams, and toolchain setup

## Verified the SHG and Admin dashboards, found another real bug

Checked both role dashboards live. SHG dashboard was clean. Admin
dashboard worked but surfaced a real defect while I was in there: the
"Approve Partnership" / "Reject Partnership" buttons on both the
Lender and Admin dashboards referenced `l.link_id`, but the actual API
field is `id`. Every click silently called the decide endpoint with
`undefined` -- lenders could never actually approve or reject an SHG
link through the UI, despite the button looking functional. Fixed all
occurrences and confirmed live: a real pending link now correctly
moves to Approved.

## Drafted the Prototype Stage report

No official course template exists yet for this report (still marked
TBA on the course site), so I built one from an approved reference
format -- matched its heading structure (Abstract/Keywords,
Introduction, Related Work, Proposed Methodology with an Algorithm
subsection, Results and Analysis, Conclusion, References) and adapted
the content to CreditSetu instead of copying its subject matter. Added
a Feasibility Report section (Technical/Operational/Economic/Schedule)
and three new appendix sections for UML diagrams, per the explicit
instructions given for this report. Every number and claim in the
report is one we actually measured or verified this session or the
previous one -- nothing padded.

## Allocated agents for the three UML diagrams

Ran three parallel agents, each reading the real codebase before
drawing anything, to produce PlantUML source for:
- **Use case diagram** -- 4 actors, ~40 use cases, plus 6 fully written
  use-case scenarios (preconditions/main flow/alternate flows/
  postconditions) grounded in the actual routers.
- **Class diagram** -- from the real SQLAlchemy models, all 16+
  tables including the role-session and payments-feature additions.
- **Activity diagram** -- the real request -> approval -> repayment ->
  rescoring flow with Borrower/System/Lender swimlanes, including the
  actual race-condition guard and the aggregate insufficient-funds
  gate.

The use-case agent independently caught the same class of bug I'd just
fixed: the borrower dashboard's "Recompute my score" button called
`POST /api/individuals/{id}/recompute-score`, which is admin-only by
design (documented in our own spec). Every click would have 401'd.
Removed the button, replaced it with accurate copy explaining that the
score updates automatically after each repayment.

## Rendering and compiling: three tool installs

None of this could be verified without local tooling, so:
- Installed **poppler** (`pdftoppm`) so I could actually read PDF
  content as images instead of taking a file's existence on faith.
- Installed **PlantUML** (needs Java, already present) and rendered
  all three diagrams to PNG locally -- caught that the use-case
  diagram is visually dense (expected, given 4 actors x ~40 use
  cases) but confirmed all three render without syntax errors.
- Embedded the rendered PNGs into the report as real
  `\includegraphics` figures.

## Debugging why Overleaf wasn't showing the diagrams

A manual ZIP upload to Overleaf lost the `figures/` folder's relative
position to `main.tex`, so every `\includegraphics` fell back to
LaTeX's "file not found" placeholder (a bordered box with the literal
filename printed inside -- not an error, easy to miss why it's
happening). Diagnosed this by walking through exactly what Overleaf's
upload flow preserves vs. flattens, rather than assuming the diagrams
themselves were broken.

## Installed MiKTeX locally and compiled for real

Rather than keep guessing at fixes for Overleaf's upload behaviour, I
installed a full LaTeX distribution (MiKTeX) locally -- first attempt
was interrupted by a GUI confirmation dialog mid-install (scoop's
wrapper didn't handle it), so I re-downloaded the installer directly
from the CTAN mirror and ran it with the correct `--unattended
--auto-install=yes` flags. Compiled `main.tex` with `pdflatex` (two
passes, for cross-references), then verified the result by rendering
the output PDF back to page images myself and visually confirming all
three diagrams are genuinely embedded and legible -- not just trusting
a "compile succeeded" message. Pushed the working PDF to the repo.

This means the project no longer depends on Overleaf working correctly
to get a compiled report -- there's now a working local LaTeX
toolchain that can rebuild either report from source at any time.
