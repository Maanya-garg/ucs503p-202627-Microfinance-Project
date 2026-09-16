# CreditSetu -- Dual-Path Microfinance Credit Scoring

UCS503P Software Engineering project (2026-27 ODD), Thapar Institute of
Engineering and Technology.

**Team:**

| Name | Roll No. |
|---|---|
| Maanya Garg | 1024030564 |
| Kashvi Bansal | 1024030563 |
| Shreesh Gupta | 1024030565 |
| Shivam Raj | 1024031140 |

## What this is

An individual credit-scoring system for microfinance lending in India.
Every borrower builds their **own** credit score from their own repayment
history, but someone who belongs to a Self-Help Group (SHG) gets a
bootstrap head start from their group's track record, while an
independent borrower starts lower and builds purely from scratch. Lenders
formally partner with specific SHGs (an approve/reject linkage, not open
lending to anyone), and a scoring engine (XGBoost + SHAP) explains *why*
each score is what it is, not just what it is.

The system is access-controlled by role: **Borrower**, **Lender**, **SHG**,
and **Admin** each log in separately and only ever see the data
appropriate to that role -- enforced server-side, not just hidden in the
UI.

See `project-proposal/main.tex` for the full project proposal (problem
statement, solution approach, evaluation criteria, scope, and risks).

## Repository layout

This repo follows the standard UCS503P template structure:

- `code/` -- the actual application (FastAPI backend + React/Vite
  frontend + the ML scoring pipeline). See `code/README.md` for
  setup/run instructions and API docs once added.
- `project-proposal/` -- the Project Proposal report (LaTeX/Overleaf).
- `project-report-prototype-stage/` -- Prototype Stage report
  (template not yet released by the instructor as of this writing).
- `project-report-final/` -- Final report (later in the semester).
- `journals/` -- one folder per team member (`<rollno>-<firstname>/`),
  weekly markdown journal entries.
- `docs/` -- project documentation, built via `mkdocs`; any commit to
  `master` triggers CI/CD build+deploy of the docs site (including the
  journals).

## Docs

`docs/` is an organised collection of markdown files, built with
[`mkdocs`](https://www.mkdocs.org/). Any commit into the `master` branch
of this repository triggers a CI/CD build and deployment of the
documentation site, including the journals.

For a local dev version of the docs:

``` shell
make docs
```
