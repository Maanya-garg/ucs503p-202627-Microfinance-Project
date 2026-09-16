"""Pydantic request bodies for the write endpoints. Read endpoints return
plain dicts built in the routers (from ORM objects or raw service output) --
not worth a parallel schema hierarchy for a project this size, and it keeps
the service-layer dicts (matching_service, clustering, anomaly) usable as-is."""
from pydantic import BaseModel


class LinkRequestIn(BaseModel):
    shg_id: int
    lender_id: int
    notes: str | None = None


class LinkDecisionIn(BaseModel):
    approve: bool
    notes: str | None = None


class OfferProposeIn(BaseModel):
    lender_id: int
    individual_id: int
    principal: float
    rate: float
    tenure: int


class OfferDecisionIn(BaseModel):
    accept: bool


class LoginIn(BaseModel):
    phone: str
    password: str


class RoleLoginIn(BaseModel):
    """Username+password login body shared by lender/SHG/admin auth."""
    username: str
    password: str


class LoanRequestIn(BaseModel):
    individual_id: int
    principal: float
    tenure: int
    purpose: str | None = None


class LoanRequestDecisionIn(BaseModel):
    lender_id: int
    approve: bool
    rate: float | None = None  # required when approve=True
