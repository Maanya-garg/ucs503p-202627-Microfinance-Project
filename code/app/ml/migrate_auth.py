"""
One-off, idempotent migration for the 4-role auth redesign (docs/SPEC.md §6,
docs/API_CONTRACT.md §11). Run directly against the existing `data/microfin.db`
-- does NOT touch `data_gen.py`'s synthetic-data generation and does NOT drop
or recreate any existing table/row. Safe to re-run: every step checks current
state first and skips work already done.

What it does, in order:
1. ALTERs `lenders` and `shgs` in place to add `username` (unique) and
   `password_hash` columns, if not already present.
2. ALTERs `shg_lender_links` to add `initiated_by_role`, backfilling every
   existing row to `"shg"` (accurate: only the SHG-initiated flow existed
   before lender auth was added).
3. Creates the three new session tables (`lender_sessions`, `shg_sessions`,
   `admin_sessions`) via SQLAlchemy's `create_all`, which only creates tables
   that don't already exist -- never touches existing ones.
4. Seeds `username`/`password_hash` on every existing `Lender`/`SHG` row that
   doesn't already have a `password_hash` set. Username = slug of `name`
   (lowercase, spaces/non-alnum -> hyphens), with `-{id}` appended on
   collision. Password = the same demo convention as borrowers
   (`auth_service.DEMO_PASSWORD`, i.e. "password123"), hashed with the
   existing `hash_password`.

Run with:  python -m app.ml.migrate_auth
"""
import re
import sqlite3

from sqlalchemy import inspect, text

from app.config import DATABASE_URL, DATA_DIR
from app.db import Base, SessionLocal, engine
from app.models import Lender, SHG, SHGLenderLink
from app.services import auth_service


def _sqlite_path() -> str:
    # DATABASE_URL is like "sqlite:///C:/.../data/microfin.db"
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("migrate_auth.py only supports the SQLite DATABASE_URL used by this project")
    return str(DATA_DIR / "microfin.db")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "user"


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_credential_columns():
    """Raw ALTER TABLE via sqlite3 -- SQLAlchemy's create_all can't add
    columns to a table that already exists, so this part has to be raw SQL."""
    con = sqlite3.connect(_sqlite_path())
    try:
        cur = con.cursor()
        for table in ("lenders", "shgs"):
            if not _column_exists(cur, table, "username"):
                cur.execute(f"ALTER TABLE {table} ADD COLUMN username VARCHAR(100)")
                print(f"  + {table}.username")
            else:
                print(f"  = {table}.username already present")
            if not _column_exists(cur, table, "password_hash"):
                cur.execute(f"ALTER TABLE {table} ADD COLUMN password_hash VARCHAR(150)")
                print(f"  + {table}.password_hash")
            else:
                print(f"  = {table}.password_hash already present")
            # Unique index -- SQLite ALTER TABLE can't add a UNIQUE constraint
            # directly, but a unique index enforces the same thing.
            idx_name = f"ix_{table}_username_unique"
            cur.execute(
                f"SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx_name,)
            )
            if cur.fetchone() is None:
                cur.execute(f"CREATE UNIQUE INDEX {idx_name} ON {table}(username)")
                print(f"  + unique index {idx_name}")
            else:
                print(f"  = unique index {idx_name} already present")

        if not _column_exists(cur, "shg_lender_links", "initiated_by_role"):
            cur.execute(
                "ALTER TABLE shg_lender_links ADD COLUMN initiated_by_role VARCHAR(6)"
            )
            print("  + shg_lender_links.initiated_by_role")
        else:
            print("  = shg_lender_links.initiated_by_role already present")

        # Backfill (safe to re-run -- only touches NULLs).
        cur.execute(
            "UPDATE shg_lender_links SET initiated_by_role = 'shg' WHERE initiated_by_role IS NULL"
        )
        print(f"  backfilled initiated_by_role on {cur.rowcount} row(s)")

        con.commit()
    finally:
        con.close()


def create_session_tables():
    """Only creates tables that don't exist yet -- never touches existing ones."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    to_create = {"lender_sessions", "shg_sessions", "admin_sessions"} - existing
    Base.metadata.create_all(bind=engine)
    if to_create:
        print(f"  created table(s): {', '.join(sorted(to_create))}")
    else:
        print("  session tables already present")


def seed_credentials():
    db = SessionLocal()
    try:
        n_lender = 0
        used_usernames: set[str] = set()
        for row in db.execute(text("SELECT username FROM lenders WHERE username IS NOT NULL")):
            used_usernames.add(row[0])
        for row in db.execute(text("SELECT username FROM shgs WHERE username IS NOT NULL")):
            used_usernames.add(row[0])

        for lender in db.query(Lender).order_by(Lender.id).all():
            if lender.password_hash:
                continue
            base = _slugify(lender.name)
            username = base if base not in used_usernames else f"{base}-{lender.id}"
            used_usernames.add(username)
            lender.username = username
            lender.password_hash = auth_service.hash_password(auth_service.DEMO_PASSWORD)
            n_lender += 1

        n_shg = 0
        for shg in db.query(SHG).order_by(SHG.id).all():
            if shg.password_hash:
                continue
            base = _slugify(shg.name)
            username = base if base not in used_usernames else f"{base}-{shg.id}"
            used_usernames.add(username)
            shg.username = username
            shg.password_hash = auth_service.hash_password(auth_service.DEMO_PASSWORD)
            n_shg += 1

        db.commit()
        print(f"  seeded credentials for {n_lender} lender(s), {n_shg} SHG(s)")
    finally:
        db.close()


def main():
    print("1. Adding credential columns / initiated_by_role...")
    add_credential_columns()
    print("2. Creating new session tables...")
    create_session_tables()
    print("3. Seeding lender/SHG credentials...")
    seed_credentials()
    print("Done.")


if __name__ == "__main__":
    main()
