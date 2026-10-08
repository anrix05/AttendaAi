"""
ui/components.py — AttendAI Institutional Ledger Design System & Presentation Components
Scope: Typography, Logo, Visual Identity, CSS Variables, and Component Renderers.
WCAG AA contrast compliant. Self-hosted fonts. Tabular figures on all numbers.
"""
import math
from typing import Dict, Any, Optional, List
import streamlit as st

# Import self-hosted base64 font definitions
try:
    from ui.fonts_data import FONT_FACES_CSS
except ImportError:
    FONT_FACES_CSS = ""


# ─────────────────────────────────────────────────────────────
# 1. INLINE SVG ICONS & BRAND ASSETS
# ─────────────────────────────────────────────────────────────
ICONS = {
    "check": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>""",
    "alert": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>""",
    "download": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>""",
    "folder": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>""",
    "trash": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>""",
    "plus": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>""",
    "arrow_left": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>""",
    "camera": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>""",
    "file_text": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>""",
    "clipboard_check": """<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="m9 14 2 2 4-4"/></svg>""",
}

# The AttendAI Mark: Ruled ledger cell with a confident signature tick breaking out through mask knockout
LOGO_MARK_INLINE_SVG = """<svg class="attendai-logo-mark" width="36" height="36" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;">
  <defs>
    <mask id="attendai-header-cell-cutout" maskUnits="userSpaceOnUse">
      <rect x="0" y="0" width="64" height="64" fill="#FFFFFF" />
      <path d="M20 34 L30 46 C34 32 44 18 60 8"
            stroke="#000000" stroke-width="11"
            stroke-linecap="round" stroke-linejoin="round" fill="none" />
    </mask>
  </defs>
  <!-- Register Cell Outline (uses CSS variable for theme adaptability) -->
  <rect x="6" y="10" width="48" height="48" rx="12"
        stroke="var(--brand, #2F3FD0)" stroke-width="4" fill="none"
        mask="url(#attendai-header-cell-cutout)" />
  <!-- Two Ruled Ledger Lines Inside -->
  <line x1="16" y1="22" x2="32" y2="22"
        stroke="var(--brand, #2F3FD0)" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
  <line x1="16" y1="30" x2="25" y2="30"
        stroke="var(--brand, #2F3FD0)" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
  <!-- Confident Signature Tick Breaking Out -->
  <path d="M20 34 L30 46 C34 32 44 18 60 8"
        stroke="var(--brand, #2F3FD0)" stroke-width="5.5"
        stroke-linecap="round" stroke-linejoin="round" fill="none" />
</svg>"""


def clean_html(html_str: str) -> str:
    """Strips leading/trailing whitespace per line to avoid CommonMark 4-space code block rendering."""
    return "\n".join(line.strip() for line in html_str.strip().splitlines() if line.strip())


def render_html(html_str: str):
    """Safely renders HTML to Streamlit without markdown formatting artifacts."""
    st.markdown(clean_html(html_str), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# 2. MASTER GLOBAL STYLES & INJECTION (Deliverable #1)
# ─────────────────────────────────────────────────────────────
def inject_global_styles():
    """
    Holds all @font-face, CSS color tokens, typography scale, container overrides,
    and institutional ledger styling. Called once at app startup.
    """
    css = f"""
    <style>
    /* 1. Self-hosted font declarations (Zero runtime Google Fonts dependency) */
    {FONT_FACES_CSS}

    /* 2. Color Tokens & Theme Variables */
    :root {{
        color-scheme: light !important;
        --ink:        #141B4D;   /* Headings, wordmark */
        --text:       #1F2937;   /* Body */
        --text-muted: #4B5563;   /* Secondary/meta (WCAG AA >= 4.5:1 on white) */
        --brand:      #2F3FD0;   /* Primary actions, active tab, brand */
        --brand-hover:#2132B8;   /* Primary hover */
        --brand-soft: #E8EBFC;   /* Chips, badges, hover fills */
        --line:       #E3E6EF;   /* Ruled dividers, borders */
        --paper:      #F7F8FC;   /* Ledger page background */
        --sheet:      #FFFFFF;   /* Cards and panel background */

        /* Semantic status tokens */
        --ok:         #0F7B4F;
        --ok-soft:    #E3F5EC;
        --warn:       #B45309;
        --warn-soft:  #FEF3E2;
        --bad:        #B42318;
        --bad-soft:   #FDECEA;

        /* Unified geometry scale */
        --radius-control: 10px;
        --radius-panel:   14px;
        --radius-chip:    999px;
    }}

    /* 3. Streamlit Chrome Suppression */
    header[data-testid="stHeader"],
    footer,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stSidebar"],
    [data-testid="stStatusWidget"],
    #MainMenu,
    .stDeployButton,
    div[data-testid="stAlert"]:has(a[href*="github.com/streamlit"]),
    div:has(> button:has-text("Don't show again")) {{
        display: none !important;
    }}

    div[data-baseweb="popover"]:has(button:has-text("Don't show again")),
    div[data-baseweb="toast"] {{
        display: none !important;
    }}

    /* 4. Canvas & Layout Setup */
    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {{
        font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif !important;
        background-color: var(--paper) !important;
        color: var(--text) !important;
        font-size: 16px;
        line-height: 1.55;
        -webkit-font-smoothing: antialiased;
    }}

    .block-container {{
        max-width: 1240px !important;
        padding-top: 0 !important;
        padding-bottom: 4rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        margin: 0 auto !important;
        background-color: transparent !important;
    }}

    @media (max-width: 768px) {{
        .block-container {{
            padding-left: 1.25rem !important;
            padding-right: 1.25rem !important;
        }}
    }}

    @media (max-width: 390px) {{
        .block-container {{
            padding-left: 14px !important;
            padding-right: 14px !important;
        }}
    }}

    /* 5. Typography Scale & Heading Hierarchy */
    h1, .page-title {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 2.0rem !important;
        line-height: 1.15 !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        color: var(--ink) !important;
        margin: 0 0 6px 0 !important;
    }}

    h2, .section-title {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 1.5rem !important;
        line-height: 1.2 !important;
        font-weight: 600 !important;
        color: var(--ink) !important;
        margin: 0 0 8px 0 !important;
    }}

    h3, .card-title {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 1.2rem !important;
        line-height: 1.25 !important;
        font-weight: 600 !important;
        color: var(--ink) !important;
        margin: 0 0 4px 0 !important;
    }}

    p, label,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] span {{
        color: var(--text) !important;
        font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif !important;
    }}

    /* Preserve Streamlit Material Icon Ligatures (Prevents 'expand_more' / 'upload' text leak) */
    [data-testid="stIconMaterial"],
    span[data-testid="stIconMaterial"],
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-icons {{
        font-family: "Material Symbols Rounded", sans-serif !important;
        font-weight: normal !important;
        font-style: normal !important;
        display: inline-block !important;
        line-height: 1 !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        word-wrap: normal !important;
        white-space: nowrap !important;
        direction: ltr !important;
    }}

    .helper-text, .text-secondary,
    .stCaption, [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {{
        font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif !important;
        color: var(--text-muted) !important;
        font-size: 0.875rem !important;
        line-height: 1.5 !important;
        max-width: 70ch;
    }}

    /* Enforce Tabular Figures for All Institutional Digits */
    .tabular-nums,
    .stat-value,
    .card-ring-text,
    .attendai-table,
    [data-testid="stDataFrame"],
    [data-testid="stDataEditor"] {{
        font-variant-numeric: tabular-nums !important;
    }}

    /* 6. Topbar & Brand Navigation */
    .attendai-topbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 64px;
        background: var(--sheet) !important;
        border: 1px solid var(--line);
        border-top: none;
        padding: 0 24px;
        margin-bottom: 20px;
        border-radius: 0 0 var(--radius-panel) var(--radius-panel);
        box-shadow: 0 1px 3px rgba(20, 27, 77, 0.03);
    }}

    .attendai-wordmark {{
        display: inline-flex;
        align-items: baseline;
        gap: 13px;
        text-decoration: none !important;
        border-bottom: none !important;
        color: inherit !important;
        outline: none;
    }}

    .attendai-wordmark .attendai-logo-mark {{
        transform: translateY(3px);
        flex-shrink: 0;
    }}

    .attendai-wordmark,
    .attendai-wordmark *,
    .attendai-wordmark:hover,
    .attendai-wordmark:visited,
    .attendai-wordmark:active {{
        text-decoration: none !important;
        border-bottom: none !important;
    }}

    .attendai-wordmark:focus-visible {{
        outline: 2px solid var(--brand, #2F3FD0) !important;
        outline-offset: 3px !important;
        border-radius: 4px !important;
    }}

    .attendai-brand-text {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.015em;
        color: var(--ink, #141B4D) !important;
        line-height: 1;
        text-decoration: none !important;
        border-bottom: none !important;
    }}

    .attendai-breadcrumb {{
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.9375rem;
        color: var(--text-muted) !important;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin-left: 20px;
        padding-left: 20px;
        border-left: 1px solid var(--line);
        line-height: 1;
    }}

    .attendai-breadcrumb a {{
        color: var(--text-muted) !important;
        font-weight: 500;
        text-decoration: none;
    }}

    .attendai-breadcrumb a:hover {{
        color: var(--brand) !important;
    }}

    .attendai-breadcrumb .current {{
        color: var(--ink) !important;
        font-weight: 600;
    }}

    .attendai-topbar-right {{
        display: inline-flex;
        align-items: center;
        gap: 14px;
    }}

    .attendai-engine-chip {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 14px;
        border-radius: var(--radius-chip);
        font-family: "IBM Plex Sans", sans-serif;
        font-size: 0.8125rem;
        font-weight: 600;
        background: var(--paper);
        border: 1px solid var(--line);
        color: var(--ink) !important;
    }}

    .attendai-engine-chip.online {{
        color: var(--ok) !important;
        background: var(--ok-soft) !important;
        border-color: transparent !important;
    }}

    .attendai-engine-chip.manual {{
        color: var(--warn) !important;
        background: var(--warn-soft) !important;
        border-color: transparent !important;
    }}

    .attendai-engine-dot {{
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: currentColor;
    }}

    .attendai-avatar {{
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: var(--brand-soft);
        color: var(--brand) !important;
        font-family: "IBM Plex Sans", sans-serif;
        font-weight: 600;
        font-size: 0.8125rem;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border: 1px solid var(--line);
    }}

    /* 7. Stat Strip (Shared Baseline, Tabular Figures) */
    .stat-strip {{
        display: flex;
        align-items: flex-end;
        background: var(--sheet) !important;
        border: 1px solid var(--line);
        border-radius: var(--radius-panel);
        padding: 18px 24px;
        margin-bottom: 24px;
    }}

    .stat-item {{
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
        padding: 0 16px;
    }}

    .stat-item:not(:last-child) {{
        border-right: 1px solid var(--line);
    }}

    .stat-value {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 2.25rem !important;
        font-weight: 700 !important;
        color: var(--ink) !important;
        line-height: 1.1 !important;
        font-variant-numeric: tabular-nums !important;
    }}

    .stat-label {{
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.875rem !important;
        color: var(--text-muted) !important;
        margin-top: 4px;
        font-weight: 400;
        line-height: 1.4;
    }}

    /* 8. Subject Cards & Progress Rings */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: var(--sheet) !important;
        border: 1px solid var(--line) !important;
        border-radius: var(--radius-panel) !important;
        padding: 6px !important;
    }}

    .card-name {{
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        color: var(--ink) !important;
        line-height: 1.25;
        margin-bottom: 4px;
    }}

    .card-meta {{
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.875rem;
        color: var(--text-muted) !important;
    }}

    .card-meta strong {{
        color: var(--ink) !important;
    }}

    .card-stats-row {{
        display: flex;
        align-items: center;
        gap: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--line);
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.875rem;
        color: var(--text-muted) !important;
    }}

    .badge-below75 {{
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: var(--radius-chip);
        background: var(--bad-soft) !important;
        color: var(--bad) !important;
        font-size: 0.75rem;
        font-weight: 600;
        margin-left: auto;
    }}

    /* Center Progress Ring Percentage Inside the Ring */
    .card-ring-wrapper {{
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}

    .card-ring-text {{
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-family: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif !important;
        font-size: 0.95rem;
        font-weight: 600;
        font-variant-numeric: tabular-nums !important;
        line-height: 1;
        text-align: center;
    }}

    /* 9. Buttons, Tabs & Controls (Unified 10px Radius, Visible Focus) */
    .stButton>button,
    button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-primary"],
    [data-baseweb="button"] {{
        border-radius: var(--radius-control) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.9375rem !important;
        font-weight: 500 !important;
        transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }}

    .stButton>button:focus-visible,
    button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    textarea:focus-visible,
    [data-baseweb="tab"]:focus-visible {{
        outline: 2px solid var(--brand) !important;
        outline-offset: 2px !important;
    }}

    .stButton>button,
    button[data-testid="baseButton-secondary"] {{
        background-color: var(--sheet) !important;
        color: var(--ink) !important;
        border: 1px solid var(--line) !important;
        padding: 8px 18px !important;
    }}

    .stButton>button:hover,
    button[data-testid="baseButton-secondary"]:hover {{
        background-color: var(--paper) !important;
        border-color: var(--brand) !important;
        color: var(--brand) !important;
    }}

    .stButton>button[kind="primary"],
    button[data-testid="baseButton-primary"],
    a[data-testid="baseLinkButton-primary"],
    [data-testid="stLinkButton"] a[kind="primary"] {{
        min-height: 44px !important;
        background-color: var(--brand) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--brand) !important;
        font-weight: 600 !important;
    }}

    .stButton>button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover,
    a[data-testid="baseLinkButton-primary"]:hover,
    [data-testid="stLinkButton"] a[kind="primary"]:hover {{
        background-color: var(--brand-hover) !important;
        border-color: var(--brand-hover) !important;
        color: #FFFFFF !important;
    }}

    .stButton>button[kind="primary"] *,
    button[data-testid="baseButton-primary"] *,
    a[data-testid="baseLinkButton-primary"] * {{
        color: #FFFFFF !important;
    }}

    /* Tabs: Plex 500, Active 2px --brand underline + --ink text */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 8px !important;
        border-bottom: 1px solid var(--line) !important;
        background-color: transparent !important;
    }}

    .stTabs [data-baseweb="tab"] {{
        font-family: "IBM Plex Sans", sans-serif !important;
        font-size: 0.9375rem !important;
        font-weight: 500 !important;
        color: var(--text-muted) !important;
        padding: 10px 18px !important;
        border-bottom: 2px solid transparent !important;
        background-color: transparent !important;
    }}

    .stTabs [data-baseweb="tab"]:hover {{
        color: var(--brand) !important;
    }}

    .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        color: var(--ink) !important;
        font-weight: 600 !important;
        border-bottom: 2px solid var(--brand) !important;
    }}

    /* Inputs, Textareas, Selectboxes */
    input, textarea,
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input,
    [data-baseweb="select"] div {{
        background-color: var(--sheet) !important;
        color: var(--text) !important;
        border-color: var(--line) !important;
        border-radius: var(--radius-control) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
    }}

    /* 10. File Uploader Styling (Section 6d) */
    [data-testid="stFileUploader"] {{
        border: none !important;
    }}

    [data-testid="stFileUploaderDropzone"] {{
        border: 1.5px dashed var(--line) !important;
        border-radius: var(--radius-panel) !important;
        background-color: var(--sheet) !important;
        padding: 24px !important;
        transition: border-color 0.15s ease, background-color 0.15s ease;
    }}

    [data-testid="stFileUploaderDropzone"]:hover {{
        border-color: var(--brand) !important;
        background-color: var(--brand-soft) !important;
    }}

    [data-testid="stFileUploaderDropzoneInstructions"] {{
        font-family: "IBM Plex Sans", sans-serif !important;
        color: var(--text) !important;
    }}

    [data-testid="stFileUploaderDropzoneInstructions"] small {{
        color: var(--text-muted) !important;
        font-size: 0.875rem !important;
    }}

    /* 11. Review Grid Status Pills (WCAG AA) */
    .pill-p {{
        background-color: var(--ok-soft) !important;
        color: var(--ok) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: var(--radius-chip);
        display: inline-block;
        font-size: 13px;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }}

    .pill-a {{
        background-color: var(--bad-soft) !important;
        color: var(--bad) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: var(--radius-chip);
        display: inline-block;
        font-size: 13px;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }}

    .pill-rev {{
        background-color: var(--warn-soft) !important;
        color: var(--warn) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: var(--radius-chip);
        display: inline-block;
        font-size: 13px;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }}

    .pill-nm {{
        background-color: #EEF0F7 !important;
        color: var(--text-muted) !important;
        font-family: "IBM Plex Sans", sans-serif !important;
        font-weight: 500;
        padding: 3px 10px;
        border-radius: var(--radius-chip);
        display: inline-block;
        font-size: 13px;
        text-align: center;
        font-variant-numeric: tabular-nums;
    }}

    /* 12. Institutional Ledger Table Container */
    .attendai-table-container {{
        width: 100%;
        overflow-x: auto;
        background: var(--sheet) !important;
        border: 1px solid var(--line);
        border-radius: var(--radius-panel);
        margin-top: 12px;
    }}

    .attendai-table {{
        width: 100%;
        border-collapse: collapse;
        font-family: "IBM Plex Sans", sans-serif;
        font-size: 14px;
        color: var(--text);
        font-variant-numeric: tabular-nums;
    }}

    .attendai-table th {{
        background: var(--paper);
        color: var(--ink);
        font-family: "Bricolage Grotesque", sans-serif;
        font-weight: 600;
        padding: 10px 14px;
        text-align: left;
        border-bottom: 1px solid var(--line);
        white-space: nowrap;
    }}

    .attendai-table td {{
        padding: 10px 14px;
        border-bottom: 1px solid #F0F2F9;
        height: 44px;
        vertical-align: middle;
    }}

    .attendai-table tr:last-child td {{
        border-bottom: none;
    }}

    .attendai-table tr:hover td {{
        background-color: var(--paper);
    }}

    .sticky-name-col {{
        position: sticky;
        left: 0;
        background: var(--sheet);
        font-weight: 500;
        z-index: 2;
        border-right: 1px solid var(--line);
    }}

    .attendai-table tr:hover .sticky-name-col {{
        background: var(--paper);
    }}

    th.sticky-name-col {{
        background: var(--paper);
        z-index: 3;
    }}

    /* 13. Summary Strip */
    .summary-strip {{
        display: flex;
        gap: 12px;
        margin: 14px 0;
        flex-wrap: wrap;
    }}

    .summary-chip {{
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 14px;
        border-radius: var(--radius-control);
        font-family: "IBM Plex Sans", sans-serif;
        font-size: 0.8125rem;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
    }}

    /* 14. Stepper Sequence */
    .stepper-container {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: var(--sheet) !important;
        border: 1px solid var(--line) !important;
        border-radius: var(--radius-panel);
        padding: 14px 28px;
        margin-bottom: 24px;
    }}

    .stepper-step {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: "IBM Plex Sans", sans-serif;
        font-size: 0.875rem;
        font-weight: 500;
        color: var(--text-muted) !important;
    }}

    .stepper-step.active {{
        color: var(--brand) !important;
        font-weight: 600;
    }}

    .stepper-step.done {{
        color: var(--ok) !important;
        font-weight: 600;
    }}

    .step-circle {{
        width: 26px;
        height: 26px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        font-weight: 600;
        border: 1.5px solid var(--line);
        background: var(--sheet);
        color: var(--text-muted) !important;
    }}

    .stepper-step.active .step-circle {{
        background: var(--brand) !important;
        color: #FFFFFF !important;
        border-color: var(--brand) !important;
    }}

    .stepper-step.done .step-circle {{
        background: var(--ok-soft) !important;
        color: var(--ok) !important;
        border-color: var(--ok) !important;
    }}

    .stepper-divider {{
        flex: 1;
        height: 1px;
        background: var(--line);
        margin: 0 16px;
    }}

    /* 15. Sticky Review Action Bar */
    .review-action-bar {{
        position: sticky;
        bottom: 12px;
        z-index: 100;
        background: var(--sheet) !important;
        border: 1px solid var(--line);
        border-radius: var(--radius-panel);
        box-shadow: 0 8px 30px rgba(20, 27, 77, 0.08);
        padding: 14px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 24px;
    }}
    </style>
    """
    render_html(css)


# ─────────────────────────────────────────────────────────────
# 3. TOP BAR & BREADCRUMB
# ─────────────────────────────────────────────────────────────
def render_top_bar(breadcrumb: Optional[str] = None, engine_chip: str = "AttendAI Vision · Online", is_manual: bool = False):
    """Renders the custom top bar with the unified AttendAI logo, breadcrumb, and vision status chip."""
    status_class = "manual" if is_manual else "online"
    tooltip = "Cloud vision engine is active." if not is_manual else "AttendAI Vision is offline. Manual entry mode is active."

    if breadcrumb:
        if breadcrumb.startswith("Subjects /"):
            sub_part = breadcrumb[len("Subjects /"):].strip()
            b_html = f"""<div class="attendai-breadcrumb"><a href="/?view=home" target="_self">Subjects</a> <span style="margin:0 4px; color:var(--line);">/</span> <span class="current">{sub_part}</span></div>"""
        else:
            b_html = f"""<div class="attendai-breadcrumb"><span class="current">{breadcrumb}</span></div>"""
    else:
        b_html = ""

    html = f"""
    <div class="attendai-topbar">
        <div style="display: flex; align-items: center;">
            <a href="/?view=home" target="_self" class="attendai-wordmark" aria-label="AttendAI Home">
                {LOGO_MARK_INLINE_SVG}
                <span class="attendai-brand-text">AttendAI</span>
            </a>
            {b_html}
        </div>
        <div class="attendai-topbar-right">
            <div class="attendai-engine-chip {status_class}" title="{tooltip}">
                <div class="attendai-engine-dot"></div>
                <span class="chip-label">{engine_chip}</span>
            </div>
            <div class="attendai-avatar" title="Faculty Profile">VIT</div>
        </div>
    </div>
    """
    render_html(html)


# ─────────────────────────────────────────────────────────────
# 4. RULED HEADER BAND
# ─────────────────────────────────────────────────────────────
def render_ruled_header(title: str, subtitle: Optional[str] = None):
    """Renders the paper register-inspired ruled header band."""
    sub_html = f"""<div class="helper-text" style="margin-top: 4px;">{subtitle}</div>""" if subtitle else ""
    html = f"""
    <div style="background: var(--sheet); padding: 20px 24px; border: 1px solid var(--line); border-radius: var(--radius-panel); margin: 16px 0 20px 0;">
        <h1 class="page-title">{title}</h1>
        {sub_html}
    </div>
    """
    render_html(html)


# ─────────────────────────────────────────────────────────────
# 5. STAT TILES STRIP
# ─────────────────────────────────────────────────────────────
def render_stat_strip(stats: List[Dict[str, Any]]):
    """
    Renders 4 stat tiles in one row with numbers in Bricolage 700 tabular-nums,
    and labels in Plex 400 --text-muted, aligned on a shared baseline.
    """
    items_html = []
    for s in stats:
        items_html.append(f"""
        <div class="stat-item">
            <div class="stat-value">{s.get('value', 0)}</div>
            <div class="stat-label">{s.get('label', '')}</div>
        </div>
        """)
    html = f"""
    <div class="stat-strip">
        {''.join(items_html)}
    </div>
    """
    render_html(html)


# ─────────────────────────────────────────────────────────────
# 6. CLASS AVERAGE RING (SVG WITH CENTERED PERCENTAGE)
# ─────────────────────────────────────────────────────────────
def generate_svg_ring(pct: float, total_sessions: int = 1, size: int = 56, stroke_width: int = 4) -> str:
    """
    Generates an SVG circular progress ring with percentage label centered inside the ring
    using Bricolage Grotesque 600 and tabular-nums.
    """
    if total_sessions == 0:
        return f"""
        <div class="card-ring-wrapper" style="width:{size}px; height:{size}px; border:1.5px dashed var(--line); border-radius:50%; display:flex; align-items:center; justify-content:center; text-align:center;">
            <span style="font-family:'IBM Plex Sans',sans-serif; font-size:9px; font-weight:500; color:var(--text-muted); line-height:1.1;">No scans</span>
        </div>
        """

    radius = (size - stroke_width * 2) / 2
    circumference = 2 * math.pi * radius
    pct_clamped = max(0.0, min(100.0, pct))
    offset = circumference * (1.0 - (pct_clamped / 100.0))
    ring_color = "#0F7B4F" if pct_clamped >= 75.0 else "#B42318"

    return f"""
    <div class="card-ring-wrapper" style="width:{size}px; height:{size}px;">
        <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="transform: rotate(-90deg);">
            <circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" stroke="var(--line)" stroke-width="{stroke_width}"/>
            <circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" stroke="{ring_color}" stroke-width="{stroke_width}"
                stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" stroke-linecap="round"/>
        </svg>
        <span class="card-ring-text" style="color: {ring_color};">{pct_clamped:.0f}%</span>
    </div>
    """


# ─────────────────────────────────────────────────────────────
# 7. SUBJECT CARD CONTENT (INSIDE st.container)
# ─────────────────────────────────────────────────────────────
BRANCH_CODES: Dict[str, str] = {
    "Computer Engineering": "CMPN",
    "Information Technology": "INFT",
    "Electronics & Telecommunication": "EXTC",
    "Electronics & Computer Science": "EXCS",
    "Biomedical Engineering": "BIOM",
}


def render_subject_card_html(subject: Dict[str, Any]) -> str:
    """Builds HTML inside st.container(border=True). Preserves subject name casing with Bricolage 600."""
    stats = subject.get("stats", {})
    avg_pct = stats.get("average_attendance_pct", 0.0)
    low_count = stats.get("students_below_75", 0)
    total_sessions = stats.get("total_sessions", 0)
    enrolled_students = stats.get("enrolled_students", 0)

    ring_html = generate_svg_ring(avg_pct, total_sessions=total_sessions, size=54, stroke_width=4)
    low_chip_html = f"""<span class="badge-below75">{low_count} below 75%</span>""" if (low_count > 0 and total_sessions > 0) else ""

    classes_label = f"<strong>{total_sessions}</strong> sheets" if total_sessions > 0 else "No sheets scanned yet"

    # Preserves subject name in original user casing (Section 6f)
    subject_title = f"{subject.get('code')} — {subject.get('name')}"
    branch_val = subject.get("branch")
    if branch_val:
        b_code = BRANCH_CODES.get(branch_val)
        branch_display = f"{branch_val} ({b_code})" if b_code else branch_val
        branch_str = f" · {branch_display}"
    else:
        branch_str = ""

    return f"""
    <div style="padding: 4px 2px 8px 2px;">
        <div class="card-top" style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
            <div>
                <div class="card-name">{subject_title}</div>
                <div class="card-meta">
                    {subject.get('class_name')}{branch_str}, Div {subject.get('division')} · Faculty: <strong>{subject.get('faculty')}</strong>
                </div>
            </div>
            {ring_html}
        </div>
        <div class="card-stats-row">
            <span>{classes_label}</span>
            <span><strong>{enrolled_students}</strong> students</span>
            {low_chip_html}
        </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────
# 8. PERSISTENT SCAN STEPPER
# ─────────────────────────────────────────────────────────────
def render_stepper(current_step: int = 1):
    """
    Renders the persistent horizontal 4-step sequence:
    1. Upload > 2. Check dates > 3. Review > 4. Done
    """
    steps = [
        (1, "Upload"),
        (2, "Check dates"),
        (3, "Review"),
        (4, "Done"),
    ]
    items_html = []
    for idx, (num, name) in enumerate(steps):
        if num < current_step:
            state = "done"
            badge = """<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>"""
        elif num == current_step:
            state = "active"
            badge = str(num)
        else:
            state = "pending"
            badge = str(num)

        items_html.append(f"""
        <div class="stepper-step {state}">
            <span class="step-circle">{badge}</span>
            <span>{name}</span>
        </div>
        """)
        if idx < len(steps) - 1:
            items_html.append("""<div class="stepper-divider"></div>""")

    html = f"""
    <div class="stepper-container">
        {''.join(items_html)}
    </div>
    """
    render_html(html)


# ─────────────────────────────────────────────────────────────
# 9. EMPTY STATE
# ─────────────────────────────────────────────────────────────
def render_empty_state_html(title: str, description: str) -> str:
    """Renders an institutional ledger-themed empty state."""
    return f"""
    <div style="background:var(--sheet); border:1px solid var(--line); border-radius:var(--radius-panel); padding:40px 24px; text-align:center; margin:16px 0;">
        <div style="color:var(--text-muted); margin-bottom:12px;">{ICONS['clipboard_check']}</div>
        <div style="font-family:'Bricolage Grotesque',sans-serif; font-size:1.15rem; font-weight:600; color:var(--ink); margin-bottom:6px;">{title}</div>
        <div class="helper-text" style="margin:0 auto;">{description}</div>
    </div>
    """


# ─────────────────────────────────────────────────────────────
# 10. REVIEW HELPERS & CUSTOM HTML TABLE
# ─────────────────────────────────────────────────────────────
def format_date_chip(raw_date_str: str) -> str:
    """Formats date strings like '9/9/26' to concise format like '9 Sep'."""
    import re
    from datetime import datetime
    if not raw_date_str:
        return "Unknown"
    try:
        dt = datetime.strptime(raw_date_str.split()[0], "%Y-%m-%d")
        return f"{dt.day} {dt.strftime('%b')}"
    except Exception:
        pass
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", raw_date_str.strip())
    if m:
        d, mon = int(m.group(1)), int(m.group(2))
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        if 1 <= mon <= 12:
            return f"{d} {month_names[mon-1]}"
    return raw_date_str.strip()


def render_summary_strip(p_cnt: int, a_cnt: int, rev_cnt: int, nm_cnt: int):
    """Renders the summary strip for attendance review with tokens paired with letter codes."""
    html = f"""
    <div class="summary-strip">
        <div class="summary-chip" style="background:var(--ok-soft); color:var(--ok);">
            <span>Present:</span> <strong>{p_cnt}</strong>
        </div>
        <div class="summary-chip" style="background:var(--bad-soft); color:var(--bad);">
            <span>Absent:</span> <strong>{a_cnt}</strong>
        </div>
        <div class="summary-chip" style="background:var(--warn-soft); color:var(--warn);">
            <span>Needs review:</span> <strong>{rev_cnt}</strong>
        </div>
        <div class="summary-chip" style="background:#EEF0F7; color:var(--text-muted);">
            <span>Not marked:</span> <strong>{nm_cnt}</strong>
        </div>
    </div>
    """
    render_html(html)


def render_review_grid_html(df, date_cols: List[Dict[str, Any]], batch_filter: str = "All Batches") -> str:
    """
    Renders the review grid as custom HTML/CSS:
    - Sticky student name column
    - Date headers like '9 Sep'
    - Paired colored status pills (P, A, NM, ?)
    - 44px row heights, tabular numerals
    - No raw Sr No column, no repeated Batch column
    """
    import html as html_lib
    if df is None or df.empty:
        return "<p style='color:var(--text-muted);'>No attendance data loaded.</p>"

    filtered = df
    if batch_filter != "All Batches":
        filtered = filtered[filtered["Batch"] == batch_filter]

    header_th = ["<th class='sticky-name-col' style='min-width:200px;'>Student</th>"]
    col_keys = []
    for i, d in enumerate(date_cols):
        col_key = f"col_{i}"
        col_keys.append(col_key)
        date_label = format_date_chip(d.get("raw_date", f"Slot {i+1}"))
        header_th.append(f"<th style='text-align:center; min-width:85px;'>{html_lib.escape(date_label)}</th>")

    def cell_to_pill(val: Any) -> str:
        s = str(val or "").strip()
        if "P" in s and "?" not in s:
            return '<span class="pill-p">P</span>'
        elif "A" in s and "?" not in s and "NA" not in s:
            return '<span class="pill-a">A</span>'
        elif "?" in s:
            return '<span class="pill-rev">?</span>'
        elif "NM" in s or "BLANK" in s or not s:
            return '<span class="pill-nm">NM</span>'
        elif "NA" in s:
            return '<span class="pill-nm">—</span>'
        return f'<span class="pill-nm">{html_lib.escape(s)}</span>'

    rows_html = []
    for _, row in filtered.iterrows():
        raw_name = str(row.get("Name", "") or "").strip()
        roll = html_lib.escape(str(row.get("Roll No", "") or "").strip())
        batch_val = html_lib.escape(str(row.get("Batch", "") or "").strip())

        if not raw_name or raw_name.upper() == roll.upper():
            name_display = '<span style="color:var(--bad); font-weight:600; font-size:12px; background:var(--bad-soft); padding:2px 8px; border-radius:6px;">Name missing</span>'
        else:
            name_display = html_lib.escape(raw_name.title())

        tds = [f"""
        <td class="sticky-name-col">
            <div style="font-weight:600; color:var(--ink); font-size:14px; line-height:1.2;">{name_display}</div>
            <div style="font-size:12px; color:var(--text-muted); margin-top:2px; font-variant-numeric:tabular-nums;">{roll} · {batch_val}</div>
        </td>
        """]

        for ck in col_keys:
            val = row.get(ck, "")
            pill = cell_to_pill(val)
            tds.append(f"<td style='text-align:center;'>{pill}</td>")

        rows_html.append(f"<tr>{''.join(tds)}</tr>")

    table_html = f"""
    <div class="attendai-table-container">
        <table class="attendai-table">
            <thead>
                <tr>{''.join(header_th)}</tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </div>
    """
    return table_html


def render_students_table_html(students: List[Dict[str, Any]], batch_filter: str = "All Batches") -> str:
    """
    Renders the Enrolled Students roster table:
    - Sticky student name column (Title Case in UI)
    - Roll number in tabular figures below
    - Batch badge
    - Sequential 1..N serials
    """
    import html as html_lib
    if not students:
        return "<p style='color:var(--text-muted);'>No students enrolled yet.</p>"

    filtered = students
    if batch_filter != "All Batches":
        import re
        m_bf = re.search(r"\d+", str(batch_filter))
        b_num = int(m_bf.group()) if m_bf else None
        filtered = [s for s in students if (b_num is not None and s.get("batch") == b_num) or f"Batch {s.get('batch')}" == batch_filter]

    rows_html = []
    for s in filtered:
        sr_no = s.get("sr_no", "")
        roll = html_lib.escape(str(s.get("roll_no", "")).strip())
        raw_name = str(s.get("name", "")).strip()
        batch_num = s.get("batch", 1)

        if not raw_name or raw_name.upper() == roll.upper():
            name_display = '<span style="color:var(--bad); font-weight:600; font-size:12px; background:var(--bad-soft); padding:2px 8px; border-radius:6px;">Name missing</span>'
        else:
            name_display = html_lib.escape(raw_name.title())

        batch_pill = f'<span style="background:var(--brand-soft); color:var(--brand); font-weight:600; font-size:12px; padding:4px 10px; border-radius:12px;">Batch {batch_num}</span>'

        rows_html.append(f"""
        <tr>
            <td style="text-align:center; font-weight:600; color:var(--text-muted); width:65px; font-variant-numeric:tabular-nums;">{sr_no}</td>
            <td class="sticky-name-col">
                <div style="font-weight:600; color:var(--ink); font-size:14px; line-height:1.2;">{name_display}</div>
                <div style="font-size:12px; color:var(--text-muted); margin-top:2px; font-variant-numeric:tabular-nums;">{roll}</div>
            </td>
            <td style="text-align:center; width:110px;">{batch_pill}</td>
        </tr>
        """)

    table_html = f"""
    <div class="attendai-table-container">
        <table class="attendai-table">
            <thead>
                <tr>
                    <th style="text-align:center; width:65px;">Sr No</th>
                    <th class="sticky-name-col">Student</th>
                    <th style="text-align:center; width:110px;">Batch</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </div>
    """
    return table_html
