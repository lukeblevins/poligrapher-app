import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# Default to a local SQLite file so the app runs with zero external setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./poligrapher.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False because background pipeline/scoring tasks
# run in a ThreadPoolExecutor and open their own sessions off the main thread.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # WAL lets readers proceed while a background task holds a write lock.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
