"""Read-only console view of the CampusLink SQLite database.

Usage:
    python show_database.py              # schema, row counts, and key evidence
    python show_database.py users        # first rows of one table
    python show_database.py --tables     # table names only

Nothing is written: the database is opened in read-only mode.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "instance" / "campuslink.db"

PURPOSE = {
    "users": "students and administrators",
    "categories": "service categories",
    "services": "published listings",
    "service_requests": "seeker briefs",
    "offers": "provider bids on a request",
    "bookings": "agreed jobs (the hub)",
    "payments": "one escrow record per booking",
    "reviews": "three-dimension ratings",
    "disputes": "formal disagreements",
    "conversations": "one-to-one chat threads",
    "messages": "chat messages",
    "notifications": "in-app event feed",
    "wallet_transactions": "append-only money ledger",
}


def connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(f"Database not found: {path}\nRun: python seed.py --reset")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_names(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r["name"] for r in rows]


def heading(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def print_table(rows: list[sqlite3.Row], columns: list[str] | None = None) -> None:
    if not rows:
        print("  (no rows)")
        return
    columns = columns or list(rows[0].keys())
    data = [[("" if r[c] is None else str(r[c])) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in data)) for i, c in enumerate(columns)]
    print("  " + "  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for row in data:
        print("  " + "  ".join(v.ljust(w) for v, w in zip(row, widths)))


def overview(con: sqlite3.Connection, path: Path) -> None:
    tables = table_names(con)
    size = path.stat().st_size / 1024
    print(f"CampusLink database: {path}")
    print(f"SQLite file, {size:.0f} KB, {len(tables)} tables")

    heading("Schema and row counts")
    for name in tables:
        count = con.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
        print(f"  {name:22} {count:>4}   {PURPOSE.get(name, '')}")

    heading("Recent bookings (state machine in action)")
    print_table(
        con.execute(
            "SELECT id, reference, status, price, scheduled_at "
            "FROM bookings ORDER BY id DESC LIMIT 7"
        ).fetchall()
    )

    heading("Escrow records (5% fee withheld)")
    print_table(
        con.execute(
            "SELECT booking_id, amount, platform_fee, provider_amount, status "
            "FROM payments ORDER BY id DESC LIMIT 7"
        ).fetchall()
    )

    heading("Wallet ledger (append-only, balance after each entry)")
    print_table(
        con.execute(
            "SELECT id, user_id, amount, kind, balance_after "
            "FROM wallet_transactions ORDER BY id DESC LIMIT 7"
        ).fetchall()
    )

    heading("Provider reputation (cached, recomputed on events)")
    print_table(
        con.execute(
            "SELECT full_name, rating_avg, review_count, completion_rate, reputation_score "
            "FROM users WHERE review_count > 0 ORDER BY reputation_score DESC LIMIT 5"
        ).fetchall()
    )

    held = con.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'held'"
    ).fetchone()["total"]
    fees = con.execute(
        "SELECT COALESCE(SUM(platform_fee), 0) AS total FROM payments WHERE status = 'released'"
    ).fetchone()["total"]
    print()
    print(f"  Money currently in escrow : K{held:,.2f}")
    print(f"  Platform fees released    : K{fees:,.2f}")


def dump_table(con: sqlite3.Connection, name: str, limit: int = 10) -> None:
    if name not in table_names(con):
        sys.exit(f"Unknown table: {name}\nAvailable: {', '.join(table_names(con))}")
    total = con.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
    heading(f"{name} (showing {min(limit, total)} of {total})")
    print_table(con.execute(f'SELECT * FROM "{name}" LIMIT {limit}').fetchall())


def main() -> None:
    args = [a for a in sys.argv[1:]]
    db_path = DEFAULT_DB
    if "--db" in args:
        index = args.index("--db")
        db_path = Path(args[index + 1]).resolve()
        del args[index : index + 2]

    con = connect(db_path)
    try:
        if args and args[0] == "--tables":
            print("\n".join(table_names(con)))
        elif args:
            dump_table(con, args[0])
        else:
            overview(con, db_path)
    finally:
        con.close()


if __name__ == "__main__":
    main()
