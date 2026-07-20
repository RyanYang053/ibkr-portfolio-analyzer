from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _build_engine():
    url = str(settings.database_url)
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            pool_pre_ping=True,
        )
    return create_engine(url, pool_pre_ping=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record) -> None:
    url = str(settings.database_url)
    if url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.close()
        return

    if not url.startswith("postgresql"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("SET app.audit_mutations_blocked = 'on'")
    cursor.close()
