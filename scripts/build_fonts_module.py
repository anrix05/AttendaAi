import base64
from pathlib import Path

fonts_dir = Path("frontend/assets/fonts")
css_lines = []

font_configs = [
    ("Bricolage Grotesque", 600, "bricolage-grotesque-600.woff2"),
    ("Bricolage Grotesque", 700, "bricolage-grotesque-700.woff2"),
    ("IBM Plex Sans", 400, "ibm-plex-sans-400.woff2"),
    ("IBM Plex Sans", 500, "ibm-plex-sans-500.woff2"),
    ("IBM Plex Sans", 600, "ibm-plex-sans-600.woff2"),
]

for family, weight, filename in font_configs:
    filepath = fonts_dir / filename
    data = filepath.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    css_lines.append(f"""@font-face {{
  font-family: '{family}';
  font-style: normal;
  font-weight: {weight};
  font-display: swap;
  src: url(data:font/woff2;base64,{b64}) format('woff2');
}}""")

full_css = "\n".join(css_lines)
print(f"Generated @font-face CSS length: {len(full_css)} chars")

out_file = Path("ui/fonts_data.py")
with open(out_file, "w", encoding="utf-8") as f:
    f.write(f'"""Self-hosted base64 font definitions for AttendAI."""\nFONT_FACES_CSS = """{full_css}"""\n')

print(f"Successfully wrote {out_file}")
