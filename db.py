# db.py
from sqlalchemy import create_engine, Column, Integer, String, LargeBinary, JSON
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite file (local). check_same_thread False because FastAPI uses threads.
ENGINE = create_engine("sqlite:///./vectors.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Base = declarative_base()

class Vector(Base):
    __tablename__ = "vectors"
    internal_id = Column(Integer, primary_key=True, index=True)  # internal int id (hnswlib)
    external_id = Column(String, unique=True, index=True, nullable=False)  # user id
    meta = Column('metadata', JSON, nullable=True)  # rename attribute to `meta` to avoid conflict
    vector = Column(JSON, nullable=False)  # raw float32 bytes

def init_db():
    Base.metadata.create_all(bind=ENGINE)
