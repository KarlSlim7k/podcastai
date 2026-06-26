import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError
from app.config import settings


async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False, "timeout": 60},
    poolclass=NullPool,  # Fresh connection per session; fully closed on session close.
    # NullPool avoids stale-transaction lock issues that QueuePool can cause
    # with SQLite when background tasks run concurrently with request sessions.
)


@event.listens_for(async_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and busy timeout to prevent 'database is locked' errors.

    WAL allows concurrent readers alongside a single writer, and the busy
    timeout makes writers wait (up to 60s) instead of failing immediately
    when another connection holds the lock.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=60000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


async def db_retry(coro_factory, max_attempts: int = 5, base_delay: float = 0.5):
    """Retry a DB operation on SQLite 'database is locked' errors.

    ``coro_factory`` must be a zero-arg callable that returns a **fresh**
    coroutine each call (the previous attempt's session/transaction is dead).
    """
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_attempts - 1:
                await asyncio.sleep(base_delay * (attempt + 1))
                continue
            raise

sync_engine = create_engine(
    settings.database_sync_url,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_lightweight_migrations)


def _apply_lightweight_migrations(conn):
    """Add columns introduced after a table was first created.

    ``create_all`` only creates missing *tables*, never new columns on an
    existing one. For SQLite we additively ``ALTER TABLE ... ADD COLUMN`` for
    nullable columns — a non-destructive, idempotent operation guarded by a
    PRAGMA check so re-runs are no-ops. This keeps existing dev/prod DBs
    working without a full migration tool.
    """
    from sqlalchemy import text

    # (table, column, column DDL type)
    additive_columns = [
        ("vertical_renders", "video_transform", "JSON"),
    ]
    for table, column, ddl in additive_columns:
        try:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        except Exception:
            # Never let a best-effort migration crash startup.
            pass
