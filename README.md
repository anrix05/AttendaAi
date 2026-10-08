# AttendAI — Smart Attendance Digitization System

<p align="center">
  <strong>Vidyalankar Institute of Technology (VIT)</strong><br>
  Automated paper register attendance digitization powered by Google Gemini Vision & FastAPI
</p>

---

## Overview

**AttendAI** digitizes handwritten academic attendance registers into **one cumulative master Excel register per subject**. 

Instead of generating fragmented spreadsheets for every lecture, AttendAI matches each student by their university **Roll Number**, preserves student rosters, appends newly verified date columns chronologically to the right, and maintains dynamic Excel formula columns (`TOTAL`, `HELD`, and `ATT %`).

### Key Capabilities

- **Vision Extraction**: Uses Google Gemini Vision (with Anthropic Claude fallback) to digitize Indian college attendance registers.
- **VIT Marking Vocabulary**:
  - Handwritten signatures $\rightarrow$ **P** (Present)
  - Explicit `AB` markings (pink, red, blue, or black ink) $\rightarrow$ **A** (Absent)
  - Spanning arrows (`↑`, `↓`, `↕`) $\rightarrow$ Deterministic range propagation anchored to `AB`
  - Empty cells in active sessions $\rightarrow$ **NM** (Not Marked)
- **Multi-Batch Roster Support**: Full support for all institutional lab and theory batches (**Batch 1**, **Batch 2**, **Batch 3**, and **Batch 4**).
- **Interactive Review Spreadsheet**:
  - **Double-click any cell** to quickly edit marks (`P`, `A`, `NM`, `?`).
  - **⚡ Bulk Fill NM Tool**: Quickly resolve unwritten cells (e.g. absent students left blank on paper) with one click.
  - Quick-fix card queue for ambiguous marks (`?`).
- **Cumulative Master Excel Engine**:
  - Maintains a single `master_attendance.xlsx` per subject.
  - Dynamically formatted with institutional headers, clean column widths, and live Excel formulas (`=COUNTIF(...)`, `=IF(...)`).
  - Real-time attendance preview right in the browser.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLite, SQLAlchemy, OpenPyXL, Pillow
- **Frontend**: Streamlit, Pandas, Altair
- **Vision Engines**: Google GenAI SDK (`gemini-2.5-flash` / `gemini-3.5-flash-lite`), Anthropic Claude Vision
- **Testing**: Pytest (54+ automated tests covering parsing, arrows, cumulative mergers, and APIs)

---

## Quick Start (Windows)

### 1. Clone the Repository
```bash
git clone git@github.com:anrix05/AttendaAi.git
cd AttendaAi
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Add your Google Gemini API key to `.env`:
```env
GEMINI_API_KEY="your_google_gemini_api_key_here"
GEMINI_MODEL="gemini-3.5-flash-lite"
PRIVACY_MODE="columns_only"
SEND_NAMES_TO_AI=true
DEBUG=true
```

### 3. Launch AttendAI (1-Click)
Run the launcher script:
```bat
run.bat
```
This automatically activates your virtual environment, launches the **FastAPI Backend** (`http://127.0.0.1:8000`), and opens the **Streamlit Academic Dashboard** (`http://localhost:8501`).

---

## Manual Execution

### Backend (FastAPI)
```powershell
uvicorn backend.main:app --reload --port 8000
```
- **Interactive API Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Endpoint**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### Frontend (Streamlit)
```powershell
streamlit run frontend/app.py --server.port 8501
```
- **Dashboard**: [http://localhost:8501](http://localhost:8501)

---

## Automated Test Suite

Run the full automated test suite (54 tests):
```powershell
pytest backend/tests/ -v
```

---

## Project Structure

```text
├── backend/
│   ├── excel/               # Cumulative Excel append & openpyxl engine
│   ├── routes/              # FastAPI endpoints (subjects, scans, attendance)
│   ├── vision/
│   │   ├── engines/         # Gemini & Claude vision drivers
│   │   ├── arrow_resolver.py# Deterministic range arrow resolver
│   │   └── aligner.py       # Roster alignment & OCR digit normalization
│   ├── database.py          # SQLAlchemy models & SQLite setup
│   ├── main.py              # FastAPI application entry point
│   └── roster.py            # Master roster union & roll number validation
├── frontend/
│   ├── app.py               # Streamlit application dashboard
│   └── assets/              # Institutional branding & icons
├── ui/
│   └── components.py        # Institutional design system & HTML/CSS templates
├── .env.example             # Template for API credentials
├── run.bat                  # One-click Windows launcher
└── requirements.txt         # Python dependencies
```

---

## Data Privacy & Institutional Compliance

- **Local Storage**: All scanned student data and master spreadsheets remain on the local server in `data/`.
- **Privacy Mode (`columns_only`)**: Only crops of active date and signature columns are transmitted to vision APIs, never entire student identity sheets.
- **PII Scrubbing**: Server loggers sanitize student names and roll numbers to ensure FERPA/institutional compliance.

---

## License

Developed for Vidyalankar Institute of Technology (VIT). Internal institutional use.
