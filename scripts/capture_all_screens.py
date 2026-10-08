"""
scripts/capture_all_screens.py — Capture verification screenshots at 1366x768
"""
import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

output_dir = Path("screenshots")
output_dir.mkdir(parents=True, exist_ok=True)
artifacts_dir = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\6e1565bf-1dca-4251-8eb6-ad44b52c26b2")
fixture_path = Path("backend/tests/fixtures/images/01_ss_divb_sr1_30_arrows.jpg").resolve()

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 768})

    # 1. Subjects Home
    print("1. Capturing Home...")
    page.goto("http://localhost:8501/?view=home")
    page.wait_for_selector(".page-title", timeout=15000)
    page.wait_for_timeout(1000)
    page.screenshot(path="screenshots/01_subjects_home_1366.png")

    # 2. Subject Workspace > Scan tab (upload state)
    print("2. Capturing Workspace Scan Upload...")
    page.goto("http://localhost:8501/?subject_id=tybtech_b_ss_theory")
    page.wait_for_selector(".section-title", timeout=15000)
    page.wait_for_timeout(1500)
    page.screenshot(path="screenshots/02_subject_scan_upload_1366.png")

    # 3. Check Register tab
    print("3. Capturing Register tab...")
    register_tab = page.locator('[data-baseweb="tab"]:has-text("Register")')
    if register_tab.count() > 0:
        register_tab.first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path="screenshots/04_register_tab_1366.png")
        print("Captured Register tab.")

    # 4. Upload photo to get Review Grid
    print("4. Capturing Review Grid...")
    scan_tab = page.locator('[data-baseweb="tab"]:has-text("Scan")')
    if scan_tab.count() > 0:
        scan_tab.first.click()
        page.wait_for_timeout(1000)

        # Upload file
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            print("Uploading fixture file...")
            file_input.first.set_input_files(str(fixture_path))
            page.wait_for_timeout(2000)

            # Click Read sheets
            read_btn = page.locator('button:has-text("Read sheets")')
            if read_btn.count() > 0:
                print("Clicking 'Read sheets'...")
                read_btn.first.click()
                # Wait for review table to appear
                page.wait_for_selector(".attendai-table", timeout=25000)
                page.wait_for_timeout(2000)
                page.screenshot(path="screenshots/03_review_grid_1366.png")
                print("Captured Review Grid.")

    browser.close()

# Copy to artifacts directory
for f in ["01_subjects_home_1366.png", "02_subject_scan_upload_1366.png", "03_review_grid_1366.png", "04_register_tab_1366.png"]:
    src = output_dir / f
    if src.exists():
        dst = artifacts_dir / f
        shutil.copy(src, dst)
        print(f"Copied {f} to {dst}")
