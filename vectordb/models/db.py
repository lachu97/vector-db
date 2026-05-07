# vectordb/models/db.py

from sqlalchemy import (
    create_engine, Column, Integer, String, LargeBinary, JSON, Text,
    DateTime, ForeignKey, UniqueConstraint, Boolean, event, func, Float, Index,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

from vectordb.config import get_settings

Base = declarative_base()

# ------------------------------------------------------------------
# Lazy engine + session
# ------------------------------------------------------------------

_ENGINE = None
_SessionLocal = None


def _set_sqlite_pragma(engine):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        settings = get_settings()

        _ENGINE = create_engine(
            settings.db_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        _set_sqlite_pragma(_ENGINE)

    return _ENGINE


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False
        )
    return _SessionLocal


# ------------------------------------------------------------------
# BACKWARD COMPATIBILITY (CRITICAL — fixes your import error)
# ------------------------------------------------------------------

# These make existing imports work:
# from vectordb.models.db import SessionLocal, ENGINE

ENGINE = get_engine()
SessionLocal = get_session_local()


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())

    vectors = relationship("Vector", back_populates="collection", cascade="all, delete-orphan")


class Vector(Base):
    __tablename__ = "vectors"
    internal_id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=False, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False, index=True)
    meta = Column("metadata", JSON, nullable=True)
    vector = Column(LargeBinary, nullable=False)
    content = Column(Text, nullable=True)

    collection = relationship("Collection", back_populates="vectors")

    __table_args__ = (
        UniqueConstraint("collection_id", "external_id", name="uq_collection_external_id"),
    )


class KeyUsageLog(Base):
    __tablename__ = "key_usage_logs"
    id = Column(Integer, primary_key=True, index=True)
    key_id = Column(Integer, nullable=True, index=True)
    key_name = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    tier = Column(String, nullable=False, default="free")
    created_at = Column(DateTime, server_default=func.now())
    last_active_at = Column(DateTime, nullable=True)

    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    usage_summaries = relationship("UserUsageSummary", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")


class UserUsageSummary(Base):
    __tablename__ = "user_usage_summary"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    period = Column(String, nullable=False)
    request_count = Column(Integer, nullable=False, default=0)
    vector_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_user_usage_period"),
    )

    user = relationship("User", back_populates="usage_summaries")


# ------------------------------------------------------------------
# GraphRAG models
# ------------------------------------------------------------------

class GraphExtractionJob(Base):
    __tablename__ = "graph_extraction_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False)
    document_id = Column(Text, nullable=False)
    chunk_id = Column(Text, nullable=False)
    chunk_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending|processing|completed|failed
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_graph_extraction_jobs_status_created_at", "status", "created_at"),
        Index("ix_graph_extraction_jobs_document_id", "document_id"),
    )


class GraphEntity(Base):
    __tablename__ = "graph_entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False)
    entity_text = Column(Text, nullable=False)
    entity_type = Column(String, nullable=True)  # PERSON|ORG|CONCEPT|PLACE|EVENT
    document_id = Column(Text, nullable=False)
    chunk_id = Column(Text, nullable=False)
    vector_external_id = Column(Text, nullable=True)  # pointer to vectors.external_id
    extractor_version = Column(Text, nullable=False)
    model_name = Column(Text, nullable=False)
    extraction_timestamp = Column(DateTime, server_default=func.now())
    extraction_prompt_hash = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_graph_entities_collection_id", "collection_id"),
        Index("ix_graph_entities_collection_id_entity_text", "collection_id", "entity_text"),
        Index("ix_graph_entities_document_id", "document_id"),
    )


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id = Column(Integer, primary_key=True, autoincrement=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False)
    source_entity_id = Column(Integer, ForeignKey("graph_entities.id"), nullable=False)
    target_entity_id = Column(Integer, ForeignKey("graph_entities.id"), nullable=False)
    relation_type = Column(Text, nullable=False)
    weight = Column(Float, nullable=False, default=1.0)
    document_id = Column(Text, nullable=False)
    chunk_id = Column(Text, nullable=False)
    extractor_version = Column(Text, nullable=False)
    model_name = Column(Text, nullable=False)
    extraction_timestamp = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_graph_edges_source_entity_id", "source_entity_id"),
        Index("ix_graph_edges_target_entity_id", "target_entity_id"),
        Index("ix_graph_edges_document_id", "document_id"),
    )


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def init_db():
    engine = get_engine()
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        import logging
        logging.warning(f"DB init skipped: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()