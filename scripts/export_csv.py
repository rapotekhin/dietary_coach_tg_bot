"""Экспорт всех таблиц SQLite в CSV.

Использование:
    python scripts/export_csv.py [--db sqlite:///./dietary_coach.db] [--out ./exports]

По умолчанию читает из ./dietary_coach.db и пишет CSV в ./exports/.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path


def _resolve_db_path(arg: str | None) -> Path:
    if arg is None:
        return Path("dietary_coach.db")
    if arg.startswith("sqlite:///"):
        return Path(arg.replace("sqlite:///", "", 1))
    if arg.startswith("sqlite+aiosqlite:///"):
        return Path(arg.replace("sqlite+aiosqlite:///", "", 1))
    return Path(arg)


def export(db_path: Path, out_dir: Path) -> None:
    if not db_path.exists():
        print(f"DB file not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'"
        )
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            print("No user tables in DB.")
            return
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            csv_path = out_dir / f"{table}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if rows:
                    writer.writerow(rows[0].keys())
                    for r in rows:
                        writer.writerow(list(r))
                else:
                    cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                    writer.writerow(cols)
            print(f"  -> {csv_path}  ({len(rows)} rows)")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Экспорт SQLite -> CSV")
    parser.add_argument("--db", default=None, help="путь к .db или sqlite URL")
    parser.add_argument("--out", default="./exports", help="директория для CSV")
    args = parser.parse_args()
    db = _resolve_db_path(args.db)
    out = Path(args.out)
    print(f"Export from {db} to {out}...")
    export(db, out)
    print("Done.")


if __name__ == "__main__":
    main()
