"""Borrower login for the "My Score" self-service view.

Deliberately minimal, and deliberately dependency-free: password hashing
uses the standard library's `hashlib.pbkdf2_hmac` (no passlib/bcrypt) and
sessions are opaque random tokens stored in the `individual_sessions` table
(no JWT library). For a real deployment you'd want a vetted password-hashing
library and short-lived signed tokens; for this demo, pulling in a new
compiled dependency just to log into a synthetic dataset isn't worth it.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from app.models import AdminSession, IndividualSession, LenderSession, SHGSession

PBKDF2_ITERATIONS = 200_000
SESSION_TTL = timedelta(days=7)

# Every synthetically-seeded borrower gets this password (see app/ml/data_gen.py).
# Not a secret -- it's demo data -- just needs to be documented somewhere obvious.
DEMO_PASSWORD = "password123"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or ":" not in stored:
        return False
    salt_hex, digest_hex = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(candidate.hex(), digest_hex)


def create_session(db, individual) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(IndividualSession(
        individual_id=individual.id, token=token,
        created_at=now, expires_at=now + SESSION_TTL,
    ))
    db.commit()
    return token


def get_individual_from_token(db, token: str | None):
    if not token:
        return None
    session = db.query(IndividualSession).filter(IndividualSession.token == token).first()
    if session is None or session.expires_at < datetime.utcnow():
        return None
    return session.individual


def invalidate_token(db, token: str | None):
    if not token:
        return
    db.query(IndividualSession).filter(IndividualSession.token == token).delete()
    db.commit()


# --- Lender / SHG / Admin sessions -- same opaque-bearer-token pattern as
# above, parallel tables (see docs/API_CONTRACT.md §1). Kept as separate
# explicit functions (rather than one generic helper) to match the style of
# the borrower functions above and keep each role's dependency trivial to
# read in app/routers/auth.py.

def create_lender_session(db, lender) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(LenderSession(lender_id=lender.id, token=token, created_at=now, expires_at=now + SESSION_TTL))
    db.commit()
    return token


def get_lender_from_token(db, token: str | None):
    if not token:
        return None
    session = db.query(LenderSession).filter(LenderSession.token == token).first()
    if session is None or session.expires_at < datetime.utcnow():
        return None
    return session.lender


def invalidate_lender_token(db, token: str | None):
    if not token:
        return
    db.query(LenderSession).filter(LenderSession.token == token).delete()
    db.commit()


def create_shg_session(db, shg) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(SHGSession(shg_id=shg.id, token=token, created_at=now, expires_at=now + SESSION_TTL))
    db.commit()
    return token


def get_shg_from_token(db, token: str | None):
    if not token:
        return None
    session = db.query(SHGSession).filter(SHGSession.token == token).first()
    if session is None or session.expires_at < datetime.utcnow():
        return None
    return session.shg


def invalidate_shg_token(db, token: str | None):
    if not token:
        return
    db.query(SHGSession).filter(SHGSession.token == token).delete()
    db.commit()


def create_admin_session(db) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(AdminSession(token=token, created_at=now, expires_at=now + SESSION_TTL))
    db.commit()
    return token


def is_admin_token_valid(db, token: str | None) -> bool:
    if not token:
        return False
    session = db.query(AdminSession).filter(AdminSession.token == token).first()
    if session is None or session.expires_at < datetime.utcnow():
        return False
    return True


def invalidate_admin_token(db, token: str | None):
    if not token:
        return
    db.query(AdminSession).filter(AdminSession.token == token).delete()
    db.commit()
