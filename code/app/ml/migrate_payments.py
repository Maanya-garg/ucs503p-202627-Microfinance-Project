"""
One-off, idempotent migration for the payments/targeted-requests feature
(docs/API_CONTRACT_PAYMENTS.md §1). Run directly against the existing
`data/microfin.db` -- does NOT touch `data_gen.py`'s synthetic-data
generation and does NOT drop or recreate any existing table/row. Safe to
re-run: every step checks current state first and skips work already done.

What it does, in order:
1. ALTERs `individuals` in place to add `wallet_balance` (FLOAT), if not
   already present.
2. ALTERs `loan_requests` in place to add `target_lender_id` (INTEGER,
   FK -> lenders.id), if not already present, plus a supporting index.
3. Seeds `wallet_balance = round(monthly_income * 1.5, 2)` on every
   `Individual` row WHERE wallet_balance IS NULL. This IS NULL guard is
   critical: it's what makes the script safe to re-run after borrowers have
   made live payments -- a second run must never reset a balance that's
   already moved from a real payment back to 1.5x monthly income.

Run with:  python -m app.ml.migrate_payments
"""
import sqlite3

from app.config import DATABASE_URL, DATA_DIR


def _sqlite_path() -> str:
    # DATABASE_URL is like "sqlite:///C:/.../data/microfin.db"
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("migrate_payments.py only supports the SQLite DATABASE_URL used by this project")
    return str(DATA_DIR / "microfin.db")


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_columns():
    """Raw ALTER TABLE via sqlite3 -- SQLAlchemy's create_all can't add
    columns to a table that already exists, so this part has to be raw SQL."""
    con = sqlite3.connect(_sqlite_path())
    try:
        cur = con.cursor()

        if not _column_exists(cur, "individuals", "wallet_balance"):
            cur.execute("ALTER TABLE individuals ADD COLUMN wallet_balance FLOAT")
            print("  + individuals.wallet_balance")
        else:
            print("  = individuals.wallet_balance already present")

        if not _column_exists(cur, "loan_requests", "target_lender_id"):
            cur.execute("ALTER TABLE loan_requests ADD COLUMN target_lender_id INTEGER")
            print("  + loan_requests.target_lender_id")
        else:
            print("  = loan_requests.target_lender_id already present")

        idx_name = "ix_loan_requests_target_lender_id"
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx_name,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE INDEX {idx_name} ON loan_requests(target_lender_id)")
            print(f"  + index {idx_name}")
        else:
            print(f"  = index {idx_name} already present")

        con.commit()
    finally:
        con.close()


def seed_wallet_balances():
    """UPDATE only rows WHERE wallet_balance IS NULL -- safe to re-run after
    live payments have moved real balances away from the seeded value."""
    con = sqlite3.connect(_sqlite_path())
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE individuals "
            "SET wallet_balance = ROUND(COALESCE(monthly_income, 0.0) * 1.5, 2) "
            "WHERE wallet_balance IS NULL"
        )
        print(f"  seeded wallet_balance on {cur.rowcount} individual(s)")
        con.commit()
    finally:
        con.close()


def main():
    print("1. Adding wallet_balance / target_lender_id columns...")
    add_columns()
    print("2. Seeding wallet balances (IS NULL guarded)...")
    seed_wallet_balances()
    print("Done.")


if __name__ == "__main__":
    main()
