"""Database layer: SQLAlchemy 2.0 Core, Postgres in production, SQLite for dev/tests."""
import os

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, MetaData, String, Table,
    Text, CheckConstraint, PrimaryKeyConstraint, create_engine, event, func,
)
from sqlalchemy.pool import StaticPool

load_dotenv()  # read .env for local runs; real environment variables win over it

metadata = MetaData()

# BigInteger on Postgres; plain Integer on SQLite (SQLite only autoincrements INTEGER keys).
ID = BigInteger().with_variant(Integer, "sqlite")

users = Table(
    "users", metadata,
    Column("id", ID, primary_key=True),
    Column("email", String, unique=True, nullable=False),
    Column("username", String, nullable=False),  # the display name, shown as typed
    Column("password_hash", String, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

documents = Table(
    "documents", metadata,
    Column("id", ID, primary_key=True),
    Column("owner_id", ID, ForeignKey("users.id"), nullable=False),
    Column("title", String, nullable=False),
    Column("content", Text, nullable=False, server_default=""),  # sanitized HTML
    Column("content_hash", String, nullable=False),              # sha256 hex of content
    Column("updated_by", ID, ForeignKey("users.id")),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

shares = Table(
    "shares", metadata,
    Column("document_id", ID, ForeignKey("documents.id", ondelete="CASCADE")),
    Column("user_id", ID, ForeignKey("users.id", ondelete="CASCADE")),
    Column("role", String, nullable=False),
    PrimaryKeyConstraint("document_id", "user_id"),
    CheckConstraint("role in ('viewer','editor')", name="shares_role_check"),
)


def make_engine(url=None):
    """Build an engine from `url`, else $DATABASE_URL, else a local SQLite file."""
    url = url or os.environ.get("DATABASE_URL") or "sqlite:///./dev.db"
    # Supabase hands out postgresql://...; SQLAlchemy needs to be told to use psycopg 3.
    if url.startswith(("postgres://", "postgresql://")):
        url = "postgresql+psycopg://" + url.split("://", 1)[1]

    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared connection, or each would get its own empty DB
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(conn, _):  # SQLite ignores foreign keys unless asked
            conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, pool_pre_ping=True)


engine = make_engine()


def init_db():
    """Create tables if missing. On Postgres also turn on Row Level Security (no policies)."""
    metadata.create_all(engine)
    with engine.begin() as conn:  # one transaction, so start-up costs one extra round trip, not two
        # Names are unique ignoring case ("Bob" and "bob" are the same name) but shown as typed. This is a separate
        # statement because create_all skips tables that already exist, and a database made before this rule has none.
        # (Those older databases also keep their original case-sensitive unique constraint on username. It is harmless.)
        conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_idx ON users (lower(username))")
        if engine.dialect.name == "postgresql":
            for table in metadata.tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
