"""
Fresh schema for the dual-path (SHG-linked + independent) credit system.

Design notes:
- `Individual.shg_id` is nullable: NULL means an independent borrower with no
  group affiliation. Every scoring/bootstrap decision branches on this.
- Credit scores are versioned history (`CreditScore` rows are append-only,
  like the old repo's credit_score_history), not a single mutable column --
  the dashboards need "score over time" and lenders need "why this score".
- `ScoreExplanation` stores the SHAP contribution per feature per score, so
  the borrower view can render "why you got this score" without re-running
  the model at read time.
- `SHGLenderLink` is the approve/reject table from Stage 4: a lender can only
  see/offer to individuals in SHGs it's linked to (or independents, who are
  open to all lenders by design).
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    state = Column(String(100), nullable=False)
    # Rough centroid, only used for the geo heatmap (Stage 7). Synthetic, not survey-grade.
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    shgs = relationship("SHG", back_populates="district")
    individuals = relationship("Individual", back_populates="district")


class SHG(Base):
    __tablename__ = "shgs"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    village = Column(String(100), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    formed_date = Column(Date, nullable=False)
    total_members = Column(Integer, default=0)
    status = Column(Enum("Active", "Inactive", "Dissolved", name="shg_status"), default="Active")

    # Login credentials for the SHG-facing dashboard (same pattern as Lender).
    username = Column(String(100), nullable=True, unique=True)
    password_hash = Column(String(150), nullable=True)

    district = relationship("District", back_populates="shgs")
    members = relationship("Individual", back_populates="shg")
    attendance_records = relationship("SHGAttendanceRecord", back_populates="shg")
    lender_links = relationship("SHGLenderLink", back_populates="shg")
    sessions = relationship("SHGSession", back_populates="shg", cascade="all, delete-orphan")

    @property
    def aggregate_repayment_rate(self):
        """On-time repayment rate across all loans of all members. Computed, not stored."""
        events = [e for m in self.members for l in m.loans for e in l.repayment_events]
        if not events:
            return None
        on_time = sum(1 for e in events if e.status == "On_Time")
        return round(on_time / len(events), 4)

    @property
    def aggregate_attendance_rate(self):
        if not self.attendance_records:
            return None
        present = sum(1 for a in self.attendance_records if a.present)
        return round(present / len(self.attendance_records), 4)


class Individual(Base):
    __tablename__ = "individuals"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(15), nullable=False, unique=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    village = Column(String(100))
    occupation = Column(String(100))
    monthly_income = Column(Float)
    has_bank_account = Column(Boolean, default=False)

    # NULL => independent borrower, no SHG trust boost. This single nullable FK
    # is what makes the whole dual-path design work without duplicating tables.
    shg_id = Column(Integer, ForeignKey("shgs.id"), nullable=True, index=True)

    joined_date = Column(Date, default=date.today)
    status = Column(Enum("Active", "Inactive", "Blocked", name="individual_status"), default="Active")

    # Login credentials for the borrower-facing "My Score" self-service view
    # (added on top of the original design -- nullable so any row seeded
    # before this existed doesn't break, though data_gen always sets it now).
    password_hash = Column(String(150), nullable=True)

    # Dummy payment-gateway balance for live repayments (docs/API_CONTRACT_PAYMENTS.md §1.1).
    # Nullable, same pattern as password_hash -- treat NULL as 0.0 everywhere read.
    wallet_balance = Column(Float, nullable=True)

    district = relationship("District", back_populates="individuals")
    shg = relationship("SHG", back_populates="members")
    savings_records = relationship("SavingsRecord", back_populates="individual")
    loans = relationship("Loan", back_populates="individual")
    credit_scores = relationship("CreditScore", back_populates="individual", order_by="CreditScore.calculated_date")
    attendance_records = relationship("SHGAttendanceRecord", back_populates="individual")
    sessions = relationship("IndividualSession", back_populates="individual", cascade="all, delete-orphan")

    @property
    def is_shg_linked(self):
        return self.shg_id is not None

    @property
    def latest_score(self):
        return self.credit_scores[-1] if self.credit_scores else None


class IndividualSession(Base):
    """A logged-in borrower session for the "My Score" self-service view --
    a plain opaque bearer token, not JWT, so no extra dependency is needed
    just to let someone look at their own score."""
    __tablename__ = "individual_sessions"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    individual = relationship("Individual", back_populates="sessions")


class LenderSession(Base):
    """Lender-facing session, identical shape to IndividualSession."""
    __tablename__ = "lender_sessions"

    id = Column(Integer, primary_key=True)
    lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    lender = relationship("Lender", back_populates="sessions")


class SHGSession(Base):
    """SHG-facing session, identical shape to IndividualSession."""
    __tablename__ = "shg_sessions"

    id = Column(Integer, primary_key=True)
    shg_id = Column(Integer, ForeignKey("shgs.id"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    shg = relationship("SHG", back_populates="sessions")


class AdminSession(Base):
    """Admin session -- no FK, since admin is an env-var credential, not a
    business entity (see docs/SPEC.md §6)."""
    __tablename__ = "admin_sessions"

    id = Column(Integer, primary_key=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class SHGAttendanceRecord(Base):
    """One row per SHG meeting per member. Only exists for SHG-linked individuals."""
    __tablename__ = "shg_attendance_records"

    id = Column(Integer, primary_key=True)
    shg_id = Column(Integer, ForeignKey("shgs.id"), nullable=False, index=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    meeting_date = Column(Date, nullable=False)
    present = Column(Boolean, nullable=False)

    shg = relationship("SHG", back_populates="attendance_records")
    individual = relationship("Individual", back_populates="attendance_records")


class SavingsRecord(Base):
    """Monthly savings behaviour -- applies to both SHG members (group savings
    target) and independents (self-reported / bank-linked savings)."""
    __tablename__ = "savings_records"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    period = Column(Date, nullable=False)  # first-of-month marker
    amount_expected = Column(Float, nullable=False)
    amount_saved = Column(Float, nullable=False)

    individual = relationship("Individual", back_populates="savings_records")


class Lender(Base):
    __tablename__ = "lenders"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    type = Column(Enum("Bank", "NBFC", "MFI", "Fintech", name="lender_type"), default="Bank")
    min_score_threshold = Column(Integer, default=500)
    max_loan_amount = Column(Float, default=50000)
    base_interest_rate = Column(Float, default=14.0)
    serves_independents = Column(Boolean, default=True)  # will this lender even look at non-SHG borrowers?

    # Login credentials for the lender-facing dashboard (added on top of the
    # original design -- nullable so pre-auth rows don't break; seeded by
    # app/ml/migrate_auth.py for every existing row).
    username = Column(String(100), nullable=True, unique=True)
    password_hash = Column(String(150), nullable=True)

    shg_links = relationship("SHGLenderLink", back_populates="lender")
    offers = relationship("LoanOffer", back_populates="lender")
    sessions = relationship("LenderSession", back_populates="lender", cascade="all, delete-orphan")


class SHGLenderLink(Base):
    """The Stage-4 approve/reject table. An SHG chooses which lenders may see
    and lend to its members; a lender can be linked to many SHGs and vice versa."""
    __tablename__ = "shg_lender_links"
    __table_args__ = (UniqueConstraint("shg_id", "lender_id", name="uq_shg_lender"),)

    id = Column(Integer, primary_key=True)
    shg_id = Column(Integer, ForeignKey("shgs.id"), nullable=False, index=True)
    lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=False, index=True)
    status = Column(Enum("Pending", "Approved", "Rejected", name="link_status"), default="Pending")
    requested_date = Column(Date, default=date.today)
    decided_date = Column(Date, nullable=True)
    notes = Column(String(300))
    # Which side created the row -- needed so /decide knows whose turn it is
    # to approve/reject (see docs/SPEC.md §4). Existing rows backfilled to
    # "shg" by app/ml/migrate_auth.py, since only the SHG-initiated flow
    # existed before lender auth was added.
    initiated_by_role = Column(Enum("shg", "lender", name="link_initiator"), nullable=False, default="shg")

    shg = relationship("SHG", back_populates="lender_links")
    lender = relationship("Lender", back_populates="shg_links")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=True, index=True)  # null for synthetic pre-marketplace history
    principal_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    tenure_months = Column(Integer, nullable=False)
    disbursement_date = Column(Date, nullable=False)
    outstanding_balance = Column(Float, nullable=False)
    status = Column(Enum("Active", "Closed", "Defaulted", "Written_Off", name="loan_status"), default="Active")
    purpose = Column(String(200))

    individual = relationship("Individual", back_populates="loans")
    lender = relationship("Lender")
    repayment_events = relationship("RepaymentEvent", back_populates="loan")


class RepaymentEvent(Base):
    __tablename__ = "repayment_events"

    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, index=True)
    due_date = Column(Date, nullable=False)
    payment_date = Column(Date, nullable=True)  # null if still unpaid/missed
    amount_due = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0)
    days_late = Column(Integer, default=0)
    status = Column(Enum("On_Time", "Late", "Partial", "Missed", name="repayment_status"), default="On_Time")

    loan = relationship("Loan", back_populates="repayment_events")


class CreditScore(Base):
    """Append-only score history. Each row is one scoring run for one individual."""
    __tablename__ = "credit_scores"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    risk_category = Column(
        Enum("Very Low", "Low", "Medium", "High", "Very High", name="risk_category"),
        nullable=False,
    )
    base_component = Column(
        Enum("shg_bootstrap", "independent_bootstrap", "model", name="score_base_component"),
        nullable=False,
    )
    model_version = Column(String(50), default="v1")
    calculated_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(String(300))

    individual = relationship("Individual", back_populates="credit_scores")
    explanations = relationship("ScoreExplanation", back_populates="score")


class ScoreExplanation(Base):
    """One row per feature per CreditScore -- the SHAP contribution that made
    up that score, so the borrower view can show 'why' without recomputing."""
    __tablename__ = "score_explanations"

    id = Column(Integer, primary_key=True)
    score_id = Column(Integer, ForeignKey("credit_scores.id"), nullable=False, index=True)
    feature_name = Column(String(100), nullable=False)
    feature_value = Column(String(200))
    shap_contribution = Column(Float, nullable=False)  # signed points, sums (approx) to score - base_value

    score = relationship("CreditScore", back_populates="explanations")


class LoanOffer(Base):
    """Stage-5 marketplace flow: lender proposes, borrower accepts/rejects."""
    __tablename__ = "loan_offers"

    id = Column(Integer, primary_key=True)
    lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=False, index=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    principal_offer = Column(Float, nullable=False)
    rate_offer = Column(Float, nullable=False)
    tenure_offer = Column(Integer, nullable=False)
    status = Column(
        Enum("Proposed", "Accepted", "Rejected", "Withdrawn", name="offer_status"),
        default="Proposed",
    )
    created_date = Column(DateTime, default=datetime.utcnow)
    decided_date = Column(DateTime, nullable=True)

    lender = relationship("Lender", back_populates="offers")
    individual = relationship("Individual")


class LoanRequest(Base):
    """Borrower-initiated loan request -- the mirror of LoanOffer (which is
    lender-initiated). A borrower states an amount/tenure/purpose once; it's
    broadcast to every lender they're currently eligible for (approved SHG
    link, or serves_independents), and whichever lender approves it first
    creates the loan directly. One lender declining does NOT close it for
    the others -- see LoanRequestDecline."""
    __tablename__ = "loan_requests"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    requested_principal = Column(Float, nullable=False)
    requested_tenure = Column(Integer, nullable=False)
    purpose = Column(String(200))
    status = Column(Enum("Pending", "Approved", "Withdrawn", name="loan_request_status"), default="Pending")
    created_date = Column(DateTime, default=datetime.utcnow)
    decided_date = Column(DateTime, nullable=True)
    decided_by_lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=True, index=True)
    resulting_loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    # NULL = broadcast (default, unchanged historical behavior). Set = only
    # this lender sees the request in their queue (docs/API_CONTRACT_PAYMENTS.md §1.2).
    target_lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=True, index=True)

    individual = relationship("Individual")
    decided_by_lender = relationship("Lender", foreign_keys=[decided_by_lender_id])
    target_lender = relationship("Lender", foreign_keys=[target_lender_id])
    resulting_loan = relationship("Loan")
    declines = relationship("LoanRequestDecline", back_populates="request", cascade="all, delete-orphan")


class LoanRequestDecline(Base):
    """One lender passing on a broadcast loan request. Doesn't change the
    request's status -- it just stops showing that request to that lender
    again, while it stays Pending (and visible) to every other eligible one."""
    __tablename__ = "loan_request_declines"
    __table_args__ = (UniqueConstraint("request_id", "lender_id", name="uq_request_lender_decline"),)

    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("loan_requests.id"), nullable=False, index=True)
    lender_id = Column(Integer, ForeignKey("lenders.id"), nullable=False, index=True)
    declined_date = Column(DateTime, default=datetime.utcnow)

    request = relationship("LoanRequest", back_populates="declines")
    lender = relationship("Lender")


class AnomalyFlag(Base):
    """Stage-8 stretch: isolation-forest output, one row per flagged individual per run."""
    __tablename__ = "anomaly_flags"

    id = Column(Integer, primary_key=True)
    individual_id = Column(Integer, ForeignKey("individuals.id"), nullable=False, index=True)
    anomaly_score = Column(Float, nullable=False)  # more negative = more anomalous (sklearn convention)
    reason = Column(Text)
    flagged_date = Column(DateTime, default=datetime.utcnow)

    individual = relationship("Individual")
