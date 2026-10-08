"""
backend/excel/cumulative_merger.py — Core Cumulative Attendance Excel Append Engine
"""
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.config import settings
from backend.schemas import AttendanceStatus

# ── Color Palette & Styles ───────────────────────────────────
FONT_TITLE = Font(name="Calibri", size=13, bold=True, color="1F4E79")
FONT_SUBTITLE = Font(name="Calibri", size=10, bold=True, color="595959")
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FONT_REGULAR = Font(name="Calibri", size=10, bold=False, color="000000")
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color="000000")
FONT_LOW_ATT = Font(name="Calibri", size=10, bold=True, color="9C0006")

FILL_HEADER = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
FILL_SUMMARY = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
FILL_PRESENT = PatternFill(start_color="D1E7DD", end_color="D1E7DD", fill_type="solid")  # soft green
FILL_ABSENT = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")   # soft red
FILL_NM = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")       # light grey
FILL_LOW_ATT = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")

THIN = Side(style="thin", color="D9D9D9")
BORDER_CELL = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


@dataclass
class StudentRosterRecord:
    sr_no: int
    roll_no: str
    name: str
    batch: int = 1


@dataclass
class DateMarkItem:
    roll_no: str
    date: str  # ISO string YYYY-MM-DD
    status: str  # P, A, NM, NA


@dataclass
class MergeResult:
    subject_id: str
    added_dates: List[str]
    updated_students_count: int
    conflicts: List[Dict[str, Any]]
    class_average_pct: float
    excel_path: Path


class CumulativeMerger:
    """
    Manages cumulative append of attendance dates into a single master Excel file.
    Preserves all historical sessions, maintains student ordering, and rewrites formulas.
    """

    def __init__(self, subject_id: str):
        self.subject_id = subject_id
        self.subject_dir = settings.SUBJECTS_DIR / subject_id
        self.subject_dir.mkdir(parents=True, exist_ok=True)
        self.master_path = self.subject_dir / "master_attendance.xlsx"
        self.backup_path = self.subject_dir / "master_attendance.bak.xlsx"

    def _format_date_display(self, iso_date: str) -> str:
        """Convert ISO YYYY-MM-DD to sheet display format d/m/yy (e.g. 9/9/26)."""
        try:
            dt = datetime.strptime(iso_date, "%Y-%m-%d")
            return f"{dt.day}/{dt.month}/{str(dt.year)[-2:]}"
        except Exception:
            return iso_date

    def _parse_display_date(self, display_date: str) -> Optional[str]:
        """Convert sheet display format d/m/yy back to ISO YYYY-MM-DD."""
        try:
            # Handle d/m/yy or d/m/yyyy
            parts = str(display_date).strip().split("/")
            if len(parts) == 3:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            pass
        return None

    def merge(
        self,
        roster: List[StudentRosterRecord],
        new_dates: List[str],  # ISO strings
        records: List[DateMarkItem],
        subject_metadata: Optional[Dict[str, str]] = None,
        overwrite_conflicts: bool = False,
    ) -> MergeResult:
        """
        Merge new session dates and student marks into the master spreadsheet.
        """
        # Ensure backup of existing master
        if self.master_path.exists():
            shutil.copy2(self.master_path, self.backup_path)

        # 1. Read existing state if master exists
        existing_dates_iso: List[str] = []
        existing_grid: Dict[str, Dict[str, str]] = {}  # roll_no -> {iso_date: status}

        if self.master_path.exists():
            wb_read = openpyxl.load_workbook(self.master_path, data_only=True)
            ws_read = wb_read.active
            existing_dates_iso, existing_grid = self._read_existing_data(ws_read)
            wb_read.close()

        # 2. Reconcile dates (chronological ordering + deduplication)
        all_dates_set = set(existing_dates_iso)
        newly_added_dates = []
        conflicts = []

        # Map incoming records by (roll_no, iso_date)
        incoming_map: Dict[Tuple[str, str], str] = {
            (r.roll_no, r.date): r.status for r in records
        }

        for d in new_dates:
            if d not in all_dates_set:
                all_dates_set.add(d)
                newly_added_dates.append(d)
            else:
                # Existing date: check for cell conflicts
                for roll in existing_grid:
                    old_val = existing_grid[roll].get(d, "NM")
                    new_val = incoming_map.get((roll, d), old_val)
                    if old_val != new_val and old_val not in ("NM", ""):
                        conflicts.append({
                            "roll_no": roll,
                            "date": d,
                            "existing": old_val,
                            "incoming": new_val,
                        })

        # Final ordered date list (chronological)
        all_dates_sorted = sorted(list(all_dates_set))

        # 3. Build updated student matrix
        combined_grid: Dict[str, Dict[str, str]] = {}
        for s in roster:
            combined_grid[s.roll_no] = {}
            for d in all_dates_sorted:
                old_val = existing_grid.get(s.roll_no, {}).get(d, "NM")
                new_val = incoming_map.get((s.roll_no, d))

                if new_val is not None:
                    if d in newly_added_dates or old_val in ("NM", "") or overwrite_conflicts:
                        combined_grid[s.roll_no][d] = new_val
                    else:
                        combined_grid[s.roll_no][d] = old_val
                else:
                    combined_grid[s.roll_no][d] = old_val

        # 4. Generate master workbook atomically
        wb = openpyxl.Workbook()
        wb.calculation.fullCalcOnLoad = True
        ws = wb.active
        ws.title = "Attendance Register"

        self._build_sheet(
            ws=ws,
            subject_meta=subject_metadata or {},
            roster=roster,
            dates_iso=all_dates_sorted,
            grid=combined_grid,
        )

        # Atomic file write
        temp_fd, temp_file_path = tempfile.mkstemp(suffix=".xlsx", dir=str(self.subject_dir))
        os.close(temp_fd)
        wb.save(temp_file_path)
        wb.close()

        # Optional LibreOffice headless calculation if available
        soffice_path = shutil.which("soffice")
        if soffice_path:
            try:
                import subprocess
                subprocess.run(
                    [soffice_path, "--headless", "--convert-to", "pdf", temp_file_path],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        # Validate that written workbook can be cleanly opened
        wb_check = openpyxl.load_workbook(temp_file_path)
        wb_check.close()

        # Safely move temp file to master_path
        shutil.move(temp_file_path, self.master_path)

        # Calculate class average attendance %
        total_p = 0
        total_held = 0
        for roll, marks in combined_grid.items():
            for d, st in marks.items():
                if st == "P":
                    total_p += 1
                    total_held += 1
                elif st == "A":
                    total_held += 1

        avg_pct = round((total_p / total_held * 100), 1) if total_held > 0 else 0.0

        return MergeResult(
            subject_id=self.subject_id,
            added_dates=newly_added_dates,
            updated_students_count=len(roster),
            conflicts=conflicts,
            class_average_pct=avg_pct,
            excel_path=self.master_path,
        )

    def _read_existing_data(self, ws) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
        """Extract existing date headers and student marks from openpyxl worksheet."""
        header_row = 4  # row 4 is standard header row
        dates_iso = []
        date_col_map: Dict[int, str] = {}  # col_idx -> iso_date

        for col in range(5, ws.max_column + 1):
            cell_val = ws.cell(row=header_row, column=col).value
            if cell_val in ("TOTAL", "HELD", "ATT %", None):
                break
            iso_d = self._parse_display_date(str(cell_val))
            if iso_d:
                dates_iso.append(iso_d)
                date_col_map[col] = iso_d

        grid: Dict[str, Dict[str, str]] = {}
        for r in range(5, ws.max_row + 1):
            roll_val = ws.cell(row=r, column=2).value
            if not roll_val or str(roll_val).startswith("Batch"):
                continue
            roll_str = str(roll_val).strip()
            grid[roll_str] = {}
            for col, d in date_col_map.items():
                mark = ws.cell(row=r, column=col).value
                grid[roll_str][d] = str(mark).strip() if mark else "NM"

        return dates_iso, grid

    def _build_sheet(
        self,
        ws,
        subject_meta: Dict[str, str],
        roster: List[StudentRosterRecord],
        dates_iso: List[str],
        grid: Dict[str, Dict[str, str]],
    ):
        """Construct the complete VIT-style styled spreadsheet."""
        static_headers = ["Sr.No", "Roll No", "Name of the Student", "Batch"]
        summary_headers = ["TOTAL", "HELD", "ATT %"]
        total_cols = len(static_headers) + len(dates_iso) + len(summary_headers)
        last_col_letter = get_column_letter(max(total_cols, 7))

        # Row 1: College Header
        ws.merge_cells(f"A1:{last_col_letter}1")
        c1 = ws["A1"]
        c1.value = "Vidyalankar Institute of Technology — Attendance Register"
        c1.font = FONT_TITLE
        c1.alignment = ALIGN_CENTER

        # Row 2: Subject Metadata Subtitle
        ws.merge_cells(f"A2:{last_col_letter}2")
        c2 = ws["A2"]
        sub_code = subject_meta.get("code", "SS")
        sub_name = subject_meta.get("name", "System Software")
        cls_name = subject_meta.get("class_name", "Semester 5")
        branch_name = subject_meta.get("branch", "Electronics & Computer Science")
        div_name = subject_meta.get("division", "B")
        fac_name = subject_meta.get("faculty", "SHP")
        acad_yr = subject_meta.get("academic_year", "2026-27 (Odd)")

        c2.value = f"Branch: {branch_name} | Class: {cls_name} | Div: {div_name} | Subject: {sub_code} ({sub_name}) | Faculty: {fac_name} | Academic Year: {acad_yr}"
        c2.font = FONT_SUBTITLE
        c2.alignment = ALIGN_CENTER

        # Row heights
        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 20
        ws.row_dimensions[3].height = 10
        ws.row_dimensions[4].height = 26
        # Row 4: Column Headers
        for idx, h in enumerate(static_headers, start=1):
            cell = ws.cell(row=4, column=idx, value=h)
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_CELL

        current_col = 5
        for d in dates_iso:
            cell = ws.cell(row=4, column=current_col, value=self._format_date_display(d))
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_CELL
            current_col += 1

        summary_headers = ["TOTAL", "HELD", "ATT %"]
        summary_start_col = current_col
        for sh in summary_headers:
            cell = ws.cell(row=4, column=current_col, value=sh)
            cell.font = FONT_HEADER
            cell.fill = FILL_HEADER
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_CELL
            current_col += 1

        # Populate Student Rows
        current_row = 5
        date_start_col_letter = "E"
        date_end_col_letter = get_column_letter(len(dates_iso) + 4) if dates_iso else "E"

        for student in roster:
            ws.row_dimensions[current_row].height = 20
            ws.cell(row=current_row, column=1, value=student.sr_no).alignment = ALIGN_CENTER
            ws.cell(row=current_row, column=2, value=student.roll_no).alignment = ALIGN_CENTER
            ws.cell(row=current_row, column=3, value=student.name).alignment = ALIGN_LEFT
            ws.cell(row=current_row, column=4, value=f"Batch {student.batch}").alignment = ALIGN_CENTER

            # Format metadata cells
            for c in range(1, 5):
                cell = ws.cell(row=current_row, column=c)
                cell.font = FONT_REGULAR
                cell.border = BORDER_CELL

            # Attendance Marks
            col_ptr = 5
            for d in dates_iso:
                status_val = grid.get(student.roll_no, {}).get(d, "NM")
                cell = ws.cell(row=current_row, column=col_ptr)
                cell.value = status_val
                cell.alignment = ALIGN_CENTER
                cell.border = BORDER_CELL

                if status_val == "P":
                    cell.fill = FILL_PRESENT
                    cell.font = FONT_BOLD
                elif status_val == "A":
                    cell.fill = FILL_ABSENT
                    cell.font = FONT_BOLD
                elif status_val == "NM":
                    cell.fill = FILL_NM
                    cell.font = FONT_REGULAR

                col_ptr += 1

            # Formulas: TOTAL, HELD, ATT %
            if dates_iso:
                total_formula = f'=COUNTIF({date_start_col_letter}{current_row}:{date_end_col_letter}{current_row},"P")'
                held_formula = f'=COUNTIF({date_start_col_letter}{current_row}:{date_end_col_letter}{current_row},"P")+COUNTIF({date_start_col_letter}{current_row}:{date_end_col_letter}{current_row},"A")'
                held_col_letter = get_column_letter(summary_start_col + 1)
                total_col_letter = get_column_letter(summary_start_col)
                pct_formula = f'=IF({held_col_letter}{current_row}=0,"",{total_col_letter}{current_row}/{held_col_letter}{current_row}*100)'
            else:
                total_formula = 0
                held_formula = 0
                pct_formula = ""

            cell_tot = ws.cell(row=current_row, column=summary_start_col, value=total_formula)
            cell_tot.font = FONT_BOLD
            cell_tot.alignment = ALIGN_CENTER
            cell_tot.fill = FILL_SUMMARY
            cell_tot.border = BORDER_CELL

            cell_held = ws.cell(row=current_row, column=summary_start_col + 1, value=held_formula)
            cell_held.font = FONT_BOLD
            cell_held.alignment = ALIGN_CENTER
            cell_held.fill = FILL_SUMMARY
            cell_held.border = BORDER_CELL

            cell_pct = ws.cell(row=current_row, column=summary_start_col + 2, value=pct_formula)
            cell_pct.font = FONT_BOLD
            cell_pct.alignment = ALIGN_CENTER
            cell_pct.fill = FILL_SUMMARY
            cell_pct.border = BORDER_CELL
            cell_pct.number_format = "0.0"

            current_row += 1

        # Conditional Formatting: Highlight ATT % < 75% in bold red
        pct_col_letter = get_column_letter(summary_start_col + 2)
        rule_low = CellIsRule(
            operator="lessThan",
            formula=["75"],
            stopIfTrue=True,
            font=FONT_LOW_ATT,
            fill=FILL_LOW_ATT,
        )
        ws.conditional_formatting.add(f"{pct_col_letter}5:{pct_col_letter}{current_row-1}", rule_low)

        # Freeze Panes on Column E (so student details remain visible when scrolling right)
        ws.freeze_panes = "E5"

        # Explicit, balanced column widths (prevents merged title in A1/A2 from inflating Column A)
        ws.column_dimensions["A"].width = 7.5    # Sr.No
        ws.column_dimensions["B"].width = 15.0   # Roll No
        ws.column_dimensions["C"].width = 28.0   # Name of the Student
        ws.column_dimensions["D"].width = 11.0   # Batch

        # Date columns
        for c_idx in range(5, 5 + len(dates_iso)):
            ws.column_dimensions[get_column_letter(c_idx)].width = 10.0

        # Summary columns (TOTAL, HELD, ATT %)
        ws.column_dimensions[get_column_letter(summary_start_col)].width = 10.0
        ws.column_dimensions[get_column_letter(summary_start_col + 1)].width = 10.0
        ws.column_dimensions[get_column_letter(summary_start_col + 2)].width = 11.0
