import os
import psycopg
from pgvector.psycopg import register_vector


def connect():
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    conn = psycopg.connect(dsn)
    register_vector(conn)
    conn.execute("SET TIME ZONE 'UTC'")
    return conn

