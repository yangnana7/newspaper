import os
try:
    import psycopg  # type: ignore
    from pgvector.psycopg import register_vector  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore
    def register_vector(conn):  # type: ignore
        return None


def connect():
    if psycopg is None:
        raise RuntimeError("psycopg is required for DB connections")
    dsn = os.environ.get("DATABASE_URL", "postgresql://127.0.0.1/newshub")
    conn = psycopg.connect(dsn)
    register_vector(conn)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn
