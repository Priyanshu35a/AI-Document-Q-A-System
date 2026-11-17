import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError
from app.core.config import settings

logger = logging.getLogger(__name__)

db_url = settings.get_database_url()

try:
    if "postgresql" in db_url:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"connect_timeout": 2}
        )
        # Attempt lightweight probe
        with engine.connect() as conn:
            pass
    else:
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
        )
except (OperationalError, Exception) as e:
    logger.warning(
        f"Could not connect to primary database ({db_url}): {e}. "
        "Falling back to local SQLite database (rag.db)."
    )
    db_url = "sqlite:///./rag.db"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
