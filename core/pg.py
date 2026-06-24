import os

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional until PostgreSQL is configured
    psycopg = None
    dict_row = None


def postgres_dsn():
    if os.getenv("POSTGRES_DSN"):
        return os.getenv("POSTGRES_DSN")
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DATABASE", "ai_bidding")
    auth = user if not password else f"{user}:{password}"
    return f"postgresql://{auth}@{host}:{port}/{database}"


def pg_available():
    return bool(psycopg and postgres_dsn())


def get_pg():
    if not psycopg:
        raise RuntimeError("psycopg is not installed. Install psycopg[binary] to use PostgreSQL RAG.")
    dsn = postgres_dsn()
    if not dsn:
        raise RuntimeError("PostgreSQL RAG is not configured. Set POSTGRES_DSN or POSTGRES_* variables.")
    return psycopg.connect(dsn, row_factory=dict_row)
