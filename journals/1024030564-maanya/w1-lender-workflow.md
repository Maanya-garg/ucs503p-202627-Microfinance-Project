# W1: Understanding and Implementing the Lender Workflow

## 1. The Lender's Position in CreditSetu

CreditSetu connects borrowers with lenders while using the borrower's
credit score as one of the inputs for lending decisions.

From the lender's perspective, the workflow can be represented as:

$$
\text{Lender Login}
\rightarrow
\text{Lender Authentication}
\rightarrow
\text{Eligible Borrowers}
\rightarrow
\text{Loan Request}
\rightarrow
\text{Lending Decision}
$$

The important part of the lender role is that the lender should only
interact with borrowers and requests that are permitted by the platform's
eligibility and authorization rules.

---

## 2. Understanding Lender Authentication

The lender is authenticated separately from the other roles in the system.

The application uses bearer tokens rather than JWTs. A successful lender
login creates a lender session, and subsequent requests use:

```text
Authorization: Bearer <token>
