"""
backend/routes/subjects.py — Subject Management & Roster CRUD Endpoints
"""
import re
import shutil
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session
import pandas as pd
import io

from backend.config import settings
from backend.database import get_db, Subject, Student, Session as DbSession, AttendanceRecord, Scan
from backend.schemas import (
    SubjectCreate,
    SubjectResponse,
    SubjectDetailResponse,
    SubjectStats,
    StudentCreate,
    StudentResponse,
    StudentUpdate,
)

router = APIRouter(prefix="/api/subjects", tags=["Subjects"])


def generate_subject_slug(data: SubjectCreate) -> str:
    parts = [
        re.sub(r"[^a-zA-Z0-9]", "", data.class_name.lower()),
        re.sub(r"[^a-zA-Z0-9]", "", data.division.lower()),
        re.sub(r"[^a-zA-Z0-9]", "", data.code.lower()),
        re.sub(r"[^a-zA-Z0-9]", "", data.type.lower()),
    ]
    return "_".join(p for p in parts if p)


def compute_subject_stats(subject: Subject, db: Session) -> SubjectStats:
    enrolled = len(subject.students)
    sessions = db.query(DbSession).filter(DbSession.subject_id == subject.id).all()
    total_sessions = len(sessions)

    if total_sessions == 0 or enrolled == 0:
        return SubjectStats(
            total_sessions=total_sessions,
            enrolled_students=enrolled,
            average_attendance_pct=0.0,
            students_below_75=0,
        )

    # Calculate average attendance % and count students below 75%
    session_ids = [s.id for s in sessions]
    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id.in_(session_ids)).all()

    student_records = {}
    for r in records:
        student_records.setdefault(r.student_id, []).append(r.status)

    students_below_75 = 0
    for s in subject.students:
        s_marks = student_records.get(s.id, [])
        s_p = sum(1 for m in s_marks if m == "P")
        s_held = sum(1 for m in s_marks if m in ("P", "A"))
        if s_held > 0 and (s_p / s_held * 100.0) < 75.0:
            students_below_75 += 1

    p_count = sum(1 for r in records if r.status == "P")
    held_count = sum(1 for r in records if r.status in ("P", "A"))

    avg_pct = round((p_count / held_count * 100), 1) if held_count > 0 else 0.0

    return SubjectStats(
        total_sessions=total_sessions,
        enrolled_students=enrolled,
        average_attendance_pct=avg_pct,
        students_below_75=students_below_75,
    )


# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[SubjectResponse])
def list_subjects(db: Session = Depends(get_db)):
    """List all active subjects with attendance statistics."""
    subjects = db.query(Subject).filter(Subject.deleted_at.is_(None)).all()
    result = []
    for s in subjects:
        stats = compute_subject_stats(s, db)
        resp = SubjectResponse(
            id=s.id,
            name=s.name,
            code=s.code,
            class_name=s.class_name,
            branch=getattr(s, "branch", None) or "Electronics & Computer Science",
            division=s.division,
            type=s.type,
            faculty=s.faculty,
            academic_year=s.academic_year,
            created_at=s.created_at,
            stats=stats,
        )
        result.append(resp)
    return result


@router.post("", response_model=SubjectDetailResponse, status_code=status.HTTP_201_CREATED)
def create_subject(data: SubjectCreate, db: Session = Depends(get_db)):
    """Create a new subject and optionally seed its student roster."""
    slug = data.id or generate_subject_slug(data)

    existing = db.query(Subject).filter(Subject.id == slug).first()
    if existing and existing.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subject with ID '{slug}' already exists.",
        )

    if existing and existing.deleted_at is not None:
        # Restore soft-deleted subject
        existing.deleted_at = None
        existing.name = data.name
        existing.faculty = data.faculty
        if data.branch:
            existing.branch = data.branch
        subject = existing
    else:
        subject = Subject(
            id=slug,
            name=data.name,
            code=data.code,
            class_name=data.class_name,
            branch=data.branch or "Electronics & Computer Science",
            division=data.division,
            type=data.type,
            faculty=data.faculty,
            academic_year=data.academic_year,
        )
        db.add(subject)

    # Create dedicated folder for the subject
    subject_dir = settings.SUBJECTS_DIR / slug
    (subject_dir / "scans").mkdir(parents=True, exist_ok=True)

    db.commit()
    db.refresh(subject)

    # Insert roster if provided
    if data.roster:
        seen_rolls = set()
        for idx, student_in in enumerate(data.roster, start=1):
            if student_in.roll_no in seen_rolls:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate roll number '{student_in.roll_no}' in roster.",
                )
            seen_rolls.add(student_in.roll_no)
            student = Student(
                subject_id=subject.id,
                sr_no=student_in.sr_no or idx,
                roll_no=student_in.roll_no,
                name=student_in.name,
                batch=student_in.batch,
            )
            db.add(student)
        db.commit()
        db.refresh(subject)

    stats = compute_subject_stats(subject, db)
    return SubjectDetailResponse(
        id=subject.id,
        name=subject.name,
        code=subject.code,
        class_name=subject.class_name,
        branch=getattr(subject, "branch", None) or "Electronics & Computer Science",
        division=subject.division,
        type=subject.type,
        faculty=subject.faculty,
        academic_year=subject.academic_year,
        created_at=subject.created_at,
        stats=stats,
        students=[StudentResponse.model_validate(st) for st in subject.students],
        scans_count=0,
        sessions=[],
    )


@router.get("/{subject_id}", response_model=SubjectDetailResponse)
def get_subject_detail(subject_id: str, db: Session = Depends(get_db)):
    """Get subject details, enrolled students, sessions, and stats."""
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    stats = compute_subject_stats(subject, db)
    sessions = db.query(DbSession).filter(DbSession.subject_id == subject.id).order_by(DbSession.date).all()
    scans_count = db.query(Scan).filter(Scan.subject_id == subject.id).count()

    students_sorted = list(subject.students)
    students_sorted.sort(key=lambda s: (s.batch, s.sr_no or 0, s.roll_no))
    for idx, st in enumerate(students_sorted, start=1):
        if st.sr_no != idx:
            st.sr_no = idx
    db.commit()

    return SubjectDetailResponse(
        id=subject.id,
        name=subject.name,
        code=subject.code,
        class_name=subject.class_name,
        branch=getattr(subject, "branch", None) or "Electronics & Computer Science",
        division=subject.division,
        type=subject.type,
        faculty=subject.faculty,
        academic_year=subject.academic_year,
        created_at=subject.created_at,
        stats=stats,
        students=[StudentResponse.model_validate(st) for st in students_sorted],
        scans_count=scans_count,
        sessions=[s.date for s in sessions],
    )


@router.delete("/{subject_id}", status_code=status.HTTP_200_OK)
def delete_subject(subject_id: str, permanent: bool = Query(False), db: Session = Depends(get_db)):
    """Soft delete or permanently remove subject and related files."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    if permanent:
        subject_dir = settings.SUBJECTS_DIR / subject_id
        if subject_dir.exists():
            shutil.rmtree(subject_dir, ignore_errors=True)
        db.delete(subject)
        message = f"Subject '{subject_id}' permanently deleted."
    else:
        subject.deleted_at = datetime.now(timezone.utc)
        message = f"Subject '{subject_id}' archived (soft-deleted)."

    db.commit()
    return {"message": message, "subject_id": subject_id}


@router.put("/{subject_id}/roster", response_model=List[StudentResponse])
def update_roster_json(
    subject_id: str,
    roster: List[StudentCreate],
    db: Session = Depends(get_db),
):
    """Replace or seed the student roster for a subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    # Remove existing students
    db.query(Student).filter(Student.subject_id == subject_id).delete()

    seen_rolls = set()
    new_students = []
    for idx, s in enumerate(roster, start=1):
        if s.roll_no in seen_rolls:
            raise HTTPException(status_code=400, detail=f"Duplicate roll number: {s.roll_no}")
        seen_rolls.add(s.roll_no)
        student = Student(
            subject_id=subject_id,
            sr_no=s.sr_no or idx,
            roll_no=s.roll_no,
            name=s.name,
            batch=s.batch,
        )
        db.add(student)
        new_students.append(student)

    db.commit()
    db.refresh(subject)
    return [StudentResponse.model_validate(st) for st in subject.students]


@router.post("/{subject_id}/roster/upload", response_model=List[StudentResponse])
async def upload_roster_file(
    subject_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV or Excel file containing columns: Roll No, Name, Batch (optional)."""
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    contents = await file.read()
    filename = file.filename.lower()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    # Normalize column names
    col_map = {c.lower().replace("_", "").replace(" ", ""): c for c in df.columns}
    roll_col = next((col_map[k] for k in ["rollno", "rollnumber", "roll"] if k in col_map), None)
    name_col = next((col_map[k] for k in ["name", "studentname"] if k in col_map), None)
    batch_col = next((col_map[k] for k in ["batch", "batchno"] if k in col_map), None)
    sr_col = next((col_map[k] for k in ["srno", "sr", "serialno"] if k in col_map), None)

    if not roll_col or not name_col:
        raise HTTPException(
            status_code=400,
            detail="File must contain at least 'Roll No' and 'Name' columns.",
        )

    roster_list: List[StudentCreate] = []
    for idx, row in df.iterrows():
        raw_roll = str(row[roll_col]).strip()
        raw_name = str(row[name_col]).strip()
        batch_val = int(row[batch_col]) if batch_col and pd.notna(row[batch_col]) else 1
        sr_val = int(row[sr_col]) if sr_col and pd.notna(row[sr_col]) else idx + 1

        try:
            student = StudentCreate(
                sr_no=sr_val,
                roll_no=raw_roll,
                name=raw_name,
                batch=batch_val,
            )
            roster_list.append(student)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Row {idx+1}: {err}")

    return update_roster_json(subject_id=subject_id, roster=roster_list, db=db)


@router.patch("/{subject_id}/students/{student_id}", response_model=StudentResponse)
def update_student(
    subject_id: str,
    student_id: int,
    data: StudentUpdate,
    db: Session = Depends(get_db),
):
    """Update student name and/or batch inline."""
    student = db.query(Student).filter(Student.id == student_id, Student.subject_id == subject_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    if data.name is not None:
        c_name = data.name.strip().upper()
        if c_name == student.roll_no.upper():
            raise HTTPException(status_code=400, detail="Roll number cannot be used as student name.")
        student.name = c_name
    if data.batch is not None:
        student.batch = data.batch
    if data.roll_no is not None:
        student.roll_no = data.roll_no.strip().upper()

    db.commit()

    # Re-order and regenerate serials
    all_s = db.query(Student).filter(Student.subject_id == subject_id).all()
    all_s.sort(key=lambda s: (s.batch, s.sr_no or 0, s.roll_no))
    for idx, s in enumerate(all_s, start=1):
        s.sr_no = idx
    db.commit()
    db.refresh(student)

    # Rebuild master Excel if it exists
    from scripts.repair_roster import repair_subject_roster
    try:
        repair_subject_roster(subject_id=subject_id, sample_30_only=False)
    except Exception:
        pass

    return StudentResponse.model_validate(student)


@router.post("/{subject_id}/roster/fix-from-sheet")
def fix_roster_from_sheet(
    subject_id: str,
    db: Session = Depends(get_db),
):
    """Re-read roster crop from stored images / cache, fix names, recompute serials and batches."""
    from scripts.repair_roster import repair_subject_roster
    success = repair_subject_roster(subject_id=subject_id, sample_30_only=True)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to repair roster from sheet.")
    return {"status": "ok", "message": "Roster successfully repaired from sheet."}
