"""
backend/database.py — SQLAlchemy Models and SQLite Engine
"""
from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from backend.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(String(100), primary_key=True)  # slug, e.g., ty_ecs_b_ss_theory
    name = Column(String(200), nullable=False)
    code = Column(String(50), nullable=False)
    class_name = Column(String(50), nullable=False)  # e.g., Semester 5 or T.Y.B.TECH
    branch = Column(String(100), default="Electronics & Computer Science", nullable=True)  # e.g., Electronics & Computer Science
    division = Column(String(10), nullable=False)    # e.g., B
    type = Column(String(20), default="Theory")      # Theory / Practical / Tutorial
    faculty = Column(String(100), nullable=False)    # e.g., SHP
    academic_year = Column(String(50), default="2026-27 (Odd)")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)     # Soft-delete timestamp

    # Relationships
    students = relationship("Student", back_populates="subject", cascade="all, delete-orphan", order_by="Student.sr_no")
    scans = relationship("Scan", back_populates="subject", cascade="all, delete-orphan", order_by="Scan.uploaded_at.desc()")
    sessions = relationship("Session", back_populates="subject", cascade="all, delete-orphan", order_by="Session.date")


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String(100), ForeignKey("subjects.id"), nullable=False)
    roll_no = Column(String(30), nullable=False)  # e.g. 24108B0001
    name = Column(String(200), nullable=False)
    batch = Column(Integer, default=1)            # 1 or 2
    sr_no = Column(Integer, nullable=False)

    subject = relationship("Subject", back_populates="students")
    attendance_records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String(100), ForeignKey("subjects.id"), nullable=False)
    image_path = Column(String(500), nullable=False)
    week_no = Column(String(20), nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String(20), default="preview")  # 'preview' | 'committed'
    raw_result_json = Column(Text, nullable=True)

    subject = relationship("Subject", back_populates="scans")
    sessions = relationship("Session", back_populates="scan")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String(100), ForeignKey("subjects.id"), nullable=False)
    date = Column(String(20), nullable=False)  # ISO YYYY-MM-DD
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=True)

    subject = relationship("Subject", back_populates="sessions")
    scan = relationship("Scan", back_populates="sessions")
    records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    status = Column(String(10), nullable=False)     # P, A, NM, NA
    source = Column(String(20), default="ai")       # 'ai' | 'teacher'
    confidence = Column(Float, default=1.0)

    student = relationship("Student", back_populates="attendance_records")
    session = relationship("Session", back_populates="records")


class ScanSession(Base):
    __tablename__ = "scan_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String(100), ForeignKey("subjects.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String(20), default="preview")  # 'preview' | 'committed'

    pages = relationship("ScanPage", back_populates="session", cascade="all, delete-orphan")


class ScanPage(Base):
    __tablename__ = "scan_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("scan_sessions.id"), nullable=False)
    image_path = Column(String(500), nullable=False)
    image_hash = Column(String(64), nullable=False)
    page_index = Column(Integer, default=1)
    quality_score = Column(Float, default=1.0)
    engine_used = Column(String(50), default="attendai_vision")

    session = relationship("ScanSession", back_populates="pages")


class TrainingCell(Base):
    __tablename__ = "training_cells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_path = Column(String(500), nullable=False)
    predicted_token = Column(String(30), nullable=False)
    final_label = Column(String(10), nullable=False)   # P, A, NM, NA
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(bind=engine)
    # Safe migration: ensure 'branch' column exists on 'subjects' table
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(subjects)").fetchall()]
            if "branch" not in cols:
                conn.exec_driver_sql("ALTER TABLE subjects ADD COLUMN branch VARCHAR(100) DEFAULT 'Electronics & Computer Science'")
                conn.commit()
    except Exception:
        pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
