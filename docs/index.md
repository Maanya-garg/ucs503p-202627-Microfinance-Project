![Tiet Logo](assets/tiet-logo.svg){ .tiet-logo }

**UCS503: Software Engineering (Project)**
**TIET Patiala**

# CreditSetu -- Dual-Path Microfinance Credit Scoring

**Team**: Shreesh Gupta, Kashvi Bansal, Maanya Garg, Shivam Raj -- CSED

An individual credit-scoring system for microfinance lending in India. Every
borrower builds their **own** credit score from their own repayment history,
but someone who belongs to a Self-Help Group (SHG) gets a bootstrap head
start from their group's track record, while an independent borrower starts
lower and builds purely from scratch. Lenders formally partner with specific
SHGs (an approve/reject linkage, not open lending to anyone), and a scoring
engine (XGBoost + SHAP) explains *why* each score is what it is, not just
what it is.

The system is access-controlled by role: **Borrower**, **Lender**, **SHG**,
and **Admin** each log in separately and only ever see the data appropriate
to that role -- enforced server-side, not just hidden in the UI.

See the [project proposal](https://github.com/shreesh1802/ucs503p-202627-Microfinance-Project/blob/master/project-proposal/main.tex)
for the full problem statement, solution approach, evaluation criteria,
scope, and risks, and [code/README.md](https://github.com/shreesh1802/ucs503p-202627-Microfinance-Project/blob/master/code/README.md)
for setup/run instructions and the API reference.

## Repository layout

- `code/` -- the actual application (FastAPI backend + React/Vite frontend +
  the ML scoring pipeline).
- `project-proposal/` -- the Project Proposal report (LaTeX/Overleaf).
- `project-report-prototype-stage/` -- Prototype Stage report (template not
  yet released by the instructor as of this writing).
- `project-report-final/` -- Final report (later in the semester).
- `journals/` -- one folder per team member, weekly markdown journal entries
  -- see the Journals section in the navigation.
