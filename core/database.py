import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SQLITE_PATH = os.path.join(_PROJECT_ROOT, "data", "liver_rag_api.db")
os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)


class Base(DeclarativeBase):
    pass


DATABASE_URL = "sqlite:///" + os.path.abspath(_SQLITE_PATH).replace("\\", "/")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    import core.models  # noqa: F401 — register ORM metadata

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
