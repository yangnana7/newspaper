#!/usr/bin/env python3
"""
Apply core DB indexes from db/indexes_core.sql.
"""
import os
import psycopg


def main() -> int:
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    sql_path = os.path.join(os.path.dirname(__file__), "..", "db", "indexes_core.sql")
    sql_path = os.path.normpath(sql_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(dsn) as conn:
        conn.execute(sql)
    print("indexes_applied=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

