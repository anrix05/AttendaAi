import sys
import shutil
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

ART_DIR = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\6e1565bf-1dca-4251-8eb6-ad44b52c26b2")
LOCAL_DIR = Path(r"d:\My Works\Attendence\screenshots")
LOCAL_DIR.mkdir(parents=True, exist_ok=True)

# Clean up any test subjects
con = sqlite3.connect("data/app.db")
cur = con.cursor()
cur.execute("DELETE FROM subjects WHERE id='test_subj_serials'")
cur.execute("DELETE FROM students WHERE subject_id='test_subj_serials'")
con.commit()
con.close()


def capture_students_screen(width=1440, height=900, name="students_tab_1440px.png"):
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome_path, headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            color_scheme="light",
        )
        page = context.new_page()
        page.goto("http://localhost:8501/?subject_id=tybtech_b_ss_theory", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Click the "Students" tab
        # Try locator for tab with text "Students"
        tab = page.locator("[data-baseweb='tab']:has-text('Students'), p:has-text('Students'), button:has-text('Students')").first
        if tab.is_visible():
            tab.click()
            page.wait_for_timeout(2500)
        else:
            print("Tab locator not visible immediately, clicking by coordinate or index...")
            tabs = page.locator("[data-baseweb='tab']").all()
            if len(tabs) >= 3:
                tabs[2].click()
                page.wait_for_timeout(2500)

        local_path = LOCAL_DIR / name
        page.screenshot(path=str(local_path), full_page=True)
        art_path = ART_DIR / name
        shutil.copy2(local_path, art_path)
        print(f"Captured {name}: {local_path} (copied to {art_path})")
        browser.close()


if __name__ == "__main__":
    capture_students_screen(1440, 900, "students_tab_1440px.png")
    capture_students_screen(390, 844, "students_tab_390px.png")
