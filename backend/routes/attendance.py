"""
backend/routes/attendance.py — Attendance Scan, Review Commit, and Master Excel Download Endpoints
"""
import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db, Subject, Student, Scan, Session as DbSession, AttendanceRecord
from backend.schemas import (
    ScanPreviewResponse,
    CommitRequest,
    CommitResponse,
    AttendanceStatus,
    RowExtraction,
    DateColumn,
)
from backend.vision.extractor import get_extractor
from backend.vision.roster_aligner import RosterAligner, ScannedStudentRow, RosterStudent
from backend.excel.cumulative_merger import (
    CumulativeMerger,
    StudentRosterRecord,
    DateMarkItem,
)

logger = logging.getLogger("attendai.attendance_routes")
router = APIRouter(prefix="/api/subjects", tags=["Attendance"])

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


# ─────────────────────────────────────────────────────────────
# 1. SCAN & EXTRACT ENDPOINT (PREVIEW ONLY)
# ─────────────────────────────────────────────────────────────

from backend.vision.image_pipeline import ImagePipeline
from backend.vision.dates import AcademicDateParser
from backend.roster import RosterManager, normalize_roll_number, PageStudentBatch, RosterStudentItem
from backend.database import ScanSession, ScanPage
import hashlib


@router.post("/{subject_id}/scan", response_model=ScanPreviewResponse)
async def scan_attendance_sheet(
    subject_id: str,
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    mock: bool = Query(False, description="Use MockExtractor for offline test evaluation"),
    db: Session = Depends(get_db),
):
    """
    Upload 1 or more attendance register scan images (multi-page/continuation sheets),
    run quality checks, perspective correction, extraction & arrow resolution.
    Continuation pages inherit date slots from Page 1.
    """
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject '{subject_id}' not found.")

    # Consolidate upload inputs
    upload_list: List[UploadFile] = []
    if files:
        upload_list.extend(files)
    if file:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No attendance sheet photo uploaded.")

    import cv2
    import numpy as np

    subject_dir = settings.SUBJECTS_DIR / subject_id
    scans_dir = subject_dir / "scans"
    scans_dir.mkdir(parents=True, exist_ok=True)

    scan_session = ScanSession(subject_id=subject_id, status="preview")
    db.add(scan_session)
    db.commit()
    db.refresh(scan_session)

    processed_pages: List[Path] = []
    quality_notes_list: List[str] = []
    system_warnings: List[str] = []

    for idx, uf in enumerate(upload_list):
        suffix = Path(uf.filename or "sheet.jpg").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Page {idx+1}: Invalid file extension '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        contents = await uf.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail=f"Page {idx+1} is empty (0 bytes).")
        if len(contents) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Page {idx+1} exceeds 15 MB limit.",
            )

        decoded = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
        if decoded is None or decoded.size == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Page {idx+1}: File is corrupt or not a readable image.",
            )

        # Quality Check Gate
        q_res = ImagePipeline.check_quality(decoded)
        if not q_res.passed:
            raise HTTPException(
                status_code=400,
                detail=f"Page {idx+1}: {q_res.guidance or q_res.message}",
            )
        if q_res.guidance:
            quality_notes_list.append(f"Page {idx+1}: {q_res.guidance}")

        # Optional perspective rectification
        rectified = ImagePipeline.rectify_perspective(decoded)
        safe_name = f"{uuid.uuid4().hex[:8]}_{Path(uf.filename or f'page_{idx+1}.jpg').name}"
        save_path = scans_dir / safe_name
        cv2.imwrite(str(save_path), rectified)

        img_hash = hashlib.sha256(contents).hexdigest()
        scan_page = ScanPage(
            session_id=scan_session.id,
            image_path=str(save_path),
            image_hash=img_hash,
            page_index=idx + 1,
            quality_score=q_res.blur_score,
            engine_used="attendai_vision",
        )
        db.add(scan_page)
        processed_pages.append(save_path)

    db.commit()

    # Legacy Scan record for backward compatibility
    scan_record = Scan(
        subject_id=subject_id,
        image_path=str(processed_pages[0]),
        status="preview",
    )
    db.add(scan_record)
    db.commit()
    db.refresh(scan_record)

    extractor = get_extractor(use_mock=mock)
    date_parser = AcademicDateParser(academic_year=subject.academic_year or "2026-27 (Odd)")

    # 1. Process Page 1
    p1_path = processed_pages[0]
    p1_preview: ScanPreviewResponse = extractor.extract(image_path=p1_path, subject_id=subject_id)

    # Normalize dates with AcademicDateParser
    normalized_dates: List[DateColumn] = []
    for d_col in p1_preview.date_columns:
        if "Date missing" in d_col.raw_date or d_col.needs_confirmation:
            system_warnings.append(f"{d_col.raw_date}: pre-filled suggestion {d_col.iso_date} (suggested, please confirm).")
            normalized_dates.append(d_col)
            continue

        parsed_dt = date_parser.parse(d_col.raw_date, fallback_iso=d_col.iso_date)
        if parsed_dt.warning:
            system_warnings.append(f"Date '{d_col.raw_date}': {parsed_dt.warning}")
        normalized_dates.append(
            DateColumn(
                col_idx=d_col.col_idx,
                raw_date=parsed_dt.raw,
                iso_date=parsed_dt.iso,
                confidence=d_col.confidence,
                needs_confirmation=d_col.needs_confirmation,
                suggested_date=d_col.suggested_date,
            )
        )
    p1_preview.date_columns = normalized_dates

    combined_rows: List[RowExtraction] = list(p1_preview.rows)

    # 2. Process Continuation Pages (if any)
    if len(processed_pages) > 1:
        for p_idx, cont_path in enumerate(processed_pages[1:], start=2):
            cont_preview: ScanPreviewResponse = extractor.extract(image_path=cont_path, subject_id=subject_id)

            # Inherit dates from Page 1 by slot index
            for r in cont_preview.rows:
                # Ensure each cell's col_idx matches Page 1 date column count
                adjusted_cells = []
                for c in r.cells:
                    if c.col_idx < len(p1_preview.date_columns):
                        adjusted_cells.append(c)
                r.cells = adjusted_cells

            combined_rows.extend(cont_preview.rows)

        # Check page order & duplicates
        batches: List[PageStudentBatch] = []
        p1_items = [
            RosterStudentItem(roll_no=r.roll_no, name=r.name, batch=r.batch, sr_no=r.sr_no)
            for r in p1_preview.rows
        ]
        first_r1 = p1_items[0].roll_no if p1_items else None
        last_r1 = p1_items[-1].roll_no if p1_items else None
        batches.append(PageStudentBatch(page_index=1, students=p1_items, first_roll=first_r1, last_roll=last_r1))

        # Add continuation batches
        cur_offset = len(p1_preview.rows)
        for p_num, cont_path in enumerate(processed_pages[1:], start=2):
            # rows for this continuation page
            cont_slice = combined_rows[cur_offset:]
            cont_items = [
                RosterStudentItem(roll_no=r.roll_no, name=r.name, batch=r.batch, sr_no=r.sr_no)
                for r in cont_slice
            ]
            first_rc = cont_items[0].roll_no if cont_items else None
            last_rc = cont_items[-1].roll_no if cont_items else None
            batches.append(PageStudentBatch(page_index=p_num, students=cont_items, first_roll=first_rc, last_roll=last_rc))
            cur_offset += len(cont_slice)

        order_warnings = RosterManager.check_page_order_and_duplicates(batches)
        for w in order_warnings:
            system_warnings.append(f"Multi-page issue: {w.message}")

    p1_preview.rows = combined_rows
    p1_preview.scan_id = scan_record.id


    # 3. Align with subject roster if subject already has students
    if subject.students and p1_preview.rows:
        try:
            aligner = RosterAligner()
            roster_data = [
                RosterStudent(sr_no=s.sr_no, roll_no=s.roll_no, name=s.name, batch=s.batch)
                for s in subject.students
            ]
            scanned_rows = [
                ScannedStudentRow(
                    sr_no=r.sr_no,
                    raw_roll_no=r.roll_no,
                    raw_name=r.name,
                    batch=r.batch,
                )
                for r in p1_preview.rows
            ]
            aligned_rows = aligner.align(scanned_rows, roster_data)

            reconciled_rows = []
            for idx, a in enumerate(aligned_rows):
                orig_row = p1_preview.rows[idx] if idx < len(p1_preview.rows) else None
                orig_cells = orig_row.cells if orig_row else []
                matched = a.matched_student
                if matched:
                    # Never overwrite real extracted name with a missing/roll-number name from DB
                    final_name = matched.name
                    if (not final_name or final_name.upper() == matched.roll_no.upper()) and orig_row and orig_row.name:
                        final_name = orig_row.name
                    final_batch = orig_row.batch if orig_row and orig_row.batch else matched.batch
                    final_sr = matched.sr_no or (orig_row.sr_no if orig_row else idx + 1)
                    reconciled_rows.append(
                        RowExtraction(
                            sr_no=final_sr,
                            roll_no=matched.roll_no,
                            name=final_name,
                            batch=final_batch,
                            cells=orig_cells,
                        )
                    )
                elif orig_row:
                    reconciled_rows.append(orig_row)

            if reconciled_rows:
                p1_preview.rows = reconciled_rows
        except Exception as align_err:
            logger.warning("Roster alignment failed (preserving raw extraction): %s", align_err, exc_info=True)

    # Rule: Sr No is regenerated strictly from the roster: sort by (batch, paper order, roll_no) -> 1..N
    p1_preview.rows.sort(key=lambda r: (r.batch, r.sr_no or 0, r.roll_no))
    for idx, r in enumerate(p1_preview.rows, start=1):
        r.sr_no = idx

    # Check for any uncertain cells
    has_unc = any(
        any(c.status == AttendanceStatus.UNCERTAIN for c in r.cells)
        for r in p1_preview.rows
    )
    p1_preview.has_uncertain = has_unc
    p1_preview.warnings = system_warnings
    p1_preview.quality_notes = "; ".join(quality_notes_list) if quality_notes_list else None

    # Store raw result in scan record
    scan_record.week_no = p1_preview.header.week_no
    scan_record.raw_result_json = p1_preview.model_dump_json()
    db.commit()

    return p1_preview



# ─────────────────────────────────────────────────────────────
# 2. COMMIT ENDPOINT (APPENDS TO MASTER EXCEL & PERSISTS TO DB)
# ─────────────────────────────────────────────────────────────

@router.post("/{subject_id}/commit", response_model=CommitResponse)
def commit_attendance_grid(
    subject_id: str,
    commit_data: CommitRequest,
    db: Session = Depends(get_db),
):
    """
    Accept teacher-verified attendance grid, persist records to SQLite database,
    and append date columns into the cumulative master_attendance.xlsx spreadsheet.
    BLOCKS commit if any cell status is UNCERTAIN.
    """
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    # 1. Blocking rule: verify zero UNCERTAIN cells
    uncertain_items = [r for r in commit_data.records if r.status == AttendanceStatus.UNCERTAIN]
    if uncertain_items:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot commit while {len(uncertain_items)} cell(s) have UNCERTAIN status. "
                "Please review and resolve all uncertain cells to P, A, NM, or NA."
            ),
        )

    # 1b. Blocking rule: verify every active slot has an explicit, confirmed date
    import re
    for d_iso in commit_data.date_columns:
        if not d_iso or "missing" in str(d_iso).lower() or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d_iso).strip()):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot commit: Active column date '{d_iso}' is missing or invalid. "
                    "Every active column must be assigned a confirmed date before appending to Master Excel."
                ),
            )


    # 2. Persist Sessions & Attendance Records in DB
    student_map = {s.roll_no: s for s in subject.students}

    # If students info provided in commit_data, update or insert them
    if commit_data.students:
        for st_in in commit_data.students:
            clean_roll = st_in.roll_no.strip().upper()
            clean_name = st_in.name.strip().upper() if st_in.name else ""
            if clean_name == clean_roll:
                clean_name = ""  # Rule: Never use roll number as name
            existing_st = student_map.get(clean_roll)
            if existing_st:
                if clean_name and (not existing_st.name or existing_st.name == existing_st.roll_no):
                    existing_st.name = clean_name
                if st_in.batch:
                    existing_st.batch = st_in.batch
            else:
                new_st = Student(
                    subject_id=subject.id,
                    sr_no=st_in.sr_no or (len(subject.students) + 1),
                    roll_no=clean_roll,
                    name=clean_name,
                    batch=st_in.batch,
                )
                db.add(new_st)
        db.commit()
        db.refresh(subject)
        student_map = {s.roll_no: s for s in subject.students}

    # If subject still has students with missing names or roll-no-as-name, check Scan raw_result_json
    if not student_map or any(s.name == s.roll_no or not s.name for s in subject.students):
        if commit_data.scan_id:
            scan_row = db.query(Scan).filter(Scan.id == commit_data.scan_id).first()
            if scan_row and scan_row.raw_result_json:
                try:
                    raw_data = json.loads(scan_row.raw_result_json)
                    for r_item in raw_data.get("rows", []):
                        r_roll = str(r_item.get("roll_no", "")).strip().upper()
                        r_name = str(r_item.get("name", "")).strip().upper()
                        r_batch = int(r_item.get("batch", 1) or 1)
                        if r_name == r_roll:
                            r_name = ""
                        st_rec = student_map.get(r_roll)
                        if st_rec:
                            if r_name and (not st_rec.name or st_rec.name == st_rec.roll_no):
                                st_rec.name = r_name
                            if r_batch:
                                st_rec.batch = r_batch
                        else:
                            st_rec = Student(
                                subject_id=subject.id,
                                sr_no=r_item.get("sr_no", len(subject.students) + 1),
                                roll_no=r_roll,
                                name=r_name,
                                batch=r_batch,
                            )
                            db.add(st_rec)
                    db.commit()
                    db.refresh(subject)
                    student_map = {s.roll_no: s for s in subject.students}
                except Exception as e:
                    logger.warning("Failed to parse raw_result_json during commit: %s", e)

    # Strictly regenerate serial numbers 1..N from final roster
    all_students = list(subject.students)
    all_students.sort(key=lambda s: (s.batch, s.sr_no or 0, s.roll_no))
    for idx, st in enumerate(all_students, start=1):
        st.sr_no = idx
    db.commit()
    db.refresh(subject)
    student_map = {s.roll_no: s for s in subject.students}

    # For each date column, create/find Session
    session_map = {}
    for d_iso in commit_data.date_columns:
        sess = db.query(DbSession).filter(DbSession.subject_id == subject.id, DbSession.date == d_iso).first()
        if not sess:
            sess = DbSession(
                subject_id=subject.id,
                date=d_iso,
                scan_id=commit_data.scan_id,
            )
            db.add(sess)
            db.commit()
            db.refresh(sess)
        session_map[d_iso] = sess

    # Upsert attendance records
    for rec in commit_data.records:
        student = student_map.get(rec.roll_no)
        sess = session_map.get(rec.date)
        if not student or not sess:
            continue

        existing_rec = db.query(AttendanceRecord).filter(
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.session_id == sess.id,
        ).first()

        if existing_rec:
            if commit_data.overwrite_conflicts or existing_rec.status in ("NM", ""):
                existing_rec.status = rec.status.value
                existing_rec.source = "teacher"
        else:
            new_record = AttendanceRecord(
                student_id=student.id,
                session_id=sess.id,
                status=rec.status.value,
                source="teacher",
            )
            db.add(new_record)

    # Mark scan and scan_session committed
    if commit_data.scan_id:
        scan_row = db.query(Scan).filter(Scan.id == commit_data.scan_id).first()
        if scan_row:
            scan_row.status = "committed"
        db.query(ScanSession).filter(ScanSession.subject_id == subject.id, ScanSession.status == "preview").update({"status": "committed"})

    db.commit()

    # 3. Append to Cumulative Master Excel
    merger = CumulativeMerger(subject_id=subject.id)
    roster_list = [
        StudentRosterRecord(
            sr_no=s.sr_no,
            roll_no=s.roll_no,
            name=s.name,
            batch=s.batch,
        )
        for s in subject.students
    ]
    date_marks = [
        DateMarkItem(
            roll_no=r.roll_no,
            date=r.date,
            status=r.status.value,
        )
        for r in commit_data.records
    ]

    meta = {
        "name": subject.name,
        "code": subject.code,
        "class_name": subject.class_name,
        "branch": getattr(subject, "branch", None) or "Electronics & Computer Science",
        "division": subject.division,
        "faculty": subject.faculty,
        "academic_year": subject.academic_year,
    }

    merge_res = merger.merge(
        roster=roster_list,
        new_dates=commit_data.date_columns,
        records=date_marks,
        subject_metadata=meta,
        overwrite_conflicts=commit_data.overwrite_conflicts,
    )

    return CommitResponse(
        subject_id=subject.id,
        added_dates=merge_res.added_dates,
        updated_students_count=merge_res.updated_students_count,
        conflicts_detected=merge_res.conflicts,
        class_average_pct=merge_res.class_average_pct,
        master_download_url=f"/api/subjects/{subject.id}/download",
    )


# ─────────────────────────────────────────────────────────────
# 3. DOWNLOAD MASTER EXCEL ENDPOINT
# ─────────────────────────────────────────────────────────────

@router.get("/{subject_id}/download")
def download_master_attendance_excel(
    subject_id: str,
    db: Session = Depends(get_db),
):
    """Download the single cumulative master_attendance.xlsx for the subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.deleted_at.is_(None)).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    excel_path = settings.SUBJECTS_DIR / subject_id / "master_attendance.xlsx"
    if not excel_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Master attendance spreadsheet has not been generated yet. Please scan and commit a sheet first.",
        )

    safe_filename = f"{subject.code}_{subject.division}_master_attendance.xlsx"
    return FileResponse(
        path=str(excel_path),
        filename=safe_filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
