import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session

DATABASE_URL = "sqlite:///./.data/freshledger.db"


def build_engine(url: str | None = None) -> Engine:
    explicit = url or os.getenv("DATABASE_URL")
    if not explicit and os.getenv("DB_HOST"):
        database = URL.create(
            "mysql+pymysql",
            username=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME"),
            query={"charset": "utf8mb4"},
        )
    else:
        database = make_url(explicit or DATABASE_URL)
    if database.get_backend_name() == "sqlite":
        if database.database and database.database != ":memory:":
            Path(database.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database, connect_args={"timeout": 15})

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

        return engine
    return create_engine(
        database, pool_pre_ping=True, pool_recycle=1800, isolation_level="READ COMMITTED"
    )


@contextmanager
def transaction(engine: Engine, *, write: bool = False) -> Iterator[Session]:
    with Session(engine) as session, session.begin():
        if engine.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")
        elif not write:
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        yield session


def store_now() -> datetime:
    return datetime.now(ZoneInfo(os.getenv("INVENTORY_TIMEZONE", "Asia/Kolkata")))


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def timestamp(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
