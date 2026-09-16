"""Auth for all four roles (borrower/lender/SHG/admin) -- see docs/SPEC.md §6
and docs/API_CONTRACT.md §1. Every non-public endpoint elsewhere in this API
requires one of the four `get_current_*` dependencies defined here, verified
server-side against that role's session table (or, for admin, the env-var
credential) -- this is the access-control retrofit the product owner asked
for, not just a frontend gate."""
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import ADMIN_PASSWORD, ADMIN_USERNAME
from app.db import get_db
from app.models import Individual, Lender, SHG
from app.schemas import LoginIn, RoleLoginIn
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


# --- Borrower (unchanged) ---------------------------------------------------

def get_current_individual(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Individual:
    token = _bearer_token(authorization)
    individual = auth_service.get_individual_from_token(db, token)
    if individual is None:
        raise HTTPException(401, "Not logged in, or your session has expired -- please log in again.")
    return individual


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    ind = db.query(Individual).filter(Individual.phone == payload.phone.strip()).first()
    if ind is None or not auth_service.verify_password(payload.password, ind.password_hash):
        raise HTTPException(401, "Incorrect phone number or password.")
    token = auth_service.create_session(db, ind)
    return {"token": token, "individual_id": ind.id, "name": ind.name}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    auth_service.invalidate_token(db, _bearer_token(authorization))
    return {"ok": True}


@router.get("/me")
def me(current: Individual = Depends(get_current_individual)):
    # Reuses the same summary shape /api/individuals already returns, so the
    # frontend can feed the id straight into the existing individual-detail
    # and score-history endpoints instead of a parallel response shape.
    from app.routers.individuals import _summary
    return _summary(current)


# --- Lender ------------------------------------------------------------

def get_current_lender(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Lender:
    token = _bearer_token(authorization)
    lender = auth_service.get_lender_from_token(db, token)
    if lender is None:
        raise HTTPException(401, "Not logged in, or your session has expired -- please log in again.")
    return lender


@router.post("/lender/login")
def lender_login(payload: RoleLoginIn, db: Session = Depends(get_db)):
    lender = db.query(Lender).filter(Lender.username == payload.username.strip()).first()
    if lender is None or not auth_service.verify_password(payload.password, lender.password_hash):
        raise HTTPException(401, "Incorrect username or password.")
    token = auth_service.create_lender_session(db, lender)
    return {"token": token, "lender_id": lender.id, "name": lender.name}


@router.post("/lender/logout")
def lender_logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    auth_service.invalidate_lender_token(db, _bearer_token(authorization))
    return {"ok": True}


@router.get("/lender/me")
def lender_me(current: Lender = Depends(get_current_lender)):
    from app.routers.lenders import _summary
    return _summary(current)


# --- SHG -----------------------------------------------------------------

def get_current_shg(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> SHG:
    token = _bearer_token(authorization)
    shg = auth_service.get_shg_from_token(db, token)
    if shg is None:
        raise HTTPException(401, "Not logged in, or your session has expired -- please log in again.")
    return shg


@router.post("/shg/login")
def shg_login(payload: RoleLoginIn, db: Session = Depends(get_db)):
    shg = db.query(SHG).filter(SHG.username == payload.username.strip()).first()
    if shg is None or not auth_service.verify_password(payload.password, shg.password_hash):
        raise HTTPException(401, "Incorrect username or password.")
    token = auth_service.create_shg_session(db, shg)
    return {"token": token, "shg_id": shg.id, "name": shg.name}


@router.post("/shg/logout")
def shg_logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    auth_service.invalidate_shg_token(db, _bearer_token(authorization))
    return {"ok": True}


@router.get("/shg/me")
def shg_me(current: SHG = Depends(get_current_shg)):
    from app.routers.shgs import _summary
    return _summary(current)


# --- Admin (env-var credential, no DB row) ---------------------------------

@dataclass
class AdminActor:
    """Marker object returned by get_current_admin -- admin has no business
    row to attach to, so this just proves "a valid admin session exists"."""
    name: str = "Admin"


def get_current_admin(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminActor:
    token = _bearer_token(authorization)
    if not auth_service.is_admin_token_valid(db, token):
        raise HTTPException(401, "Not logged in, or your session has expired -- please log in again.")
    return AdminActor()


@router.post("/admin/login")
def admin_login(payload: RoleLoginIn, db: Session = Depends(get_db)):
    if not (secrets_compare(payload.username, ADMIN_USERNAME) and secrets_compare(payload.password, ADMIN_PASSWORD)):
        raise HTTPException(401, "Incorrect username or password.")
    token = auth_service.create_admin_session(db)
    return {"token": token, "name": "Admin"}


def secrets_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)


@router.post("/admin/logout")
def admin_logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    auth_service.invalidate_admin_token(db, _bearer_token(authorization))
    return {"ok": True}


@router.get("/admin/me")
def admin_me(current: AdminActor = Depends(get_current_admin)):
    return {"name": current.name}


# --- Generic "any logged-in role" dependency --------------------------------

@dataclass
class CurrentActor:
    role: str  # "individual" | "lender" | "shg" | "admin"
    individual: Individual | None = None
    lender: Lender | None = None
    shg: SHG | None = None


def get_current_actor(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentActor:
    token = _bearer_token(authorization)
    if token:
        ind = auth_service.get_individual_from_token(db, token)
        if ind is not None:
            return CurrentActor(role="individual", individual=ind)
        lender = auth_service.get_lender_from_token(db, token)
        if lender is not None:
            return CurrentActor(role="lender", lender=lender)
        shg = auth_service.get_shg_from_token(db, token)
        if shg is not None:
            return CurrentActor(role="shg", shg=shg)
        if auth_service.is_admin_token_valid(db, token):
            return CurrentActor(role="admin")
    raise HTTPException(401, "Not logged in, or your session has expired -- please log in again.")
