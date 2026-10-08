"""
scripts/generate_brand_assets.py — Generates SVG and PNG brand assets for AttendAI
Redesigned mark: Ruled ledger cell with confident signature-style tick breaking out through mask knockout.
"""
from pathlib import Path
from PIL import Image, ImageDraw
import matplotlib.textpath
from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MplPath

brand_dir = Path("frontend/assets/brand")
brand_dir.mkdir(parents=True, exist_ok=True)
static_dir = Path("static")
static_dir.mkdir(parents=True, exist_ok=True)

# 1. logo-mark.svg (64x64 viewBox)
# Outlined rounded register cell: x=6 y=10 w=48 h=48, rx=12, stroke #2F3FD0, stroke-width 4, no fill
# Two short ruled lines inside: round caps, stroke #2F3FD0 at 28% opacity, width 3
# One confident pen-stroke tick: d="M20 34 L30 46 C34 32 44 18 60 8" stroke #2F3FD0 width 5.5
# Knock-out mask: tick path stroke-width 11 cutting through the square outline
logo_mark_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" fill="none">
  <defs>
    <mask id="register-cell-cutout" maskUnits="userSpaceOnUse">
      <rect x="0" y="0" width="64" height="64" fill="#FFFFFF" />
      <path d="M20 34 L30 46 C34 32 44 18 60 8"
            stroke="#000000" stroke-width="11"
            stroke-linecap="round" stroke-linejoin="round" fill="none" />
    </mask>
  </defs>
  <!-- Register Cell Outline (knocked out by tick) -->
  <rect x="6" y="10" width="48" height="48" rx="12"
        stroke="#2F3FD0" stroke-width="4" fill="none"
        mask="url(#register-cell-cutout)" />
  <!-- Two Ruled Ledger Lines Inside -->
  <line x1="16" y1="22" x2="32" y2="22"
        stroke="#2F3FD0" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
  <line x1="16" y1="30" x2="25" y2="30"
        stroke="#2F3FD0" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
  <!-- Confident Signature Tick Breaking Out -->
  <path d="M20 34 L30 46 C34 32 44 18 60 8"
        stroke="#2F3FD0" stroke-width="5.5"
        stroke-linecap="round" stroke-linejoin="round" fill="none" />
</svg>'''

# 2. favicon.svg (Simplified 64x64 version for small sizes)
# Solid #2F3FD0 rounded-square tile (rx ~22%), white tick only (~9% width = 5.8px), no ruled lines, no break-out
favicon_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" fill="none">
  <rect width="64" height="64" rx="14" fill="#2F3FD0" />
  <path d="M18 33 L27 43 L46 22"
        stroke="#FFFFFF" stroke-width="5.8"
        stroke-linecap="round" stroke-linejoin="round" fill="none" />
</svg>'''

# Generate vectorized path outline for text "AttendAI"
def get_text_svg_path(text: str, x: float, y: float, size: float):
    prop = FontProperties(weight='bold', family='sans-serif')
    tp = matplotlib.textpath.TextPath((x, y), text, size=size, prop=prop)
    cmds = []
    for vertices, code in tp.iter_segments():
        if code == MplPath.MOVETO:
            cmds.append(f"M {vertices[0]:.2f} {-vertices[1]:.2f}")
        elif code == MplPath.LINETO:
            cmds.append(f"L {vertices[0]:.2f} {-vertices[1]:.2f}")
        elif code == MplPath.CURVE3:
            cmds.append(f"Q {vertices[0]:.2f} {-vertices[1]:.2f} {vertices[2]:.2f} {-vertices[3]:.2f}")
        elif code == MplPath.CURVE4:
            cmds.append(f"C {vertices[0]:.2f} {-vertices[1]:.2f} {vertices[2]:.2f} {-vertices[3]:.2f} {vertices[4]:.2f} {-vertices[5]:.2f}")
        elif code == MplPath.CLOSEPOLY:
            cmds.append("Z")
    return " ".join(cmds)

# Wordmark baseline at y=58, font size 42, start x=86 (64 + 22 gap)
text_outline_path = get_text_svg_path("AttendAI", x=86, y=-58, size=42)

# 3. logo-full.svg (Full lockup, light background)
logo_full_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 64" width="280" height="64" fill="none">
  <defs>
    <mask id="register-cell-cutout-full" maskUnits="userSpaceOnUse">
      <rect x="0" y="0" width="64" height="64" fill="#FFFFFF" />
      <path d="M20 34 L30 46 C34 32 44 18 60 8"
            stroke="#000000" stroke-width="11"
            stroke-linecap="round" stroke-linejoin="round" fill="none" />
    </mask>
  </defs>
  <!-- Mark (Aligned baseline at y=58) -->
  <g transform="translate(0, 0)">
    <rect x="6" y="10" width="48" height="48" rx="12"
          stroke="#2F3FD0" stroke-width="4" fill="none"
          mask="url(#register-cell-cutout-full)" />
    <line x1="16" y1="22" x2="32" y2="22"
          stroke="#2F3FD0" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
    <line x1="16" y1="30" x2="25" y2="30"
          stroke="#2F3FD0" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
    <path d="M20 34 L30 46 C34 32 44 18 60 8"
          stroke="#2F3FD0" stroke-width="5.5"
          stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <!-- Outlined Wordmark "AttendAI" in #141B4D (No font required) -->
  <path d="{text_outline_path}" fill="#141B4D" />
</svg>'''

# 4. logo-full-dark.svg (Full lockup, dark background)
logo_full_dark_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 64" width="280" height="64" fill="none">
  <defs>
    <mask id="register-cell-cutout-dark" maskUnits="userSpaceOnUse">
      <rect x="0" y="0" width="64" height="64" fill="#FFFFFF" />
      <path d="M20 34 L30 46 C34 32 44 18 60 8"
            stroke="#000000" stroke-width="11"
            stroke-linecap="round" stroke-linejoin="round" fill="none" />
    </mask>
  </defs>
  <!-- Mark (Aligned baseline at y=58) in #E8EBFC -->
  <g transform="translate(0, 0)">
    <rect x="6" y="10" width="48" height="48" rx="12"
          stroke="#E8EBFC" stroke-width="4" fill="none"
          mask="url(#register-cell-cutout-dark)" />
    <line x1="16" y1="22" x2="32" y2="22"
          stroke="#E8EBFC" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
    <line x1="16" y1="30" x2="25" y2="30"
          stroke="#E8EBFC" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" />
    <path d="M20 34 L30 46 C34 32 44 18 60 8"
          stroke="#E8EBFC" stroke-width="5.5"
          stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <!-- Outlined Wordmark "AttendAI" in #E8EBFC (No font required) -->
  <path d="{text_outline_path}" fill="#E8EBFC" />
</svg>'''

# Write SVG files
files = {
    brand_dir / "logo-mark.svg": logo_mark_svg,
    brand_dir / "logo-full.svg": logo_full_svg,
    brand_dir / "logo-full-dark.svg": logo_full_dark_svg,
    brand_dir / "favicon.svg": favicon_svg,
    static_dir / "favicon.svg": favicon_svg,
    static_dir / "logo-full.svg": logo_full_svg,
}

for path, content in files.items():
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"Wrote {path}")

# Draw high-res anti-aliased PNG favicons using Pillow with supersampling (8x)
def draw_favicon_png(size: int, output_path: Path):
    scale = 8
    canvas_size = size * scale
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 64x64 base coordinate space
    # Rounded tile: 0..64, rx=14 (21.9%)
    radius = (14.0 / 64.0) * canvas_size
    draw.rounded_rectangle(
        [0, 0, canvas_size, canvas_size],
        radius=radius,
        fill="#2F3FD0"
    )

    # Tick: M18 33 L27 43 L46 22
    # Stroke width: 9% of tile width = 0.09 * canvas_size
    stroke_w = int(round(0.09 * canvas_size))

    p1 = (18.0 * canvas_size / 64.0, 33.0 * canvas_size / 64.0)
    p2 = (27.0 * canvas_size / 64.0, 43.0 * canvas_size / 64.0)
    p3 = (46.0 * canvas_size / 64.0, 22.0 * canvas_size / 64.0)

    # Segment 1
    draw.line([p1, p2], fill="#FFFFFF", width=stroke_w)
    # Segment 2
    draw.line([p2, p3], fill="#FFFFFF", width=stroke_w)

    # Rounded caps and elbow joint
    r_cap = stroke_w / 2.0
    for p in (p1, p2, p3):
        draw.ellipse([p[0] - r_cap, p[1] - r_cap, p[0] + r_cap, p[1] + r_cap], fill="#FFFFFF")

    # Downsample with Lanczos filter for razor-sharp antialiasing
    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    final_img.save(output_path, "PNG")
    print(f"Generated {output_path} ({size}x{size})")

draw_favicon_png(32, brand_dir / "favicon-32.png")
draw_favicon_png(180, brand_dir / "favicon-180.png")
draw_favicon_png(512, brand_dir / "favicon-512.png")

# Also copy to static
draw_favicon_png(32, static_dir / "favicon-32.png")
draw_favicon_png(180, static_dir / "favicon-180.png")
print("Brand asset generation complete.")
