import os
import shutil
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUDIT_DIR = Path("ui_audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
IMG_FIXTURE = str(Path("backend/tests/fixtures/images/09_sr31_66_multi_dates.png").resolve())

AUDIT_JS = """
() => {
    function parseRgb(colorStr) {
        if (!colorStr) return null;
        const m = colorStr.match(/rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)(?:\\s*,\\s*([\\d.]+))?\\s*\\)/);
        if (!m) return null;
        return {
            r: parseInt(m[1], 10),
            g: parseInt(m[2], 10),
            b: parseInt(m[3], 10),
            a: m[4] !== undefined ? parseFloat(m[4]) : 1.0
        };
    }

    function getLuminance(rgb) {
        const a = [rgb.r, rgb.g, rgb.b].map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    function getContrast(rgb1, rgb2) {
        const l1 = getLuminance(rgb1);
        const l2 = getLuminance(rgb2);
        const lighter = Math.max(l1, l2);
        const darker = Math.min(l1, l2);
        return (lighter + 0.05) / (darker + 0.05);
    }

    function blend(fg, bg) {
        return {
            r: Math.round(fg.r * fg.a + bg.r * (1 - fg.a)),
            g: Math.round(fg.g * fg.a + bg.g * (1 - fg.a)),
            b: Math.round(fg.b * fg.a + bg.b * (1 - fg.a)),
            a: 1.0
        };
    }

    function getEffectiveBg(el) {
        let cur = el;
        const pageBg = { r: 247, g: 248, b: 252, a: 1.0 }; // #F7F8FC
        let layers = [];

        while (cur && cur !== document.documentElement) {
            const style = window.getComputedStyle(cur);
            const parsed = parseRgb(style.backgroundColor);
            if (parsed && parsed.a > 0.05) {
                layers.unshift(parsed);
                if (parsed.a >= 0.95) break;
            }
            cur = cur.parentElement;
        }

        let bg = pageBg;
        for (const layer of layers) {
            bg = blend(layer, bg);
        }
        return bg;
    }

    const results = [];
    const elements = document.querySelectorAll('*');

    for (const node of elements) {
        if (['SCRIPT', 'STYLE', 'SVG', 'PATH', 'NOSCRIPT'].includes(node.tagName)) continue;
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const style = window.getComputedStyle(node);
        if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) < 0.1) continue;

        let directText = '';
        for (const child of node.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) {
                const t = child.nodeValue.trim();
                if (t.length > 0) directText += t + ' ';
            }
        }
        directText = directText.trim();
        if (!directText) continue;

        const textColor = parseRgb(style.color);
        if (!textColor) continue;

        const bgColor = getEffectiveBg(node);
        const ratio = getContrast(textColor, bgColor);

        const fontSize = parseFloat(style.fontSize) || 14;
        const isBold = parseInt(style.fontWeight, 10) >= 700 || style.fontWeight === 'bold';
        const isLarge = fontSize >= 18 || (fontSize >= 14 && isBold);
        const threshold = isLarge ? 3.0 : 4.5;

        const isIdentical = textColor.r === bgColor.r && textColor.g === bgColor.g && textColor.b === bgColor.b;
        if (ratio < threshold || isIdentical) {
            results.push({
                text: directText.substring(0, 45),
                tagName: node.tagName,
                className: (typeof node.className === 'string' ? node.className : ''),
                fontSize: fontSize,
                fontWeight: style.fontWeight,
                color: style.color,
                bgColor: `rgb(${bgColor.r}, ${bgColor.g}, ${bgColor.b})`,
                ratio: Math.round(ratio * 100) / 100,
                threshold: threshold
            });
        }
    }
    return results;
}
"""

def audit():
    total_failures = 0
    all_failure_details = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        configurations = [
            ("dark", 1440, 900),
            ("dark", 390, 844),
            ("light", 1440, 900),
            ("light", 390, 844),
        ]

        for scheme, w, h in configurations:
            ctx = browser.new_context(
                color_scheme=scheme,
                viewport={"width": w, "height": h}
            )
            page = ctx.new_page()

            # ── 1. HOME SCREEN ────────────────────────────────
            page.goto("http://localhost:8501?view=home", wait_until="networkidle")
            page.wait_for_timeout(2000)

            failures = page.evaluate(AUDIT_JS)
            scr_path = AUDIT_DIR / f"home_{scheme}_{w}px.png"
            page.screenshot(path=str(scr_path))
            if failures:
                total_failures += len(failures)
                all_failure_details.append((f"Home ({scheme}, {w}px)", failures))

            # ── 2. NEW SUBJECT DIALOG ─────────────────────────
            try:
                new_btn = page.locator("button:has-text('+ New subject')").first
                if new_btn.is_visible():
                    new_btn.click()
                    page.wait_for_timeout(1000)
                    failures = page.evaluate(AUDIT_JS)
                    scr_path = AUDIT_DIR / f"new_subject_{scheme}_{w}px.png"
                    page.screenshot(path=str(scr_path))
                    if failures:
                        total_failures += len(failures)
                        all_failure_details.append((f"New Subject Dialog ({scheme}, {w}px)", failures))
                    print(f"[{scheme} {w}px] New Subject Dialog audited: {len(failures)} failures")
                    # Close dialog
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)
            except Exception as e:
                print(f"Dialog error: {e}")

            # ── 3. SUBJECT PAGE (SCAN UPLOAD) ─────────────────
            page.goto("http://localhost:8501", wait_until="networkidle")
            page.wait_for_timeout(1500)
            open_btn = page.locator("button:has-text('Open')").first
            if open_btn.is_visible():
                open_btn.click()
                page.wait_for_timeout(2500)

                failures = page.evaluate(AUDIT_JS)
                scr_path = AUDIT_DIR / f"subject_scan_{scheme}_{w}px.png"
                page.screenshot(path=str(scr_path))
                if failures:
                    total_failures += len(failures)
                    all_failure_details.append((f"Subject Scan Screen ({scheme}, {w}px)", failures))
                print(f"[{scheme} {w}px] Subject Scan Screen audited: {len(failures)} failures")

                # ── 4. CHECK DATES & REVIEW GRID ───────────────
                try:
                    page.set_input_files("input[type='file']", IMG_FIXTURE)
                    page.wait_for_timeout(2500)
                    read_btn = page.locator("button:has-text('Read sheets'), button:has-text('Read Sheets')").first
                    if read_btn.is_visible():
                        read_btn.click()
                        page.wait_for_selector("text=Review status", timeout=40000)
                        page.wait_for_timeout(2500)

                        # Full Grid review screen audit
                        failures = page.evaluate(AUDIT_JS)
                        scr_path = AUDIT_DIR / f"review_fullgrid_{scheme}_{w}px.png"
                        page.screenshot(path=str(scr_path))
                        if failures:
                            total_failures += len(failures)
                            all_failure_details.append((f"Review Full Grid ({scheme}, {w}px)", failures))
                        print(f"[{scheme} {w}px] Review Full Grid audited: {len(failures)} failures", flush=True)

                        # Quick Fix mode audit
                        try:
                            qf_btn = page.locator("button:has-text('Quick fix')").first
                            if qf_btn.is_visible():
                                qf_btn.click()
                                page.wait_for_timeout(1500)
                                failures = page.evaluate(AUDIT_JS)
                                scr_path = AUDIT_DIR / f"review_quickfix_{scheme}_{w}px.png"
                                page.screenshot(path=str(scr_path))
                                if failures:
                                    total_failures += len(failures)
                                    all_failure_details.append((f"Review Quick Fix ({scheme}, {w}px)", failures))
                                print(f"[{scheme} {w}px] Review Quick Fix audited: {len(failures)} failures", flush=True)
                        except Exception as e:
                            print(f"Quick Fix error: {e}", flush=True)
                except Exception as e:
                    print(f"Review upload error: {e}", flush=True)

                # ── 5. REGISTER TAB ───────────────────────────
                try:
                    reg_tab = page.locator("p:has-text('Register')").first
                    if reg_tab.count() > 0:
                        reg_tab.click()
                        page.wait_for_timeout(1500)
                        failures = page.evaluate(AUDIT_JS)
                        scr_path = AUDIT_DIR / f"register_{scheme}_{w}px.png"
                        page.screenshot(path=str(scr_path))
                        if failures:
                            total_failures += len(failures)
                            all_failure_details.append((f"Register Tab ({scheme}, {w}px)", failures))
                        print(f"[{scheme} {w}px] Register Tab audited: {len(failures)} failures", flush=True)
                except Exception as e:
                    print(f"Register Tab error: {e}", flush=True)

                # ── 6. STUDENTS TAB ───────────────────────────
                try:
                    stud_tab = page.locator("p:has-text('Students')").first
                    if stud_tab.count() > 0:
                        stud_tab.click()
                        page.wait_for_timeout(1500)
                        failures = page.evaluate(AUDIT_JS)
                        scr_path = AUDIT_DIR / f"students_{scheme}_{w}px.png"
                        page.screenshot(path=str(scr_path))
                        if failures:
                            total_failures += len(failures)
                            all_failure_details.append((f"Students Tab ({scheme}, {w}px)", failures))
                        print(f"[{scheme} {w}px] Students Tab audited: {len(failures)} failures", flush=True)
                except Exception as e:
                    print(f"Students Tab error: {e}", flush=True)

                # ── 7. HISTORY TAB ────────────────────
                try:
                    hist_tab = page.locator("p:has-text('History')").first
                    if hist_tab.count() > 0:
                        hist_tab.click()
                        page.wait_for_timeout(1500)
                        failures = page.evaluate(AUDIT_JS)
                        scr_path = AUDIT_DIR / f"history_{scheme}_{w}px.png"
                        page.screenshot(path=str(scr_path))
                        if failures:
                            total_failures += len(failures)
                            all_failure_details.append((f"History Tab ({scheme}, {w}px)", failures))
                        print(f"[{scheme} {w}px] History Tab audited: {len(failures)} failures", flush=True)
                except Exception as e:
                    print(f"History Tab error: {e}", flush=True)

            ctx.close()

        browser.close()

    print("===============================================================")
    print("                AUTOMATED CONTRAST AUDIT REPORT                 ")
    print("===============================================================")
    if total_failures == 0:
        print("RESULT: 0 failures! All text nodes meet or exceed WCAG AA contrast.")
    else:
        print(f"RESULT: {total_failures} contrast failure(s) found:")
        for screen_name, f_list in all_failure_details:
            print(f"\n--- {screen_name} ---")
            for f in f_list:
                print(f"  * \"{f['text']}\" <{f['tagName']} class=\"{f['className']}\">")
                print(f"    Color: {f['color']} | Bg: {f['bgColor']} | Ratio: {f['ratio']}:1 (min {f['threshold']}:1)")

    return total_failures

if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    res = audit()
    sys.exit(0 if res == 0 else 1)

