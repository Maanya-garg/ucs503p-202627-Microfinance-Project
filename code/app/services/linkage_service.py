"""
Stage 4: SHG <-> Lender linkage. Deliberately a plain approve/reject table,
not a negotiation workflow -- per the project plan, that's out of scope for
the demo. An SHG requests a link to a lender (or a lender proactively offers
one -- either side can initiate), and whichever side didn't initiate approves
or rejects it. Once Approved, the lender can see that SHG's members in the
matching service (Stage 5); Pending/Rejected links are invisible to matching.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models import SHG, Lender, SHGLenderLink


class LinkageError(ValueError):
    pass


def request_link(db: Session, shg_id: int, lender_id: int, notes: str | None = None,
                  initiated_by_role: str = "shg") -> SHGLenderLink:
    shg = db.get(SHG, shg_id)
    lender = db.get(Lender, lender_id)
    if shg is None:
        raise LinkageError(f"SHG {shg_id} not found")
    if lender is None:
        raise LinkageError(f"Lender {lender_id} not found")

    existing = (
        db.query(SHGLenderLink)
        .filter(SHGLenderLink.shg_id == shg_id, SHGLenderLink.lender_id == lender_id)
        .first()
    )
    if existing is not None:
        raise LinkageError(
            f"A link between SHG {shg_id} and lender {lender_id} already exists "
            f"(status={existing.status}). Use decide_link to change it."
        )

    link = SHGLenderLink(shg_id=shg_id, lender_id=lender_id, status="Pending", requested_date=date.today(),
                          notes=notes, initiated_by_role=initiated_by_role)
    db.add(link)
    db.flush()
    return link


def decide_link(db: Session, link_id: int, approve: bool, notes: str | None = None) -> SHGLenderLink:
    link = db.get(SHGLenderLink, link_id)
    if link is None:
        raise LinkageError(f"Link {link_id} not found")
    if link.status != "Pending":
        raise LinkageError(f"Link {link_id} already decided (status={link.status})")

    link.status = "Approved" if approve else "Rejected"
    link.decided_date = date.today()
    if notes:
        link.notes = notes
    db.flush()
    return link


def approved_lenders_for_shg(db: Session, shg_id: int) -> list[Lender]:
    return (
        db.query(Lender)
        .join(SHGLenderLink, SHGLenderLink.lender_id == Lender.id)
        .filter(SHGLenderLink.shg_id == shg_id, SHGLenderLink.status == "Approved")
        .all()
    )


def approved_shgs_for_lender(db: Session, lender_id: int) -> list[SHG]:
    return (
        db.query(SHG)
        .join(SHGLenderLink, SHGLenderLink.shg_id == SHG.id)
        .filter(SHGLenderLink.lender_id == lender_id, SHGLenderLink.status == "Approved")
        .all()
    )
