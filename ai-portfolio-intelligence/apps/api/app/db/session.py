from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@event.listens_for(engine, "connect")
def _configure_connection(dbapi_connection, _connection_record) -> None:
    if not str(settings.database_url).startswith("postgresql"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("SET app.audit_mutations_blocked = 'on'")
    cursor.close()
