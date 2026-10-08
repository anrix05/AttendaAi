"""
scripts/capture_review_grid.py — Upload sample sheet and capture review grid screenshot
"""
import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

fixture_path = Path("backend/tests/fixtures/images/01_ss_divb_sr1_30_arrows.jpg").resolve()
artifacts_dir = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\6e1565bf-1dca-4251-8eb6-ad44b52c26b2")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    page.goto("http://localhost:8501/?subject_id=tybtech_b_ss_theory")
    page.wait_for_selector(".section-title", timeout=15000)

    file_input = page.locator('input[type="file"]')
    print("Found file input:", file_input.count())
    if file_input.count() > 0:
        file_input.first.set_input_files(str(fixture_path))
        print("Set input files. Waiting for Streamlit to upload...")
        time.sleep(4)

        read_btn = page.locator('button:has-text("Read sheets")')
        print("Read button count:", read_btn.count())
        if read_btn.count() > 0:
            read_btn.first.click()
            print("Clicked 'Read sheets'. Waiting for review table...")
            page.wait_for_selector(".attendai-table", timeout=40000)
            time.sleep(2)
            out_p = Path("screenshots/03_review_grid_1366.png")
            page.screenshot(path=str(out_p))
            print("Captured:", out_p)
            shutil.copy(out_p, artifacts_dir / out_p.name)
            print("Copied to artifacts.")
        else:
            print("Read sheets button not visible.")
            page.screenshot(path="screenshots/debug_no_read_btn.png")
    else:
        print("File input not found.")

    browser.close()
