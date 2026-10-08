# AttendAI Visual Identity & Typography Refresh — Changes Log

**Date:** October 2026  
**Audience:** Faculty & HODs, Vidyalankar Institute of Technology (VIT)  
**Scope:** Strict visual presentation layer, typography, brand assets, favicon, and CSS tokens. Zero backend/data changes.

---

## 1. Files Touched

| File | Change Summary |
|---|---|
| `ui/components.py` | Replaced legacy fonts and inline styling with `inject_global_styles()`, containing self-hosted `@font-face` declarations, official color tokens (`--ink`, `--text`, `--text-muted`, `--brand`, `--line`, `--paper`, etc.), institutional ledger typography scale, centered card ring percentages, Streamlit container overrides, and protected Material Icon ligatures. |
| `frontend/app.py` | Updated `st.set_page_config` with `page_title="AttendAI · Smart attendance"` and `page_icon` pointing to the new `favicon-32.png`. Injected SVG favicon hook. Called `inject_global_styles()`. Refined workspace headers and upload dropzone labels to sentence case. |
| `.streamlit/config.toml` | Enabled `enableStaticServing = true` and updated core brand theme tokens (`primaryColor = "#2F3FD0"`, `textColor = "#1F2937"`). |
| `ui/theme.py` | Simplified module to delegate directly to `ui.components.inject_global_styles()`. |

---

## 2. New Asset Files

### Fonts (`frontend/assets/fonts/` & `static/fonts/`)
- `bricolage-grotesque-600.woff2` (Display headings, card titles, stat counters)
- `bricolage-grotesque-700.woff2` (Page titles, brand wordmark, large numbers)
- `ibm-plex-sans-400.woff2` (Body, table cells, secondary descriptions)
- `ibm-plex-sans-500.woff2` (Tabs, buttons, breadcrumbs)
- `ibm-plex-sans-600.woff2` (Table headers, sticky names, batch chips)
- `ui/fonts_data.py`: Pre-encoded base64 `@font-face` definitions for 100% offline, zero-network runtime reliability.

### Brand & Favicons (`frontend/assets/brand/` & `static/`)
- `logo-mark.svg`: Ruled register cell (rounded square in `#2F3FD0`) with faint ledger lines and white signature pen stroke breaking out past the right edge.
- `logo-mark-simplified.svg`: Clear, high-contrast mark for smaller sizes.
- `logo-full.svg`: Mark + "AttendAI" wordmark in single-color `#141B4D` Bricolage Grotesque 700.
- `logo-full-dark.svg`: Full lockup with white wordmark for dark backgrounds.
- `favicon.svg`: Vector favicon for modern browser tab headers.
- `favicon-32.png`: 32x32 crisp raster icon.
- `favicon-180.png`: 180x180 Apple touch icon.
- `favicon-512.png`: 512x512 PWA/high-res raster icon.

---

## 3. Specific UI Fixes Implemented

1. **Subject Card Ring**: The percentage label ("81%") is now centered directly inside the SVG ring in Bricolage 600 tabular figures (`0.95rem`), with zero vertical misalignment.
2. **Text Contrast (WCAG AA compliant)**: All secondary helper text, captions, and footer labels use `--text-muted` (`#4B5563`), guaranteeing $\ge 4.5:1$ contrast against white surfaces.
3. **Stat Strip**: Digits formatted in Bricolage 700 with `font-variant-numeric: tabular-nums;`, aligned with `--text-muted` labels along a shared baseline.
4. **File Uploader Dropzone**: Styled with dashed `--line` (`#E3E6EF`) border, secondary helper text ("200MB per file · JPG, PNG"), and sentence-case label. Material Symbol icons protected from font overrides.
5. **Top Bar Header**: Left lockup features the signature tick mark and single-color "AttendAI" wordmark; center breadcrumb is in Plex 500 `--text-muted` (`--ink` for active page); right status chip displays `AttendAI Vision · Online` aligned on the same midline.
6. **Card Titles**: Uses Bricolage 600 and preserves user's exact subject casing (e.g. `SS — Signals And System`).
7. **Buttons & Inputs**: Unified `10px` border-radius across all inputs and buttons, minimum `44px` height for primary actions, and visible `2px` `--brand` focus outline for keyboard accessibility.
8. **Tabs**: Styled in IBM Plex Sans 500; active tab has a `2px` `--brand` underline and `--ink` text; inactive tabs use `--text-muted`.

---

## 4. Verification Screenshots (1366x768)

- `01_subjects_home_1366.png`: Subjects Home dashboard with stat strip and centered rings.
- `02_subject_scan_upload_1366.png`: Subject Workspace > Scan tab in upload state.
- `03_review_grid_1366.png`: Scan Review screen with stepper, date chips, and paired status pills.
- `04_register_tab_1366.png`: Cumulative Master Register preview table with tabular figures.

---

## 5. Logo Redesign & Wordmark Link Fix (Latest)

- **Logo Concept**: Redesigned mark to represent an institutional paper register cell with a teacher's confident signature tick breaking out of it.
  - Outlined rounded square (`x=6 y=10 w=48 h=48 rx=12`, stroke `#2F3FD0`, width `4`, no fill).
  - Two short ruled ledger lines inside at 28% opacity (`#2F3FD0`, width `3`, round caps).
  - Confident signature tick (`M20 34 L30 46 C34 32 44 18 60 8`, stroke width `5.5`, round caps/joins).
  - SVG `<mask id="...">` knockout with wider stroke (`11`) to cut through the register square's outline without clipping ruled lines.
- **Header Lockup**:
  - Inlined SVG mark (`36px` tall) using CSS variables (`var(--brand, #2F3FD0)`).
  - Wordmark "AttendAI" in Bricolage Grotesque 700 (`1.5rem`), single color `#141B4D` (`var(--ink)`).
  - Square baseline aligned to wordmark baseline with a clean `13px` gap (`0.35x` mark width).
- **Underline & Focus Fix**:
  - Eliminated all underlines on `.attendai-wordmark`, hovered/visited/active states, and child elements (`text-decoration: none !important; border-bottom: none !important;`).
  - Added visible accessibility focus ring (`2px #2F3FD0`, offset `3px`) on `:focus-visible`.
  - Configured breadcrumb links to only underline when hovered.
- **Small-Size & Favicon Export**:
  - Solid `#2F3FD0` rounded tile (`rx ~22%`) with thickened white tick (`~9%` stroke width) and no ruled lines or break-out for crisp 16-32px display.
  - Exported `favicon.svg`, `favicon-32.png`, `favicon-180.png`, and `favicon-512.png`.
- **Files Touched**:
  - `ui/components.py` (inline mark SVG, wordmark styling, underline elimination)
  - `frontend/assets/brand/` (`logo-mark.svg`, `logo-full.svg`, `logo-full-dark.svg`, `favicon.svg`, `favicon-32.png`, `favicon-180.png`, `favicon-512.png`)
  - `scripts/generate_brand_assets.py` (vectorized brand generator with Pillow antialiasing)

---

## 6. Official Institutional Branches & Code Integration

- Updated the branch selection and display across the application to match the 5 official departments:
  1. **Computer Engineering** (`CMPN`)
  2. **Information Technology** (`INFT`)
  3. **Electronics & Telecommunication** (`EXTC`)
  4. **Electronics & Computer Science** (`EXCS`)
  5. **Biomedical Engineering** (`BIOM`)
- **Modal Dropdown**: Formatted with both full department title and code badge (e.g. `Computer Engineering (CMPN)`).
- **Search & Filter**: Added code search support so typing `CMPN`, `INFT`, `EXTC`, `EXCS`, or `BIOM` instantly matches subjects in that branch.
- **Card & Workspace Display**: Enhanced subject cards and workspace header to display the branch title alongside its official code.


