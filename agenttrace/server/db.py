from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///agenttrace.db"

# check_same_thread=False: SQLite's default is to refuse multi-threaded access;
# SQLAlchemy handles thread safety, so we disable the warning.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Yield a database session per request, then close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
