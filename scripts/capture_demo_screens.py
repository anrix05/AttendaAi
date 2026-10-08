"""
scripts/capture_demo_screens.py — Capture verification screenshots at 1366x768
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

output_dir = Path("screenshots")
output_dir.mkdir(parents=True, exist_ok=True)
artifacts_dir = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\6e1565bf-1dca-4251-8eb6-ad44b52c26b2")

fixture_path = Path("backend/tests/fixtures/images/01_ss_divb_sr1_30_arrows.jpg").resolve()

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        device_scale_factor=1.0,
    )
    page = context.new_page()

    # 1. Subjects Home
    print("Navigating to Home...")
    page.goto("http://localhost:8501/?view=home", wait_until="networkidle")
    time.sleep(2)
    p1 = output_dir / "01_subjects_home_1366.png"
    page.screenshot(path=str(p1))
    print(f"Captured: {p1}")

    # 2. Subject Workspace > Scan tab (upload state)
    print("Navigating to Subject Workspace...")
    page.goto("http://localhost:8501/?subject_id=tybtech_b_ss_theory", wait_until="networkidle")
    time.sleep(2)
    p2 = output_dir / "02_subject_scan_upload_1366.png"
    page.screenshot(path=str(p2))
    print(f"Captured: {p2}")

    # 3. Upload sheet and get Review Grid
    print("Uploading attendance sheet fixture...")
    file_input = page.locator('input[type="file"]')
    if file_input.count() > 0:
        file_input.first.set_input_files(str(fixture_path))
        time.sleep(2)
        # Click "Read sheets"
        read_btn = page.locator('button:has-text("Read sheets")')
        if read_btn.count() > 0:
            print("Clicking 'Read sheets'...")
            read_btn.first.click()
            # Wait for extraction (up to 20 seconds)
            time.sleep(12)
            p3 = output_dir / "03_review_grid_1366.png"
            page.screenshot(path=str(p3))
            print(f"Captured: {p3}")

    # 4. Click Register tab
    print("Navigating to Register tab...")
    register_tab = page.locator('[data-baseweb="tab"]:has-text("Register")')
    if register_tab.count() > 0:
        register_tab.first.click()
        time.sleep(2)
        p4 = output_dir / "04_register_tab_1366.png"
        page.screenshot(path=str(p4))
        print(f"Captured: {p4}")

    browser.close()

# Copy to artifacts directory
for f in ["01_subjects_home_1366.png", "02_subject_scan_upload_1366.png", "03_review_grid_1366.png", "04_register_tab_1366.png"]:
    src = output_dir / f
    if src.exists():
        dst = artifacts_dir / f
        try:
            import shutil
            shutil.copy(src, dst)
            print(f"Copied {f} to {dst}")
        except Exception as ex:
            print(f"Error copying {f}: {ex}")
