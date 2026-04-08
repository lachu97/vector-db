# vectordb/models/db.py
from sqlalchemy import (
    create_engine, Column, Integer, String, LargeBinary, JSON, Text,
    DateTime, ForeignKey, UniqueConstraint, Boolean, event, func,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

from vectordb.config import get_settings

settings = get_settings()

ENGINE = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
    pool_size=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Base = declarative_base()


# ------------------------------------------------------------------
# Enable WAL mode and performance pragmas for SQLite
# ------------------------------------------------------------------
@event.listens_for(ENGINE, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")  # cosine, l2, ip
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    vectors = relationship("Vector", back_populates="collection", cascade="all, delete-orphan")


class Vector(Base):
    __tablename__ = "vectors"
    internal_id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=False, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False, index=True)
    meta = Column("metadata", JSON, nullable=True)
    vector = Column(LargeBinary, nullable=False)  # binary float32 bytes
    content = Column(Text, nullable=True)  # optional text content for hybrid search

    collection = relationship("Collection", back_populates="vectors")

    __table_args__ = (
        UniqueConstraint("collection_id", "external_id", name="uq_collection_external_id"),
    )


class KeyUsageLog(Base):
    __tablename__ = "key_usage_logs"
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(Integer, nullable=True, index=True)   # null for bootstrap key
    key_name = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin", "readwrite", "readonly"
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)       # None = never expires
    last_used_at = Column(DateTime, nullable=True)     # updated on every authenticated request


def init_db():
    Base.metadata.create_all(bind=ENGINE)


def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
