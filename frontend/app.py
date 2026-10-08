"""
frontend/app.py — AttendAI Modern Academic Dashboard
Multi-view Streamlit UI: Subject Management, Live Sheet Scanner, Interactive Review Matrix, and Master Excel Export
"""
import io
import os
import re
import textwrap
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import altair as alt
import openpyxl
import pandas as pd
import requests
import streamlit as st
from PIL import Image

# ─────────────────────────────────────────────────────────────
# 1. APP CONFIGURATION & THEMING (AttendAI Institutional Ledger)
# ─────────────────────────────────────────────────────────────
_FAVICON_PATH = Path(__file__).resolve().parent / "assets" / "brand" / "favicon-32.png"
_fav_icon = Image.open(_FAVICON_PATH) if _FAVICON_PATH.exists() else "📋"

st.set_page_config(
    page_title="AttendAI · Smart attendance",
    page_icon=_fav_icon,
    layout="wide",
    initial_sidebar_state="collapsed",
)

API_BASE = os.environ.get("ATTENDAI_API_BASE", "http://127.0.0.1:8000")

# Status badges and reverse mappings for Streamlit data_editor
STATUS_MAP = {"P": "P", "A": "A", "NM": "NM", "NA": "NA", "UNCERTAIN": "?"}
REV_STATUS_MAP = {
    "P": "P", "A": "A", "NM": "NM", "NA": "NA", "?": "UNCERTAIN",
    "🟢 P": "P", "🔴 A": "A", "⚪ NM": "NM", "➖ NA": "NA", "🟡 ?": "UNCERTAIN"
}
STATUS_CHOICES = ["P", "A", "NM", "NA", "?"]

def clean_attendance_token(val: Any) -> str:
    s = str(val or "").strip().upper()
    if "?" in s or "UNCERTAIN" in s:
        return "?"
    elif "P" in s:
        return "P"
    elif "A" in s and "NA" not in s:
        return "A"
    elif "NA" in s:
        return "NA"
    return "NM"

BRANCH_OPTIONS = [
    "Computer Engineering",
    "Information Technology",
    "Electronics & Telecommunication",
    "Electronics & Computer Science",
    "Biomedical Engineering",
]

BRANCH_CODES = {
    "Computer Engineering": "CMPN",
    "Information Technology": "INFT",
    "Electronics & Telecommunication": "EXTC",
    "Electronics & Computer Science": "EXCS",
    "Biomedical Engineering": "BIOM",
}

# ─────────────────────────────────────────────────────────────
# 1.1 MASTER THEME & COMPONENTS INJECTION
# ─────────────────────────────────────────────────────────────
import importlib
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui.components
importlib.reload(ui.components)

from ui.components import (
    render_html,
    inject_global_styles,
    render_top_bar,
    render_ruled_header,
    render_stat_strip,
    render_subject_card_html,
    render_stepper,
    render_empty_state_html,
    format_date_chip,
    render_summary_strip,
    render_review_grid_html,
    render_students_table_html,
    ICONS,
)

# Inject self-hosted Bricolage Grotesque + IBM Plex Sans, CSS variables, and ledger styling
inject_global_styles()

# Inject high-res SVG favicon into document head
st.markdown("""
<script>
(function() {
    var link = document.querySelector("link[rel*='icon']");
    if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        document.getElementsByTagName('head')[0].appendChild(link);
    }
    link.type = 'image/svg+xml';
    link.href = '/app/static/favicon.svg';
})();
</script>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# 2. STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────
def init_state():
    if st.query_params.get("view") == "home":
        st.session_state.current_subject_id = None
        st.session_state.scan_preview = None
        st.session_state.review_df = None
        try:
            st.query_params.clear()
        except Exception:
            pass
    if st.query_params.get("subject_id"):
        st.session_state.current_subject_id = st.query_params.get("subject_id")
    elif "current_subject_id" not in st.session_state:
        st.session_state.current_subject_id = None
    if "scan_preview" not in st.session_state:
        st.session_state.scan_preview = None
    if "review_df" not in st.session_state:
        st.session_state.review_df = None
    if "scan_image_path" not in st.session_state:
        st.session_state.scan_image_path = None
    if "reasons_map" not in st.session_state:
        st.session_state.reasons_map = {}
    if "last_uploaded_bytes" not in st.session_state:
        st.session_state.last_uploaded_bytes = None

init_state()


# ─────────────────────────────────────────────────────────────
# 3. API CLIENT HELPERS
# ─────────────────────────────────────────────────────────────
def api_get(endpoint: str) -> Optional[Any]:
    try:
        res = requests.get(f"{API_BASE}{endpoint}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as exc:
        if endpoint != "/api/health":
            st.error(f"API Error ({endpoint}): {exc}")
        return None

def api_post(endpoint: str, json_data: dict = None, files: dict = None, timeout: int = 120) -> Optional[Any]:
    try:
        res = requests.post(f"{API_BASE}{endpoint}", json=json_data, files=files, timeout=timeout)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as exc:
        try:
            err = res.json().get("detail", str(exc))
        except Exception:
            err = str(exc)
        st.error(f"Failed: {err}")
        return None
    except Exception as exc:
        st.error(f"Network error: {exc}")
        return None

def api_patch(endpoint: str, json_data: dict = None, timeout: int = 15) -> Optional[Any]:
    try:
        res = requests.patch(f"{API_BASE}{endpoint}", json=json_data, timeout=timeout)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as exc:
        try:
            err = res.json().get("detail", str(exc))
        except Exception:
            err = str(exc)
        st.error(f"Failed: {err}")
        return None
    except Exception as exc:
        st.error(f"Network error: {exc}")
        return None

def api_delete(endpoint: str) -> bool:
    try:
        res = requests.delete(f"{API_BASE}{endpoint}", timeout=10)
        res.raise_for_status()
        return True
    except Exception as exc:
        st.error(f"Delete error: {exc}")
        return False

def get_subject_excel_bytes(subject_id: str) -> Optional[bytes]:
    """Retrieve master excel bytes directly from storage or internal backend."""
    p = Path(f"data/subjects/{subject_id}/master_attendance.xlsx")
    if p.exists():
        try:
            return p.read_bytes()
        except Exception:
            pass
    try:
        res = requests.get(f"{API_BASE}/api/subjects/{subject_id}/download", timeout=15)
        if res.status_code == 200:
            return res.content
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# 4. VIEW: HOME (SUBJECT DASHBOARD)
# ─────────────────────────────────────────────────────────────
@st.dialog("New subject")
def open_create_subject_dialog():
    render_html("""
    <div style="font-size:14px; color:var(--ink-2); margin-bottom:18px;">
        Set up a new course register. You can upload a student roster or read it automatically from the first scan.
    </div>
    """)
    c1, c2 = st.columns(2)
    with c1:
        name_in = st.text_input("Subject name", placeholder="e.g. Signal And System")
        code_in = st.text_input("Subject code", placeholder="e.g. SS")
        branch_in = st.selectbox(
            "Branch",
            BRANCH_OPTIONS,
            index=3,  # Electronics & Computer Science
            format_func=lambda b: f"{b} ({BRANCH_CODES.get(b, '')})" if b in BRANCH_CODES else b,
        )
        class_in = st.selectbox("Class", [f"Semester {i}" for i in range(1, 9)], index=4)
    with c2:
        type_in = st.segmented_control("Session type", ["Theory", "Practical"], default="Theory")
        fac_in = st.text_input("Faculty initials", placeholder="e.g. SHP")
        div_in = st.selectbox("Division", ["B", "A", "C", "D"])
        acad_in = st.text_input("Academic year", value="2026-27 (Odd)")

    st.markdown('<div style="margin: 16px 0 8px; font-weight: 600; font-size: 13px; color: var(--ink);">Roster setup</div>', unsafe_allow_html=True)
    roster_choice = st.segmented_control(
        "Roster option",
        ["Upload roster file", "Read from first scan"],
        default="Upload roster file",
        label_visibility="collapsed",
    )
    uploaded_file = None
    if roster_choice == "Upload roster file":
        uploaded_file = st.file_uploader("Upload CSV or Excel roster", type=["csv", "xlsx"])

    st.markdown('<div style="height: 12px;"></div>', unsafe_allow_html=True)
    b_submit = st.button("Create subject register", type="primary", use_container_width=True)
    if b_submit:
        if not name_in or not code_in or not fac_in:
            st.error("Please fill in Subject name, Code, and Faculty.")
        else:
            payload = {
                "name": name_in.strip(),
                "code": code_in.strip().upper(),
                "branch": branch_in,
                "class_name": class_in,
                "division": div_in,
                "type": type_in or "Theory",
                "faculty": fac_in.strip().upper(),
                "academic_year": acad_in.strip() or "2026-27 (Odd)",
            }
            if roster_choice == "Upload roster file" and uploaded_file:
                try:
                    if uploaded_file.name.endswith(".csv"):
                        df_r = pd.read_csv(uploaded_file)
                    else:
                        df_r = pd.read_excel(uploaded_file)
                    payload["roster"] = []
                    for idx, r in df_r.iterrows():
                        payload["roster"].append({
                            "sr_no": int(r.get("Sr No", idx + 1)),
                            "roll_no": str(r.get("Roll No", "")),
                            "name": str(r.get("Name", "")),
                            "batch": int(re.search(r"\d+", str(r.get("Batch", 1))).group()) if re.search(r"\d+", str(r.get("Batch", 1))) else 1,
                        })
                except Exception as ex:
                    st.error(f"Error reading roster: {ex}")
                    return

            created = api_post("/api/subjects", json_data=payload)
            if created:
                st.toast(f"Subject '{created.get('name')}' created successfully!")
                time.sleep(0.4)
                st.rerun()


def render_home_view():
    # 1. Fetch Subjects
    subjects = api_get("/api/subjects") or []

    # 2. Ruled Page Header Band
    h_col1, h_col2 = st.columns([3, 1], vertical_alignment="center")
    with h_col1:
        render_ruled_header(
            "Your subjects",
            "Single cumulative register system for Vidyalankar Institute of Technology."
        )
    with h_col2:
        if st.button("+ New subject", type="primary", use_container_width=True):
            open_create_subject_dialog()

    # 3. Stat Strip (Numbers in Fraunces, separated by thin rules)
    total_subjects = len(subjects)
    total_students = sum(s.get("stats", {}).get("enrolled_students", 0) for s in subjects)
    total_sessions = sum(s.get("stats", {}).get("total_sessions", 0) for s in subjects)
    total_below_75 = sum(s.get("stats", {}).get("students_below_75", 0) for s in subjects)

    render_stat_strip([
        {"label": "Subjects", "value": total_subjects},
        {"label": "Sheets scanned", "value": total_sessions},
        {"label": "Students tracked", "value": total_students},
        {"label": "Below 75%", "value": total_below_75},
    ])

    if not subjects:
        render_html(render_empty_state_html(
            "No subjects yet",
            "Create a subject, then scan its attendance sheet."
        ))
        e_col1, e_col2, e_col3 = st.columns([1, 1, 1])
        with e_col2:
            if st.button("Create your first subject", type="primary", use_container_width=True):
                open_create_subject_dialog()
        return

    # 4. Search and Segmented Filter Bar
    s_col1, s_col2 = st.columns([2, 1])
    with s_col1:
        search_query = st.text_input("Search subjects", placeholder="Search by name, code, faculty...", label_visibility="collapsed")
    with s_col2:
        type_filter = st.segmented_control("Filter", ["All", "Theory", "Practical"], default="All", label_visibility="collapsed")

    filtered_subjects = [
        s for s in subjects
        if (type_filter == "All" or s.get("type", "").lower() == (type_filter or "").lower())
        and (
            not search_query or (
                search_query.lower() in s.get("name", "").lower()
                or search_query.lower() in s.get("code", "").lower()
                or search_query.lower() in s.get("faculty", "").lower()
                or search_query.lower() in s.get("class_name", "").lower()
                or search_query.lower() in (s.get("branch") or "").lower()
                or search_query.lower() in BRANCH_CODES.get(s.get("branch", ""), "").lower()
            )
        )
    ]

    if not filtered_subjects:
        st.info(f"No subjects matching '{search_query}'.")
        return

    # 5. Render Subject Cards Grid
    cols = st.columns(3)
    for idx, subj in enumerate(filtered_subjects):
        col = cols[idx % 3]
        subj_id = subj["id"]

        with col:
            with st.container(border=True, key=f"subject_{subj_id}"):
                # Content inside card
                render_html(render_subject_card_html(subj))

                # Buttons inside card, aligned along bottom
                b1, b2, b3 = st.columns([2, 1, 1])
                with b1:
                    if st.button("Open", key=f"open_{subj_id}", type="primary", use_container_width=True):
                        st.session_state.current_subject_id = subj_id
                        st.session_state.scan_preview = None
                        st.session_state.review_df = None
                        st.rerun()
                with b2:
                    excel_data = get_subject_excel_bytes(subj_id)
                    if excel_data:
                        st.download_button(
                            "Excel",
                            data=excel_data,
                            file_name=f"{subj.get('code', 'subject')}_master_attendance.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key=f"dl_excel_{subj_id}",
                        )
                    else:
                        st.button("Excel", disabled=True, help="No sheets scanned yet", use_container_width=True, key=f"dl_excel_{subj_id}")
                with b3:
                    with st.popover("...", help="More options"):
                        st.markdown(f"**Delete {subj.get('code')}?**")
                        st.caption("Permanent action. Removes all scans, sessions, and files.")
                        if st.button("Delete subject", key=f"confirm_del_{subj_id}", type="primary", use_container_width=True):
                            if api_delete(f"/api/subjects/{subj_id}?permanent=true"):
                                st.toast(f"Deleted {subj.get('code')}")
                                st.rerun()


# ─────────────────────────────────────────────────────────────
# 5. VIEW: SUBJECT WORKSPACE
# ─────────────────────────────────────────────────────────────
def render_workspace_view():
    subj_id = st.session_state.current_subject_id
    subject = api_get(f"/api/subjects/{subj_id}")

    if not subject:
        st.error("Subject not found or removed.")
        if st.button("Back to Subjects"):
            st.session_state.current_subject_id = None
            st.rerun()
        return

    branch_val = subject.get("branch")
    if branch_val:
        b_code = BRANCH_CODES.get(branch_val)
        branch_display = f"{branch_val} ({b_code})" if b_code else branch_val
        branch_str = f" · {branch_display}"
    else:
        branch_str = ""

    # Compact Header Block (max 100px tall, no large gap, institutional ledger style)
    render_html(f"""
    <div style="background:var(--sheet); border:1px solid var(--line); border-radius:var(--radius-panel); padding:16px 24px; margin:16px 0 20px 0;">
        <h2 class="section-title" style="margin:0 !important; line-height:1.2;">
            {subject.get('code')} — {subject.get('name')}
        </h2>
        <div class="helper-text" style="margin-top:4px;">
            {subject.get('class_name')}{branch_str} · Division {subject.get('division')} · Faculty: <strong style="color:var(--ink);">{subject.get('faculty')}</strong>
        </div>
    </div>
    """)

    # Workspace Tabs (Scan, Register, Students, History — no emoji, clean text)
    tab_scan, tab_register, tab_students, tab_history = st.tabs([
        "Scan",
        "Register",
        "Students",
        "History",
    ])

    # ── TAB 1: SCAN & REVIEW ─────────────────────────────────
    with tab_scan:
        has_preview = st.session_state.scan_preview is not None and st.session_state.review_df is not None

        # 4-Step Academic Progress Stepper via SVG components
        if not has_preview:
            current_step = 1
        else:
            missing_dates = any("Date missing" in str(d.get("raw_date", "")) or d.get("needs_confirmation") for d in (st.session_state.scan_preview.get("date_columns", [])))
            current_step = 2 if missing_dates else 3
        render_stepper(current_step=current_step)

        if not has_preview:
            c_left, c_right = st.columns([1, 1])

            with c_left:
                render_html("<h3 class='card-title' style='margin-bottom:4px;'>Upload register photos</h3>")
                st.caption("Upload 1 or more photos (Page 1 + back/continuation sheets).")
                uploaded_files = st.file_uploader(
                    "Upload photos",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )

                # Quick fixture loader buttons (DEV MODE ONLY)
                is_dev_mode = os.environ.get("DEV_MODE", "false").lower() in ("true", "1")
                load_single_demo = False
                load_multi_demo = False
                if is_dev_mode:
                    st.markdown("**Developer test fixtures:**")
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Div-B Page 1 (Sr 1-30)", use_container_width=True):
                            load_single_demo = True
                    with btn_col2:
                        if st.button("Div-B 2-Page Set (Sr 1-66)", use_container_width=True):
                            load_multi_demo = True

                file_payloads = []
                if uploaded_files:
                    for uf in uploaded_files:
                        file_payloads.append((uf.name, uf.getvalue(), uf.type or "image/jpeg"))
                elif load_single_demo:
                    p1 = Path("backend/tests/fixtures/images/01_ss_divb_sr1_30_arrows.jpg")
                    if p1.exists():
                        with open(p1, "rb") as f:
                            file_payloads.append(("01_ss_divb_sr1_30_arrows.jpg", f.read(), "image/jpeg"))
                elif load_multi_demo:
                    p1 = Path("backend/tests/fixtures/images/01_ss_divb_sr1_30_arrows.jpg")
                    p2 = Path("backend/tests/fixtures/images/09_sr31_66_multi_dates.png")
                    if p1.exists() and p2.exists():
                        with open(p1, "rb") as f1, open(p2, "rb") as f2:
                            file_payloads.append(("01_page1.jpg", f1.read(), "image/jpeg"))
                            file_payloads.append(("02_page2.png", f2.read(), "image/png"))

                if file_payloads:
                    st.info(f"Loaded {len(file_payloads)} sheet photo(s). Ready to scan.")
                    img_cols = st.columns(min(len(file_payloads), 3))
                    for i, (fname, b_data, _) in enumerate(file_payloads[:3]):
                        with img_cols[i]:
                            st.image(b_data, caption=f"Page {i+1}: {fname}", use_container_width=True)

            with c_right:
                if file_payloads:
                    if st.button("Read sheets", type="primary", use_container_width=True):
                        st.session_state.last_uploaded_bytes = file_payloads[0][1]
                        with st.spinner("AttendAI Vision is analyzing the sheets and extracting attendance..."):
                            multi_files = [("files", (fn, b, ct)) for fn, b, ct in file_payloads]
                            preview_data = api_post(f"/api/subjects/{subj_id}/scan?mock=false", files=multi_files)

                        if preview_data:
                            st.session_state.scan_preview = preview_data
                            date_cols = preview_data.get("date_columns", [])
                            rows = preview_data.get("rows", [])

                            df_rows = []
                            reasons = {}
                            for r in rows:
                                row_dict = {
                                    "Sr No": r["sr_no"],
                                    "Roll No": r["roll_no"],
                                    "Name": r["name"],
                                    "Batch": f"Batch {r['batch']}",
                                }
                                # Build stable slot-indexed cells (col_0, col_1, ...)
                                for c in r.get("cells", []):
                                    d_idx = c["col_idx"]
                                    if d_idx < len(date_cols):
                                        col_key = f"col_{d_idx}"
                                        # Strict token/status resolution: NEVER silently default to NM
                                        raw_st = c.get("status")
                                        if not raw_st:
                                            tok = str(c.get("token") or "").upper()
                                            if tok == "SIGN":
                                                raw_st = "P"
                                            elif tok == "AB":
                                                raw_st = "A"
                                            elif tok == "BLANK":
                                                raw_st = "NM"
                                            else:
                                                raw_st = "UNCERTAIN"
                                        status_badge = STATUS_MAP.get(raw_st, "🟡 ?")
                                        row_dict[col_key] = status_badge
                                        reasons[(r["roll_no"], col_key)] = c.get("reason", "")
                                df_rows.append(row_dict)

                            st.session_state.review_df = pd.DataFrame(df_rows)
                            st.session_state.reasons_map = reasons
                            st.rerun()
                        else:
                            st.error("AttendAI Vision could not read the sheet. Please retry or adjust photo lighting.")

        # ── STEP 2 & 3: REVIEW SCREEN & QUICK FIX ────────────
        if has_preview:
            preview = st.session_state.scan_preview
            date_cols = preview.get("date_columns", [])
            df = st.session_state.review_df

            # Display system warnings or quality notes if any
            for w in preview.get("warnings", []):
                st.warning(f"{w}")
            if preview.get("quality_notes"):
                st.info(f"{preview.get('quality_notes')}")

            # Top Header Info: Week field + Date Chips + Discard button
            r_top1, r_top2, r_top3 = st.columns([1, 3, 1], vertical_alignment="center")
            with r_top1:
                cur_week = preview.get('header', {}).get('week_no') or '08'
                st.text_input("Week", value=str(cur_week), key="header_week_no", label_visibility="collapsed")
            with r_top2:
                chips_html = "".join(
                    f"""<span style="background:#FFFFFF; border:1px solid #C9CEE6; border-radius:8px; padding:6px 12px; font-size:13px; font-weight:600; color:#14183A; margin-right:8px; display:inline-block;">{format_date_chip(d.get('raw_date', 'Slot'))}</span>"""
                    for d in date_cols
                )
                render_html(f"""<div style="display:flex; align-items:center; flex-wrap:wrap;">{chips_html}</div>""")
            with r_top3:
                with st.popover("Discard & rescan"):
                    st.write("Are you sure you want to discard this scan and restart?")
                    if st.button("Yes, discard scan", type="primary", use_container_width=True):
                        try:
                            api_post("/api/vision/clear-cache")
                        except Exception:
                            pass
                        st.session_state.scan_preview = None
                        st.session_state.review_df = None
                        st.session_state.reasons_map = {}
                        st.session_state.last_uploaded_bytes = None
                        st.rerun()

            # Active Date Slots Verification & Confirmation
            missing_cols = [d for d in date_cols if "Date missing" in d.get("raw_date", "") or d.get("needs_confirmation")]
            if missing_cols:
                st.warning(f"{len(missing_cols)} active column(s) have missing dates. Please confirm or edit the suggested dates below before appending.")
                d_boxes = st.columns(len(date_cols))
                for c_i, d_info in enumerate(date_cols):
                    with d_boxes[c_i]:
                        if "Date missing" in d_info.get("raw_date", "") or d_info.get("needs_confirmation"):
                            curr_val = d_info.get("iso_date", "")
                            edited_date = st.text_input(
                                f"Slot {c_i+1} Date",
                                value=curr_val,
                                key=f"date_inp_{c_i}",
                                help="Pre-filled suggestion (previous + 7 days). Click Confirm to save.",
                            )
                            if st.button(f"Confirm Slot {c_i+1}", key=f"conf_btn_{c_i}", use_container_width=True):
                                d_info["raw_date"] = edited_date
                                d_info["iso_date"] = edited_date
                                d_info["needs_confirmation"] = False
                                st.rerun()
                        else:
                            st.success(f"Slot {c_i+1}: {d_info['raw_date']}")

            # Collect uncertain cells using stable slot keys (col_0, col_1, ...)
            uncertain_cells = []
            p_cnt = 0
            a_cnt = 0
            rev_cnt = 0
            nm_cnt = 0

            if df is not None:
                for r_idx, row in df.iterrows():
                    for c_i, d_info in enumerate(date_cols):
                        c_key = f"col_{c_i}"
                        c_val = str(row.get(c_key, "")).strip()
                        if "?" in c_val or c_val == "UNCERTAIN":
                            rev_cnt += 1
                            uncertain_cells.append({
                                "row_idx": r_idx,
                                "roll_no": row["Roll No"],
                                "name": row["Name"],
                                "batch": row["Batch"],
                                "col_key": c_key,
                                "date": d_info["raw_date"],
                                "reason": st.session_state.reasons_map.get((row["Roll No"], c_key), "Uncertain mark"),
                            })
                        elif "P" in c_val:
                            p_cnt += 1
                        elif "A" in c_val and "NA" not in c_val:
                            a_cnt += 1
                        else:
                            nm_cnt += 1

            # Summary strip with tokens
            render_summary_strip(p_cnt, a_cnt, rev_cnt, nm_cnt)

            st.divider()

            # Two-Column Layout: Left = Paper View, Right = Review Matrix / Quick Fix
            c_paper, c_review = st.columns([1, 2], gap="large")

            with c_paper:
                with st.expander("📄 View scanned sheet photo", expanded=False):
                    if st.session_state.get("last_uploaded_bytes"):
                        st.image(st.session_state["last_uploaded_bytes"], use_container_width=True)
                    else:
                        default_fix = Path("backend/tests/fixtures/images/09_sr31_66_multi_dates.png")
                        if default_fix.exists():
                            st.image(str(default_fix), use_container_width=True)
                        else:
                            st.info("No sheet image preview available.")

            with c_review:
                # Segmented Control for Review mode
                qf_label = f"Quick fix ({rev_cnt})"
                grid_label = "Full grid"
                review_mode = st.segmented_control(
                    "Review workflow",
                    [qf_label, grid_label],
                    default=grid_label if rev_cnt == 0 else qf_label,
                    label_visibility="collapsed",
                )

                # ── MODE A: QUICK FIX CARD QUEUE ──────────────────
                if review_mode == qf_label:
                    if len(uncertain_cells) == 0:
                        st.success("All uncertain cells have been resolved! You can now commit below.")
                    else:
                        item = uncertain_cells[0]
                        render_html(f"""
                        <div style="background:#FFFFFF; border:1px solid #E3E6F2; border-left:4px solid #8A5200; border-radius:14px; padding:18px; margin-bottom:16px;">
                            <div style="font-size:12px; color:#8A5200; font-weight:600; text-transform:uppercase;">
                                Uncertain cell verification ({len(uncertain_cells)} in queue)
                            </div>
                            <div style="font-size:20px; font-weight:600; color:#14183A; margin:6px 0;">
                                {item['roll_no']} — {item['name']}
                            </div>
                            <div style="font-size:13px; color:#5B6285;">
                                Date: <strong style="color:#14183A;">{item['date']}</strong> · Batch: <strong style="color:#14183A;">{item['batch']}</strong> · Reason: {item['reason']}
                            </div>
                        </div>
                        """)

                        # 2x2 grid: Finger-friendly on mobile, crisp on desktop
                        q_r1_c1, q_r1_c2 = st.columns(2)
                        with q_r1_c1:
                            if st.button("Present (P)", key="qf_p", use_container_width=True, type="primary"):
                                df.at[item["row_idx"], item["col_key"]] = "P"
                                st.session_state.review_df = df
                                st.rerun()
                        with q_r1_c2:
                            if st.button("Absent (A)", key="qf_a", use_container_width=True):
                                df.at[item["row_idx"], item["col_key"]] = "A"
                                st.session_state.review_df = df
                                st.rerun()

                        q_r2_c1, q_r2_c2 = st.columns(2)
                        with q_r2_c1:
                            if st.button("Not marked (NM)", key="qf_nm", use_container_width=True):
                                df.at[item["row_idx"], item["col_key"]] = "NM"
                                st.session_state.review_df = df
                                st.rerun()
                        with q_r2_c2:
                            if st.button("Not applicable (NA)", key="qf_na", use_container_width=True):
                                df.at[item["row_idx"], item["col_key"]] = "NA"
                                st.session_state.review_df = df
                                st.rerun()

                # ── MODE B: FULL MATRIX GRID ──────────────────────
                else:
                    f_c1, f_c2 = st.columns(2, vertical_alignment="bottom")
                    with f_c1:
                        batch_filter = st.selectbox("Filter batch", ["All Batches", "Batch 1", "Batch 2", "Batch 3", "Batch 4"], key="grid_batch_filter")
                    with f_c2:
                        with st.popover("⚡ Bulk fill NM marks"):
                            st.markdown("**Quickly mark Not Marked (NM) students**")
                            b_col_idx = st.selectbox(
                                "Target date column",
                                range(len(date_cols)),
                                format_func=lambda i: format_date_chip(date_cols[i].get("raw_date", f"Slot {i+1}")),
                                key="bulk_nm_col_sel",
                            )
                            target_ck = f"col_{b_col_idx}"
                            target_date_name = format_date_chip(date_cols[b_col_idx].get("raw_date", f"Slot {b_col_idx+1}"))

                            nm_matches = [
                                idx for idx, r in df.iterrows()
                                if clean_attendance_token(r.get(target_ck, "")) == "NM"
                                and (batch_filter == "All Batches" or str(r.get("Batch", "")).strip() == batch_filter)
                            ]
                            st.info(f"**{len(nm_matches)}** student(s) currently marked as NM for {target_date_name}.")

                            b_btn1, b_btn2 = st.columns(2)
                            with b_btn1:
                                if st.button("Mark all as Absent (A)", use_container_width=True, disabled=len(nm_matches) == 0):
                                    for idx in nm_matches:
                                        st.session_state.review_df.at[idx, target_ck] = "A"
                                    st.toast(f"Marked {len(nm_matches)} NM students as Absent on {target_date_name}")
                                    st.rerun()
                            with b_btn2:
                                if st.button("Mark all as Present (P)", use_container_width=True, type="primary", disabled=len(nm_matches) == 0):
                                    for idx in nm_matches:
                                        st.session_state.review_df.at[idx, target_ck] = "P"
                                    st.toast(f"Marked {len(nm_matches)} NM students as Present on {target_date_name}")
                                    st.rerun()

                    grid_view = st.segmented_control(
                        "Grid view",
                        ["✏️ Double-click editable grid", "📋 Visual pills ledger"],
                        default="✏️ Double-click editable grid",
                        label_visibility="collapsed",
                        key="grid_view_mode",
                    )

                    if grid_view == "✏️ Double-click editable grid":
                        # Prepare filtered view
                        if batch_filter != "All Batches":
                            view_df = df[df["Batch"] == batch_filter].copy()
                        else:
                            view_df = df.copy()

                        # Ensure slot cells are sanitized clean tokens
                        for i in range(len(date_cols)):
                            ck = f"col_{i}"
                            if ck in view_df.columns:
                                view_df[ck] = view_df[ck].apply(clean_attendance_token)

                        col_configs = {
                            "Sr No": st.column_config.NumberColumn("Sr", width="small", disabled=True),
                            "Roll No": st.column_config.TextColumn("Roll No", width="small", disabled=True),
                            "Name": st.column_config.TextColumn("Student Name", width="medium", disabled=False),
                            "Batch": st.column_config.TextColumn("Batch", width="small", disabled=True),
                        }
                        active_cols = ["Sr No", "Roll No", "Name", "Batch"]
                        for i, d in enumerate(date_cols):
                            ck = f"col_{i}"
                            if ck in view_df.columns:
                                active_cols.append(ck)
                                date_label = format_date_chip(d.get("raw_date", f"Slot {i+1}"))
                                col_configs[ck] = st.column_config.SelectboxColumn(
                                    label=date_label,
                                    options=["P", "A", "NM", "NA", "?"],
                                    required=True,
                                    width="small",
                                    help=f"Double-click cell to change mark for {date_label}",
                                )

                        st.caption("💡 **Double-click any attendance cell** to change its mark (**P**, **A**, **NM**, **?**). Edits save automatically.")

                        editor_key = f"review_data_editor_{batch_filter}"
                        edited_view = st.data_editor(
                            view_df[active_cols],
                            key=editor_key,
                            use_container_width=True,
                            hide_index=True,
                            column_config=col_configs,
                            disabled=["Sr No", "Roll No", "Batch"],
                        )

                        # Sync edits back to master review_df
                        changes_detected = False
                        if edited_view is not None:
                            for _, erow in edited_view.iterrows():
                                roll = erow["Roll No"]
                                matches = st.session_state.review_df[st.session_state.review_df["Roll No"] == roll].index
                                if len(matches) > 0:
                                    row_idx = matches[0]
                                    new_name = str(erow.get("Name", "")).strip()
                                    if new_name and new_name != str(st.session_state.review_df.at[row_idx, "Name"]):
                                        st.session_state.review_df.at[row_idx, "Name"] = new_name
                                        changes_detected = True
                                    for i in range(len(date_cols)):
                                        ck = f"col_{i}"
                                        if ck in erow:
                                            new_val = clean_attendance_token(erow[ck])
                                            cur_val = clean_attendance_token(st.session_state.review_df.at[row_idx, ck])
                                            if new_val != cur_val:
                                                st.session_state.review_df.at[row_idx, ck] = new_val
                                                changes_detected = True

                        if changes_detected:
                            st.rerun()

                    else:
                        # Render custom HTML/CSS table with sticky column and token pills
                        render_html(render_review_grid_html(df, date_cols, batch_filter=batch_filter))

                        # Edit Student attendance manual panel
                        with st.expander("Edit student attendance mark manually"):
                            e_c1, e_c2, e_c3 = st.columns(3)
                            with e_c1:
                                stud_list = [f"{r['Roll No']} - {r['Name']}" for _, r in df.iterrows()]
                                sel_stud = st.selectbox("Select student", stud_list, key="edit_sel_stud")
                            with e_c2:
                                sel_col_i = st.selectbox(
                                    "Select date",
                                    range(len(date_cols)),
                                    format_func=lambda i: format_date_chip(date_cols[i].get("raw_date", f"Slot {i+1}")),
                                    key="edit_sel_date",
                                )
                            with e_c3:
                                new_mark = st.selectbox("New mark", ["Present (P)", "Absent (A)", "Not marked (NM)", "Needs review (?)"], key="edit_sel_mark")
                                if st.button("Update mark", use_container_width=True, type="primary"):
                                    roll_match = sel_stud.split(" - ")[0]
                                    row_match_idx = df[df["Roll No"] == roll_match].index[0]
                                    mark_val = {"Present (P)": "P", "Absent (A)": "A", "Not marked (NM)": "NM", "Needs review (?)": "?"}[new_mark]
                                    df.at[row_match_idx, f"col_{sel_col_i}"] = mark_val
                                    st.session_state.review_df = df
                                    st.rerun()

            # Recalculate remaining uncertain count across stable slot keys
            rem_uncertain = 0
            if st.session_state.review_df is not None:
                for c_i in range(len(date_cols)):
                    c_key = f"col_{c_i}"
                    if c_key in st.session_state.review_df.columns:
                        for v in st.session_state.review_df[c_key]:
                            if "?" in str(v or "") or str(v or "") == "UNCERTAIN":
                                rem_uncertain += 1

            st.divider()

            # ── STEP 4: COMMIT TO MASTER EXCEL (STICKY ACTION BAR) ──
            has_unconfirmed_dates = any("Date missing" in str(d.get("raw_date", "")) or d.get("needs_confirmation") for d in date_cols)
            can_commit = (rem_uncertain == 0 and not has_unconfirmed_dates)

            status_msg = "All cells verified. Ready to add to register." if can_commit else (
                f"{rem_uncertain} cell(s) still require review before committing." if rem_uncertain > 0 else "Active column(s) have unconfirmed missing dates."
            )

            render_html(f"""
            <div class="review-action-bar">
                <div>
                    <div style="font-weight:600; color:#14183A; font-size:15px;">Review status</div>
                    <div style="font-size:13px; color:#5B6285;">{status_msg}</div>
                </div>
            </div>
            """)

            c_act1, c_act2 = st.columns([2, 1])

            with c_act1:
                if st.button(
                    "Confirm and add to register",
                    type="primary",
                    disabled=not can_commit,
                    use_container_width=True,
                ):
                    commit_records = []
                    date_iso_list = [d["iso_date"] for d in date_cols]

                    has_missing_cells = False
                    for _, row in st.session_state.review_df.iterrows():
                        roll = row["Roll No"]
                        for d_idx, d_info in enumerate(date_cols):
                            col_key = f"col_{d_idx}"
                            iso_d = d_info["iso_date"]
                            badge_val = row.get(col_key)
                            if badge_val is None:
                                st.error(f"Integrity Error: Missing mark for student {roll} in column {d_idx+1}.")
                                has_missing_cells = True
                                break
                            status_code = REV_STATUS_MAP.get(str(badge_val).strip(), "NM")
                            commit_records.append({
                                "roll_no": roll,
                                "date": iso_d,
                                "status": status_code,
                            })
                        if has_missing_cells:
                            break

                    # Rule: Block "Confirm and add to register" for a NEW roster until every student has a name
                    missing_name_rolls = [
                        r["Roll No"] for _, r in df.iterrows()
                        if not str(r.get("Name", "")).strip() or str(r.get("Name", "")).strip().upper() == str(r.get("Roll No", "")).strip().upper()
                    ]
                    if missing_name_rolls and not subject.get("students"):
                        st.error(f"Cannot commit new roster: {len(missing_name_rolls)} student(s) have missing names. Please enter their names before confirming or use 'Fix names from sheet'.")
                        has_missing_cells = True

                    if not has_missing_cells:
                        commit_students = []
                        for _, r in df.iterrows():
                            b_str = str(r.get("Batch", "1"))
                            m_batch = re.search(r"\d+", b_str)
                            b_num = int(m_batch.group()) if m_batch else 1
                            commit_students.append({
                                "roll_no": r["Roll No"],
                                "name": r.get("Name", ""),
                                "batch": b_num,
                                "sr_no": int(r.get("Sr No", 1)),
                            })

                        commit_payload = {
                            "scan_id": preview.get("scan_id"),
                            "date_columns": date_iso_list,
                            "records": commit_records,
                            "students": commit_students,
                            "overwrite_conflicts": True,
                        }

                        with st.spinner("Appending new dates to master Excel & updating database..."):
                            commit_res = api_post(f"/api/subjects/{subj_id}/commit", json_data=commit_payload)

                        if commit_res:
                            st.success(f"Successfully committed! Appended {len(commit_res.get('added_dates', []))} session(s). New class average: {commit_res.get('class_average_pct')}%.")
                            st.session_state.scan_preview = None
                            st.session_state.review_df = None
                            st.session_state.reasons_map = {}
                            st.rerun()

            with c_act2:
                excel_data = get_subject_excel_bytes(subj_id)
                if excel_data:
                    st.download_button(
                        "Download Excel",
                        data=excel_data,
                        file_name=f"{subject.get('code', 'subject')}_{subject.get('division', '')}_master_attendance.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="dl_excel_commit_bar",
                    )
                else:
                    st.button("Download Excel", disabled=True, use_container_width=True, key="dl_excel_commit_bar_dis")


    # ── TAB 2: REGISTER ──────────────────────────────────────
    with tab_register:
        st.markdown("#### Cumulative Master Register")
        st.caption("All weekly sheets merged into this cumulative master spreadsheet.")

        master_file_path = Path(f"data/subjects/{subj_id}/master_attendance.xlsx")
        if master_file_path.exists():
            try:
                master_df = pd.read_excel(master_file_path, skiprows=3)
                # If formula columns are uncalculated (None), compute them for the web preview
                if "TOTAL" in master_df.columns and master_df["TOTAL"].isna().any():
                    cols = list(master_df.columns)
                    if "Batch" in cols and "TOTAL" in cols:
                        b_idx = cols.index("Batch")
                        t_idx = cols.index("TOTAL")
                        date_cols_preview = cols[b_idx + 1:t_idx]
                        totals, helds, pcts = [], [], []
                        for _, row in master_df.iterrows():
                            p_c = sum(1 for c in date_cols_preview if str(row[c]).strip().upper() == "P")
                            a_c = sum(1 for c in date_cols_preview if str(row[c]).strip().upper() == "A")
                            h_c = p_c + a_c
                            pct_val = round((p_c / h_c * 100), 1) if h_c > 0 else 0.0
                            totals.append(p_c)
                            helds.append(h_c)
                            pcts.append(f"{pct_val}%")
                        master_df["TOTAL"] = totals
                        master_df["HELD"] = helds
                        master_df["ATT %"] = pcts
                st.dataframe(master_df, use_container_width=True)
                excel_data = get_subject_excel_bytes(subj_id)
                if excel_data:
                    st.download_button(
                        "Download Excel",
                        data=excel_data,
                        file_name=f"{subject.get('code', 'subject')}_{subject.get('division', '')}_master_attendance.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        key="dl_excel_register_tab",
                    )
            except Exception as e:
                st.warning(f"Could not preview spreadsheet: {e}")
        else:
            st.info("No master register generated yet. Read and confirm your first sheet in the 'Scan' tab.")

    # ── TAB 3: STUDENTS ──────────────────────────────────────
    with tab_students:
        s_head_col1, s_head_col2 = st.columns([2, 1], vertical_alignment="center")
        with s_head_col1:
            st.markdown("#### Enrolled Students")
            st.caption("Official subject enrollment list with assigned batches and sequential serial numbers.")
        with s_head_col2:
            if st.button("Fix names from sheet", key="fix_roster_btn", use_container_width=True, type="secondary"):
                with st.spinner("Re-reading roster crop and repairing names from sheet..."):
                    res = api_post(f"/api/subjects/{subj_id}/roster/fix-from-sheet")
                    if res and res.get("status") == "ok":
                        st.success("Roster successfully repaired from sheet!")
                        st.rerun()
                    else:
                        st.error("Failed to repair roster from sheet.")

        students = subject.get("students", [])

        if students:
            # Batch filter & Search
            f_col1, f_col2 = st.columns([1, 1])
            with f_col1:
                st_batch_filter = st.selectbox("Filter batch", ["All Batches", "Batch 1", "Batch 2", "Batch 3", "Batch 4"], key="st_batch_filter")
            with f_col2:
                search_query = st.text_input("Search student", placeholder="Search by name or roll number...", key="st_search_inp")

            filtered_students = students
            if search_query:
                sq = search_query.strip().lower()
                filtered_students = [
                    s for s in filtered_students
                    if sq in str(s.get("name", "")).lower() or sq in str(s.get("roll_no", "")).lower()
                ]

            render_html(render_students_table_html(filtered_students, batch_filter=st_batch_filter))

            # Inline Student Edit Form
            with st.expander("Edit Student Name / Batch"):
                stud_options = {
                    f"{s['sr_no']}. {s['name'] or 'Name missing'} ({s['roll_no']})": s
                    for s in students
                }
                sel_label = st.selectbox("Select student to edit", list(stud_options.keys()), key="edit_stud_sel")
                if sel_label:
                    sel_s = stud_options[sel_label]
                    e_col1, e_col2 = st.columns([2, 1])
                    with e_col1:
                        new_name = st.text_input("Student Name (Full Name)", value=sel_s.get("name", ""), key="edit_stud_name")
                    with e_col2:
                        cur_b = sel_s.get("batch", 1)
                        new_batch = st.selectbox("Batch", [1, 2, 3, 4], index=(cur_b - 1) if 1 <= cur_b <= 4 else 0, key="edit_stud_batch")

                    if st.button("Save Student", key="save_stud_btn", type="primary"):
                        if not new_name.strip() or new_name.strip().upper() == sel_s["roll_no"].upper():
                            st.error("Please enter a valid student name (cannot be blank or roll number).")
                        else:
                            patch_res = api_patch(
                                f"/api/subjects/{subj_id}/students/{sel_s['id']}",
                                json_data={"name": new_name.strip().upper(), "batch": new_batch},
                            )
                            if patch_res:
                                st.success("Student updated successfully!")
                                st.rerun()
        else:
            st.info("No students enrolled yet. Scan your first register sheet or upload a roster file below.")

        st.divider()
        st.markdown("##### Import Roster via CSV / Excel")
        roster_file = st.file_uploader("Upload Roster File (.csv or .xlsx)", type=["csv", "xlsx"], key="roster_upload_file")
        if roster_file:
            if st.button("Upload & Replace Roster", key="upload_roster_btn"):
                files = {"file": (roster_file.name, roster_file.getvalue(), roster_file.type)}
                updated = api_post(f"/api/subjects/{subj_id}/roster/upload", files=files)
                if updated:
                    st.success("Roster updated successfully!")
                    st.rerun()

    # ── TAB 4: HISTORY ───────────────────────────────────────
    with tab_history:
        st.markdown("#### Session History")
        st.caption("Audit trail of processed attendance sheets for this subject.")
        scans = subject.get("scans", [])
        if scans:
            hist_rows = [
                {"Session": s.get("id"), "Date/Week": s.get("week_no") or "General", "Created": s.get("created_at", "")[:10], "Status": s.get("status")}
                for s in scans
            ]
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No scan history yet for this subject.")


def render_header_bar():
    health = api_get("/api/health") or {}
    is_manual = "Manual" in health.get("engine_chip", "") or health.get("status") != "ok"
    chip_text = "AttendAI Vision · Online" if not is_manual else "Manual mode"

    breadcrumb = None
    if st.session_state.current_subject_id:
        subject = api_get(f"/api/subjects/{st.session_state.current_subject_id}")
        if subject:
            breadcrumb = f"Subjects / {subject.get('code')}, {subject.get('class_name')} Div {subject.get('division')}"
        else:
            breadcrumb = "Subjects"
    else:
        breadcrumb = "Subjects"

    render_top_bar(breadcrumb=breadcrumb, engine_chip=chip_text, is_manual=is_manual)


def render_footer():
    st.markdown('<div style="height: 36px;"></div>', unsafe_allow_html=True)
    st.caption("AttendAI — Single Cumulative Register System · Vidyalankar Institute of Technology (v1.2.0)")


# ─────────────────────────────────────────────────────────────
# 6. APP MAIN ROUTER
# ─────────────────────────────────────────────────────────────
def main():
    render_header_bar()
    if st.session_state.current_subject_id is None:
        render_home_view()
    else:
        render_workspace_view()
    render_footer()

if __name__ == "__main__":
    main()