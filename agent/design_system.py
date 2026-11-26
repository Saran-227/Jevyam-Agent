"""Jevyam Technologies — Premium Graphic Design System 2.0.

Modular, agency-grade creative engine featuring:
- Sophisticated Blue & White brand palette (#1769E0, #102A56, #FFFFFF, #EAF3FF)
- Multi-family editorial typography (Poppins, Playfair Display + Italic, Inter, Space Grotesk)
- Real human photography integrated via circular, arch, rounded, and split-panel masks
- 8 distinct creative directions supporting both 1200x1200 (square) and 1080x1350 (portrait)
- Design quality validation gate

Note: Kept isolated for preview and review until explicitly enabled in production.
"""

from io import BytesIO
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field

from agent.pillars import get_pillar_by_name

# ==============================================================================
# 1. BRAND COLOR PALETTE (BLUE & WHITE SYSTEM)
# ==============================================================================

SQUARE_SIZE = (1200, 1200)
PORTRAIT_SIZE = (1080, 1350)
LANDSCAPE_SIZE = (1200, 628)

ROYAL_BLUE = (23, 105, 224, 255)      # #1769E0
DEEP_NAVY = (16, 42, 86, 255)         # #102A56
WHITE = (255, 255, 255, 255)          # #FFFFFF
ICE_BLUE = (234, 243, 255, 255)       # #EAF3FF

LIGHT_BLUE = (187, 216, 255, 255)     # #BBD8FF
SOFT_GREY = (244, 246, 250, 255)      # #F4F6FA
DARK_CHARCOAL = (32, 42, 56, 255)     # #202A38
MUTED_SLATE = (92, 107, 128, 255)     # #5C6B80
BORDER_BLUE = (209, 227, 252, 255)    # #D1E3FC

DESIGN_DIRECTIONS: List[str] = [
    "editorial_collage",
    "human_centric_campaign",
    "bold_typography_poster",
    "split_editorial",
    "business_metrics",
    "creative_service_showcase",
    "visual_storytelling",
    "multi_panel_agency",
    "diagonal_slice",
    "magazine_quote",
    "timeline_blueprint",
    "floating_frame_hero",
    "landscape_banner",
    "checklist_card",
]

_ROOT_DIR = Path(__file__).resolve().parent.parent
_ASSETS_DIR = _ROOT_DIR / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"
_PHOTOS_DIR = _ASSETS_DIR / "photos"

_SERVICE_PHOTO_MAP: Dict[str, str] = {
    "website": "website_development.jpg",
    "crm": "crm_solutions.jpg",
    "inventory": "inventory_management.jpg",
    "custom": "custom_software.jpg",
    "mobile": "mobile_apps.jpg",
    "digital": "digital_marketing.jpg",
    "ai": "ai_automation.jpg",
    "it": "it_consultancy.jpg",
}

# ==============================================================================
# 2. MULTI-FAMILY TYPOGRAPHY ENGINE
# ==============================================================================

_FONT_CACHE: Dict[Tuple[str, int], Any] = {}


def get_brand_font(family: str, size: int) -> Any:
    """Load bundled Google Font family with weight/style support and safe fallback."""
    key = (family, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    file_map = {
        "poppins_bold": ("Poppins-Bold.ttf", None),
        "poppins_semibold": ("Poppins-SemiBold.ttf", None),
        "poppins_regular": ("Poppins-Regular.ttf", None),
        "playfair_bold": ("PlayfairDisplay-Bold.ttf", [700]),
        "playfair_italic": ("PlayfairDisplay-Italic.ttf", [600]),
        "inter_regular": ("Inter-Regular.ttf", [400]),
        "inter_semibold": ("Inter-Regular.ttf", [600]),
        "space_bold": ("SpaceGrotesk-Bold.ttf", [700]),
    }
    fname, axes = file_map.get(family, ("Poppins-Regular.ttf", None))
    fpath = _FONTS_DIR / fname

    font = None
    if fpath.exists():
        try:
            font = ImageFont.truetype(str(fpath), size=size)
            if axes and hasattr(font, "set_variation_by_axes"):
                try:
                    font.set_variation_by_axes(axes)
                except Exception:
                    pass
        except Exception:
            font = None

    if font is None:
        fallback = "C:/Windows/Fonts/georgia.ttf" if "playfair" in family else "C:/Windows/Fonts/segoeuib.ttf"
        try:
            font = ImageFont.truetype(fallback, size=size)
        except Exception:
            font = ImageFont.load_default()

    _FONT_CACHE[key] = font
    return font


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> List[str]:
    words = (text or "").strip().split()
    if not words:
        return []
    lines: List[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if draw.textbbox((0, 0), cand, font=font)[2] <= max_width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_headline(
    draw: ImageDraw.ImageDraw,
    text: str,
    family: str,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int = 24,
) -> Tuple[Any, List[str]]:
    """Fit text cleanly inside max_width and max_lines with zero clipping."""
    for sz in range(start_size, min_size - 1, -2):
        fnt = get_brand_font(family, sz)
        lines = _wrap_lines(draw, text, fnt, max_width)
        if len(lines) <= max_lines:
            return fnt, lines
    fnt = get_brand_font(family, min_size)
    lines = _wrap_lines(draw, text, fnt, max_width)[:max_lines]
    if lines and len(lines) == max_lines:
        last = lines[-1]
        while len(last) > 3 and draw.textbbox((0, 0), last + "...", font=fnt)[2] > max_width:
            last = last[:-1].rstrip()
        if last != lines[-1]:
            lines[-1] = last + "..."
    return fnt, lines


# ==============================================================================
# 3. REUSABLE DESIGN COMPONENTS
# ==============================================================================

def resolve_service_photo(
    service_category: Optional[str] = None,
    photo_path: Optional[Path] = None,
    secondary: bool = False,
) -> Optional[Path]:
    """Resolve an appropriate human photograph for the target service."""
    if photo_path and Path(photo_path).exists():
        return Path(photo_path)

    svc = (service_category or "").lower()
    chosen = "website_development.jpg"
    for key, fname in _SERVICE_PHOTO_MAP.items():
        if key in svc:
            chosen = fname
            break

    if secondary:
        all_photos = sorted(_PHOTOS_DIR.glob("*.jpg"))
        for p in all_photos:
            if p.name != chosen:
                return p

    cand = _PHOTOS_DIR / chosen
    if cand.exists():
        return cand
    existing = sorted(_PHOTOS_DIR.glob("*.jpg"))
    return existing[0] if existing else None


def draw_masked_photo(
    canvas: Image.Image,
    photo_path: Optional[Path],
    box: Tuple[int, int, int, int],
    mask_type: str = "rounded",
    radius: int = 24,
    border_color: Optional[Tuple[int, int, int, int]] = None,
    border_width: int = 0,
) -> bool:
    """Place a high-res human photograph cropped cleanly into a geometric mask."""
    if not photo_path or not photo_path.exists():
        return False

    x1, y1, x2, y2 = box
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    src = Image.open(photo_path).convert("RGBA")
    cropped = ImageOps.fit(src, (w, h), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))

    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    if mask_type == "circle":
        md.ellipse([0, 0, w, h], fill=255)
    elif mask_type == "arch":
        r = w // 2
        md.ellipse([0, 0, w, w], fill=255)
        md.rectangle([0, r, w, h], fill=255)
    elif mask_type == "rect":
        md.rectangle([0, 0, w, h], fill=255)
    else:
        md.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.paste(cropped, (0, 0), mask)
    canvas.alpha_composite(layer, (x1, y1))

    if border_color and border_width > 0:
        draw = ImageDraw.Draw(canvas)
        if mask_type == "circle":
            draw.ellipse([x1, y1, x2, y2], outline=border_color, width=border_width)
        elif mask_type == "rounded":
            draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=border_color, width=border_width)
    return True


def draw_logo_mark(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    on_dark: bool = False,
    scale: float = 1.0,
) -> int:
    """Place official Jevyam star mark + clean typography without background artifacts."""
    mark_h = int(48 * scale)
    mark_w = mark_h
    mark_file = "mark_dark.png" if on_dark else "mark_light.png"
    pasted = False

    p = _ASSETS_DIR / mark_file
    if p.exists():
        try:
            raw = Image.open(p).convert("RGBA")
            px = list(raw.getdata())
            raw.putdata([(r, g, b, 0 if a < 28 else a) for (r, g, b, a) in px])
            mark_w = int(raw.width * (mark_h / raw.height))
            resized = raw.resize((mark_w, mark_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(resized, (x, y))
            pasted = True
        except Exception:
            pass

    if not pasted:
        cx, cy = x + mark_h // 2, y + mark_h // 2
        col = LIGHT_BLUE if on_dark else ROYAL_BLUE
        draw.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], outline=col, width=3)

    title_col = WHITE if on_dark else DEEP_NAVY
    sub_col = LIGHT_BLUE if on_dark else ROYAL_BLUE
    tx = x + mark_w + int(12 * scale)
    draw.text((tx, y + int(2 * scale)), "JEEVYAM", font=get_brand_font("poppins_bold", int(23 * scale)), fill=title_col)
    draw.text((tx + 1, y + int(28 * scale)), "TECHNOLOGIES", font=get_brand_font("inter_semibold", int(10 * scale)), fill=sub_col)
    return tx + int(155 * scale)


def draw_label_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    bg: Tuple[int, int, int, int] = ICE_BLUE,
    fg: Tuple[int, int, int, int] = ROYAL_BLUE,
    border: Optional[Tuple[int, int, int, int]] = None,
    font_size: int = 14,
) -> int:
    fnt = get_brand_font("space_bold", font_size)
    label = text.upper()
    bb = draw.textbbox((0, 0), label, font=fnt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = 18, 9
    w, h = tw + pad_x * 2, th + pad_y * 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=bg, outline=border, width=2 if border else 0)
    draw.text((x + pad_x, y + pad_y - 2), label, font=fnt, fill=fg)
    return x + w


def draw_editorial_card(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    title: str,
    body: Optional[str] = None,
    bg: Tuple[int, int, int, int] = WHITE,
    border: Tuple[int, int, int, int] = BORDER_BLUE,
    accent: Tuple[int, int, int, int] = ROYAL_BLUE,
    title_color: Tuple[int, int, int, int] = DEEP_NAVY,
    body_color: Tuple[int, int, int, int] = DARK_CHARCOAL,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle([x1, y1, x2, y2], radius=18, fill=bg, outline=border, width=2)
    draw.rounded_rectangle([x1 + 20, y1 + 20, x1 + 56, y1 + 26], radius=3, fill=accent)

    max_w = (x2 - x1) - 44
    tf, tlines = fit_headline(draw, title, "poppins_semibold", max_w, 2, 22, 16)
    ty = y1 + 40
    for ln in tlines:
        draw.text((x1 + 22, ty), ln, font=tf, fill=title_color)
        ty += int(tf.size * 1.25)

    if body:
        ty += 6
        bf, blines = fit_headline(draw, body, "inter_regular", max_w, 3, 17, 14)
        for ln in blines:
            draw.text((x1 + 22, ty), ln, font=bf, fill=body_color)
            ty += int(bf.size * 1.35)


def draw_dot_accent(draw: ImageDraw.ImageDraw, x: int, y: int, cols: int, rows: int, color: Tuple[int, int, int, int], step: int = 18) -> None:
    for c in range(cols):
        for r in range(rows):
            dx, dy = x + c * step, y + r * step
            draw.ellipse([dx - 2, dy - 2, dx + 2, dy + 2], fill=color)


def _service_tag(service_category: Optional[str]) -> str:
    p = get_pillar_by_name(service_category or "")
    return p["name"] if p else (service_category or "Technology Solutions")


# ==============================================================================
# 4. EIGHT CREATIVE DIRECTIONS
# ==============================================================================

def _render_editorial_collage(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """A. Editorial Collage — Asymmetrical grid, Playfair/Poppins pairing, arch photo, floating card."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)
    margin = 64

    # Soft Ice Blue asymmetrical background block on right
    draw.rectangle([w // 2 - 40, 0, w, h - 120], fill=ICE_BLUE)
    draw_dot_accent(draw, w - 150, 56, 5, 4, LIGHT_BLUE, step=18)

    # Header
    draw_logo_mark(img, draw, x=margin, y=48, on_dark=False)
    draw_label_badge(draw, x=margin, y=132, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    # Left column: Oversized mixed editorial headline (Playfair + Poppins)
    hf, hlines = fit_headline(draw, headline, "playfair_bold", max_width=520, max_lines=4, start_size=58, min_size=36)
    ty = 200
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.16)

    ty += 22
    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=490, max_lines=3, start_size=22, min_size=17)
    for ln in slines:
        draw.text((margin, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.38)

    # Right column: Arch-masked human photo
    photo_box = (w // 2 + 10, 140, w - margin, h - 290)
    draw_masked_photo(img, photo_path, photo_box, mask_type="arch")

    # Floating Royal Blue editorial card overlapping bottom-left/center
    pts = key_points[:2] or ["Built around real workflows", "Reliable everyday performance"]
    card_top = h - 340
    draw.rounded_rectangle([margin, card_top, w // 2 + 140, h - 110], radius=20, fill=DEEP_NAVY)
    draw.text((margin + 28, card_top + 26), "KEY FOCUS", font=get_brand_font("space_bold", 14), fill=LIGHT_BLUE)
    cy = card_top + 60
    for pt in pts:
        pf, pl = fit_headline(draw, f"•  {pt}", "poppins_semibold", (w // 2 + 140 - margin) - 56, 2, 21, 16)
        for ln in pl:
            draw.text((margin + 28, cy), ln, font=pf, fill=WHITE)
            cy += int(pf.size * 1.3)
        cy += 8

    # Bottom footer strip
    draw.text((margin, h - 68), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_human_centric_campaign(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """B. Human-Centric Campaign — Large hero photo + crisp Royal Blue/White editorial overlay."""
    w, h = size
    img = Image.new("RGBA", size, SOFT_GREY)
    draw = ImageDraw.Draw(img)

    # Large hero photograph occupying top 62%
    hero_h = int(h * 0.62)
    draw_masked_photo(img, photo_path, (0, 0, w, hero_h), mask_type="rect")

    # Top-left floating white brand pill
    draw.rounded_rectangle([48, 44, 330, 118], radius=16, fill=WHITE)
    draw_logo_mark(img, draw, x=64, y=57, on_dark=False, scale=0.88)

    # Top-right Royal Blue service pill
    tag = _service_tag(service_category).upper()
    tf = get_brand_font("space_bold", 14)
    tw = draw.textbbox((0, 0), tag, font=tf)[2] + 36
    draw_label_badge(draw, x=w - 48 - tw, y=58, text=tag, bg=ROYAL_BLUE, fg=WHITE)

    # Clean overlapping white editorial panel at bottom
    panel_top = hero_h - 60
    draw.rounded_rectangle([48, panel_top, w - 48, h - 44], radius=26, fill=WHITE, outline=BORDER_BLUE, width=2)
    draw.rectangle([48, panel_top + 40, 62, panel_top + 150], fill=ROYAL_BLUE)

    hf, hlines = fit_headline(draw, headline, "poppins_bold", max_width=w - 170, max_lines=2, start_size=48, min_size=32)
    ty = panel_top + 42
    for ln in hlines:
        draw.text((92, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    ty += 16
    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=w - 170, max_lines=2, start_size=22, min_size=17)
    for ln in slines:
        draw.text((92, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.35)

    draw.line([(92, h - 108), (w - 92, h - 108)], fill=ICE_BLUE, width=2)
    draw.text((92, h - 88), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_semibold", 18), fill=ROYAL_BLUE)
    return img


def _render_bold_typography_poster(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """C. Bold Typography Poster — Royal Blue color block, oversized mixed fonts, circular portrait inset."""
    w, h = size
    img = Image.new("RGBA", size, ROYAL_BLUE)
    draw = ImageDraw.Draw(img)
    margin = 72

    # Crisp white editorial bottom band
    band_y = h - 250
    draw.rectangle([0, band_y, w, h], fill=WHITE)

    # Header
    draw_logo_mark(img, draw, x=margin, y=54, on_dark=True)
    draw_label_badge(draw, x=margin, y=144, text=_service_tag(service_category), bg=DEEP_NAVY, fg=LIGHT_BLUE)

    # Circular human portrait in top-right
    circle_sz = 230
    draw_masked_photo(
        img,
        photo_path,
        (w - margin - circle_sz, 54, w - margin, 54 + circle_sz),
        mask_type="circle",
        border_color=WHITE,
        border_width=6,
    )

    # Oversized Headline with selective italic emphasis on last word
    words = headline.strip().split()
    main_part = " ".join(words[:-1]) if len(words) > 2 else headline
    emph_word = words[-1] if len(words) > 2 else ""

    hf, hlines = fit_headline(draw, main_part, "poppins_bold", max_width=w - margin * 2 - 40, max_lines=3, start_size=70, min_size=42)
    ty = 260
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=WHITE)
        ty += int(hf.size * 1.12)

    if emph_word:
        ef = get_brand_font("playfair_italic", min(82, hf.size + 10))
        draw.text((margin, ty + 4), emph_word, font=ef, fill=ICE_BLUE)

    # Supporting copy in white bottom band
    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=w - margin * 2, max_lines=2, start_size=24, min_size=18)
    by = band_y + 42
    for ln in slines:
        draw.text((margin, by), ln, font=sf, fill=DARK_CHARCOAL)
        by += int(sf.size * 1.38)

    draw.text((margin, h - 68), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 19), fill=ROYAL_BLUE)
    return img


def _render_split_editorial(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """D. Split Editorial Layout — Left full-height human photo, Right large typography & points."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)

    split_x = int(w * 0.44)
    draw_masked_photo(img, photo_path, (0, 0, split_x, h), mask_type="rect")

    # Subtle Royal Blue vertical accent divider
    draw.rectangle([split_x, 0, split_x + 10, h], fill=ROYAL_BLUE)

    rx = split_x + 56
    rmax = w - rx - 56

    draw_logo_mark(img, draw, x=rx, y=56, on_dark=False, scale=0.92)
    draw_label_badge(draw, x=rx, y=148, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE)

    hf, hlines = fit_headline(draw, headline, "playfair_bold", max_width=rmax, max_lines=4, start_size=52, min_size=34)
    ty = 224
    for ln in hlines:
        draw.text((rx, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    ty += 20
    draw.rectangle([rx, ty, rx + 72, ty + 5], fill=ROYAL_BLUE)
    ty += 28

    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=rmax, max_lines=3, start_size=21, min_size=16)
    for ln in slines:
        draw.text((rx, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.38)

    # Optional 2 concise takeaways
    pts = key_points[:2]
    if pts:
        ty += 24
        for pt in pts:
            draw.rounded_rectangle([rx, ty, w - 56, ty + 76], radius=12, fill=SOFT_GREY, outline=BORDER_BLUE, width=1)
            pf, pl = fit_headline(draw, pt, "poppins_semibold", rmax - 36, 2, 18, 15)
            py = ty + (76 - len(pl) * int(pf.size * 1.25)) // 2
            for ln in pl:
                draw.text((rx + 18, py), ln, font=pf, fill=DEEP_NAVY)
                py += int(pf.size * 1.25)
            ty += 90

    draw.text((rx, h - 68), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_business_metrics(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
    verified_metrics: Optional[List[Tuple[str, str]]] = None,
) -> Image.Image:
    """E. Business Metrics Creative — Metric/highlight cards + human photo (zero invented stats)."""
    w, h = size
    img = Image.new("RGBA", size, ICE_BLUE)
    draw = ImageDraw.Draw(img)
    margin = 64

    draw_logo_mark(img, draw, x=margin, y=48, on_dark=False)
    draw_label_badge(draw, x=margin, y=132, text=_service_tag(service_category), bg=WHITE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    # Human photo card top-right
    draw_masked_photo(img, photo_path, (w - margin - 260, 48, w - margin, 268), mask_type="rounded", radius=22, border_color=WHITE, border_width=4)

    hf, hlines = fit_headline(draw, headline, "poppins_bold", max_width=w - margin * 2 - 290, max_lines=3, start_size=48, min_size=32)
    ty = 192
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    # Cards area (uses ONLY explicitly supplied verified_metrics, or qualitative highlight cards)
    cards_top = max(ty + 44, 340)
    if verified_metrics:
        items = [(val, lbl) for val, lbl in verified_metrics[:3]]
    else:
        pts = key_points[:3] or ["Centralized Operations", "Zero Manual Re-entry", "Built Around Your Team"]
        items = [(f"0{i + 1}", pt) for i, pt in enumerate(pts)]

    card_w = (w - margin * 2 - 24 * (len(items) - 1)) // len(items)
    card_h = 340
    for idx, (big_val, label) in enumerate(items):
        cx = margin + idx * (card_w + 24)
        is_mid = (idx == 1)
        bg = ROYAL_BLUE if is_mid else WHITE
        val_col = WHITE if is_mid else ROYAL_BLUE
        lbl_col = ICE_BLUE if is_mid else DEEP_NAVY
        draw.rounded_rectangle([cx, cards_top, cx + card_w, cards_top + card_h], radius=22, fill=bg, outline=BORDER_BLUE if not is_mid else None, width=2)
        vf = get_brand_font("space_bold", 54)
        draw.text((cx + 28, cards_top + 42), big_val, font=vf, fill=val_col)
        lf, llines = fit_headline(draw, label, "poppins_semibold", card_w - 56, 3, 24, 17)
        ly = cards_top + 148
        for ln in llines:
            draw.text((cx + 28, ly), ln, font=lf, fill=lbl_col)
            ly += int(lf.size * 1.3)

    # Supporting explanation card at bottom (vertically centered)
    bot_y = cards_top + card_h + 32
    bot_h = h - 104
    draw.rounded_rectangle([margin, bot_y, w - margin, bot_h], radius=18, fill=WHITE)
    sf, slines = fit_headline(draw, subheadline, "inter_regular", w - margin * 2 - 64, 3, 24, 18)
    total_sh = len(slines) * int(sf.size * 1.35)
    sy = bot_y + max(24, (bot_h - bot_y - total_sh) // 2)
    for ln in slines:
        draw.text((margin + 32, sy), ln, font=sf, fill=DARK_CHARCOAL)
        sy += int(sf.size * 1.35)

    draw.text((margin, h - 68), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_creative_service_showcase(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """F. Creative Service Showcase — Deep Navy & White showcase with human photo & 3 capabilities."""
    w, h = size
    img = Image.new("RGBA", size, DEEP_NAVY)
    draw = ImageDraw.Draw(img)
    margin = 64

    # Header
    draw_logo_mark(img, draw, x=margin, y=48, on_dark=True)
    draw_label_badge(draw, x=margin, y=132, text=_service_tag(service_category), bg=ROYAL_BLUE, fg=WHITE)

    # Human photo right panel
    photo_box = (w // 2 + 40, 132, w - margin, 520)
    draw_masked_photo(img, photo_path, photo_box, mask_type="rounded", radius=24, border_color=LIGHT_BLUE, border_width=3)

    # Left service headline
    hf, hlines = fit_headline(draw, headline, "poppins_bold", max_width=w // 2 - 48, max_lines=4, start_size=48, min_size=32)
    ty = 200
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=WHITE)
        ty += int(hf.size * 1.18)

    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=w // 2 - 48, max_lines=3, start_size=20, min_size=16)
    ty += 16
    for ln in slines:
        draw.text((margin, ty), ln, font=sf, fill=LIGHT_BLUE)
        ty += int(sf.size * 1.35)

    # 3 Capability Cards across bottom
    pillar = get_pillar_by_name(service_category or "")
    feats = (key_points or (pillar.get("capabilities", []) if pillar else []))[:3]
    if not feats:
        feats = ["Custom Business Architecture", "Seamless System Integration", "Dedicated Ongoing Support"]

    cards_y = 600
    card_h = min(320, h - cards_y - 140)
    card_w = (w - margin * 2 - 40) // 3
    for i, feat in enumerate(feats):
        cx = margin + i * (card_w + 20)
        draw_editorial_card(
            draw,
            (cx, cards_y, cx + card_w, cards_y + card_h),
            title=feat,
            body=f"Capability 0{i + 1}",
            bg=WHITE,
            border=LIGHT_BLUE,
            accent=ROYAL_BLUE,
        )

    draw.text((margin, h - 68), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=LIGHT_BLUE)
    return img


def _render_visual_storytelling(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
    problem_points: Optional[List[str]] = None,
    solution_points: Optional[List[str]] = None,
) -> Image.Image:
    """G. Visual Storytelling — Problem vs Solution human-centered comparison."""
    w, h = size
    img = Image.new("RGBA", size, SOFT_GREY)
    draw = ImageDraw.Draw(img)
    margin = 60

    draw_logo_mark(img, draw, x=margin, y=44, on_dark=False)
    draw_label_badge(draw, x=margin, y=124, text=_service_tag(service_category), bg=WHITE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    # Human photo circular badge top-right
    draw_masked_photo(img, photo_path, (w - margin - 170, 40, w - margin, 210), mask_type="circle", border_color=ROYAL_BLUE, border_width=4)

    hf, hlines = fit_headline(draw, headline, "playfair_bold", max_width=w - margin * 2 - 200, max_lines=2, start_size=46, min_size=30)
    ty = 186
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    probs = (problem_points or key_points[:2] or ["Manual spreadsheet handoffs", "Missed follow-ups & delays"])[:2]
    sols = (solution_points or key_points[2:4] or ["Centralized digital workflow", "Clear team-wide visibility"])[:2]

    top_y = max(ty + 36, 330)
    bot_y = h - 108
    col_w = (w - margin * 2 - 28) // 2

    # Before Card (White / Soft Grey)
    draw.rounded_rectangle([margin, top_y, margin + col_w, bot_y], radius=22, fill=WHITE, outline=BORDER_BLUE, width=2)
    draw_label_badge(draw, margin + 28, top_y + 28, "BEFORE · THE FRICTION", bg=SOFT_GREY, fg=MUTED_SLATE)
    for i, ptxt in enumerate(probs):
        py = top_y + 100 + i * ((bot_y - top_y - 120) // 2)
        pf, pl = fit_headline(draw, ptxt, "poppins_semibold", col_w - 56, 3, 24, 17)
        for ln in pl:
            draw.text((margin + 28, py), ln, font=pf, fill=DARK_CHARCOAL)
            py += int(pf.size * 1.3)

    # After Card (Royal Blue)
    rx = margin + col_w + 28
    draw.rounded_rectangle([rx, top_y, rx + col_w, bot_y], radius=22, fill=ROYAL_BLUE)
    draw_label_badge(draw, rx + 28, top_y + 28, "AFTER · WITH JEEVYAM", bg=DEEP_NAVY, fg=WHITE)
    for i, stxt in enumerate(sols):
        sy = top_y + 100 + i * ((bot_y - top_y - 120) // 2)
        sf, sl = fit_headline(draw, stxt, "poppins_semibold", col_w - 56, 3, 24, 17)
        for ln in sl:
            draw.text((rx + 28, sy), ln, font=sf, fill=WHITE)
            sy += int(sf.size * 1.3)

    draw.text((margin, h - 66), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_multi_panel_agency(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
    secondary_photo_path: Optional[Path] = None,
) -> Image.Image:
    """H. Multi-Panel Agency Creative — Dual human photos, blue center block, editorial art direction."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)
    margin = 56

    draw_logo_mark(img, draw, x=margin, y=44, on_dark=False)
    draw_label_badge(draw, x=w - margin - 260, y=52, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE)

    # Top row: 2 photographic panels
    p_top = 136
    p_h = int(h * 0.32)
    half_w = (w - margin * 2 - 20) // 2
    draw_masked_photo(img, photo_path, (margin, p_top, margin + half_w, p_top + p_h), mask_type="rounded", radius=20)
    draw_masked_photo(img, secondary_photo_path or photo_path, (margin + half_w + 20, p_top, w - margin, p_top + p_h), mask_type="rounded", radius=20)

    # Center Royal Blue typography block (vertically balanced)
    mid_top = p_top + p_h + 24
    mid_bot = h - 220
    draw.rounded_rectangle([margin, mid_top, w - margin, mid_bot], radius=24, fill=ROYAL_BLUE)

    hf, hlines = fit_headline(draw, headline, "playfair_bold", max_width=w - margin * 2 - 72, max_lines=3, start_size=54, min_size=34)
    sf, slines = fit_headline(draw, subheadline, "inter_regular", max_width=w - margin * 2 - 72, max_lines=2, start_size=23, min_size=17)
    block_content_h = len(hlines) * int(hf.size * 1.18) + 18 + len(slines) * int(sf.size * 1.35)
    ty = mid_top + max(32, (mid_bot - mid_top - block_content_h) // 2)
    for ln in hlines:
        draw.text((margin + 36, ty), ln, font=hf, fill=WHITE)
        ty += int(hf.size * 1.18)

    ty += 18
    for ln in slines:
        draw.text((margin + 36, ty), ln, font=sf, fill=ICE_BLUE)
        ty += int(sf.size * 1.35)

    # Bottom white takeaway strip
    pts = key_points[:2] or ["Tailored for your business workflow", "Zero generic templates"]
    bot_top = mid_bot + 20
    for idx, pt in enumerate(pts):
        bx = margin + idx * (half_w + 20)
        draw.rounded_rectangle([bx, bot_top, bx + half_w, h - 92], radius=16, fill=ICE_BLUE, outline=BORDER_BLUE, width=1)
        pf, pl = fit_headline(draw, pt, "poppins_semibold", half_w - 40, 2, 19, 15)
        py = bot_top + 22
        for ln in pl:
            draw.text((bx + 20, py), ln, font=pf, fill=DEEP_NAVY)
            py += int(pf.size * 1.25)

    draw.text((margin, h - 62), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_diagonal_slice(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """I. Diagonal Slice — Bold diagonal Royal Blue color block + overlapping human portrait."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)
    margin = 64

    # Diagonal Royal Blue polygon on right/bottom
    draw.polygon([(int(w * 0.48), 0), (w, 0), (w, h), (int(w * 0.22), h)], fill=ROYAL_BLUE)
    draw_dot_accent(draw, w - 140, h - 120, 4, 3, LIGHT_BLUE, step=18)

    draw_logo_mark(img, draw, x=margin, y=48, on_dark=False)
    draw_label_badge(draw, x=margin, y=132, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    # Human photo in large rounded frame on right
    p_box = (int(w * 0.46), 140, w - margin, int(h * 0.68))
    draw_masked_photo(img, photo_path, p_box, mask_type="rounded", radius=28, border_color=WHITE, border_width=6)

    # Editorial card on bottom-left overlapping diagonal edge
    card_top = int(h * 0.42)
    card_w = int(w * 0.56)
    draw.rounded_rectangle([margin, card_top, margin + card_w, h - 108], radius=24, fill=DEEP_NAVY)

    hf, hlines = fit_headline(draw, headline, "space_bold", card_w - 64, 4, 46, 30)
    ty = card_top + 40
    for ln in hlines:
        draw.text((margin + 32, ty), ln, font=hf, fill=WHITE)
        ty += int(hf.size * 1.18)

    ty += 18
    sf, slines = fit_headline(draw, subheadline, "inter_regular", card_w - 64, 3, 21, 16)
    for ln in slines:
        draw.text((margin + 32, ty), ln, font=sf, fill=LIGHT_BLUE)
        ty += int(sf.size * 1.38)

    draw.text((margin, h - 64), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=DEEP_NAVY)
    return img


def _render_magazine_quote(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """J. Magazine Editorial Quote — Ice Blue canvas, oversized Playfair quote, circular human portrait."""
    w, h = size
    img = Image.new("RGBA", size, ICE_BLUE)
    draw = ImageDraw.Draw(img)
    margin = 76

    # Top bar
    draw_logo_mark(img, draw, x=margin, y=54, on_dark=False)
    draw_label_badge(draw, x=margin, y=144, text=_service_tag(service_category), bg=WHITE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    # Oversized decorative quotation mark
    draw.text((margin - 8, 210), "“", font=get_brand_font("playfair_italic", 170), fill=LIGHT_BLUE)

    hf, hlines = fit_headline(draw, headline, "playfair_bold", w - margin * 2, 4, 56, 34)
    ty = 315
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.2)

    ty += 24
    sf, slines = fit_headline(draw, subheadline, "inter_regular", w - margin * 2, 3, 24, 18)
    for ln in slines:
        draw.text((margin, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.38)

    # Bottom attribution strip with circular human portrait
    strip_y = h - 250
    draw.rounded_rectangle([margin, strip_y, w - margin, h - 76], radius=24, fill=WHITE, outline=BORDER_BLUE, width=2)
    draw_masked_photo(img, photo_path, (margin + 24, strip_y + 24, margin + 150, strip_y + 150), mask_type="circle", border_color=ROYAL_BLUE, border_width=3)
    draw.text((margin + 178, strip_y + 48), "Jeevyam Technologies Advisory", font=get_brand_font("poppins_bold", 22), fill=DEEP_NAVY)
    draw.text((margin + 178, strip_y + 84), f"{_service_tag(service_category)}  ·  {cta_text or 'jeevyamtechnologies.com'}", font=get_brand_font("inter_regular", 18), fill=ROYAL_BLUE)
    return img


def _render_timeline_blueprint(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """K. Timeline Blueprint — 3-step horizontal/vertical roadmap with human workspace photo."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)
    margin = 64

    draw_logo_mark(img, draw, x=margin, y=48, on_dark=False)
    draw_label_badge(draw, x=margin, y=130, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE)

    # Human workspace photo top-right
    draw_masked_photo(img, photo_path, (w - margin - 260, 48, w - margin, 260), mask_type="rounded", radius=20, border_color=BORDER_BLUE, border_width=2)

    hf, hlines = fit_headline(draw, headline, "poppins_bold", w - margin * 2 - 290, 3, 46, 30)
    ty = 190
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    steps = (key_points or ["Audit current operational bottlenecks", "Deploy tailored system architecture", "Automate reporting & daily alerts"])[:3]
    top_y = max(ty + 44, 340)
    bot_y = h - 120
    gap = 24
    step_h = (bot_y - top_y - gap * (len(steps) - 1)) // len(steps)

    spine_x = margin + 36
    draw.line([(spine_x, top_y + 36), (spine_x, bot_y - 36)], fill=LIGHT_BLUE, width=4)

    for idx, stxt in enumerate(steps):
        sy = top_y + idx * (step_h + gap)
        cy = sy + step_h // 2
        draw.ellipse([spine_x - 30, cy - 30, spine_x + 30, cy + 30], fill=ROYAL_BLUE if idx != 1 else DEEP_NAVY)
        nf = get_brand_font("space_bold", 22)
        draw.text((spine_x - 13, cy - 13), f"0{idx + 1}", font=nf, fill=WHITE)

        draw.rounded_rectangle([margin + 88, sy, w - margin, sy + step_h], radius=18, fill=SOFT_GREY, outline=BORDER_BLUE, width=1)
        sf, slines = fit_headline(draw, stxt, "poppins_semibold", w - margin * 2 - 136, 2, 24, 17)
        text_y = sy + (step_h - len(slines) * int(sf.size * 1.25)) // 2
        for ln in slines:
            draw.text((margin + 116, text_y), ln, font=sf, fill=DEEP_NAVY)
            text_y += int(sf.size * 1.25)

    draw.text((margin, h - 66), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


def _render_floating_frame_hero(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """L. Floating Frame Hero — Deep Navy canvas, tall human photo right, crisp white floating card left."""
    w, h = size
    img = Image.new("RGBA", size, DEEP_NAVY)
    draw = ImageDraw.Draw(img)
    margin = 56

    draw_logo_mark(img, draw, x=margin, y=46, on_dark=True)

    # Tall human photo on right half
    photo_box = (int(w * 0.45), 118, w - margin, h - 108)
    draw_masked_photo(img, photo_path, photo_box, mask_type="rounded", radius=26, border_color=ROYAL_BLUE, border_width=3)

    # Floating crisp white editorial card overlapping left-center
    card_top = int(h * 0.22)
    card_bot = h - 140
    card_right = int(w * 0.62)
    draw.rounded_rectangle([margin, card_top, card_right, card_bot], radius=24, fill=WHITE)
    draw_label_badge(draw, margin + 36, card_top + 36, _service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE)

    hf, hlines = fit_headline(draw, headline, "playfair_bold", (card_right - margin) - 72, 4, 48, 30)
    ty = card_top + 104
    for ln in hlines:
        draw.text((margin + 36, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    ty += 18
    sf, slines = fit_headline(draw, subheadline, "inter_regular", (card_right - margin) - 72, 3, 21, 16)
    for ln in slines:
        draw.text((margin + 36, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.38)

    draw_label_badge(draw, margin + 36, card_bot - 78, cta_text or "jeevyamtechnologies.com", bg=ROYAL_BLUE, fg=WHITE, font_size=15)
    return img


def _render_landscape_banner(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """M. Landscape Banner (1200x628) — Wide LinkedIn horizontal editorial banner."""
    w, h = size
    img = Image.new("RGBA", size, WHITE)
    draw = ImageDraw.Draw(img)
    margin = 52

    split_x = int(w * 0.57)
    draw_masked_photo(img, photo_path, (split_x, 0, w, h), mask_type="rect")
    draw.rectangle([split_x - 8, 0, split_x, h], fill=ROYAL_BLUE)

    draw_logo_mark(img, draw, x=margin, y=40, on_dark=False, scale=0.88)
    draw_label_badge(draw, x=margin, y=114, text=_service_tag(service_category), bg=ICE_BLUE, fg=ROYAL_BLUE, font_size=13)

    hf, hlines = fit_headline(draw, headline, "poppins_bold", split_x - margin - 44, 3, 42, 28)
    ty = 176
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    ty += 14
    sf, slines = fit_headline(draw, subheadline, "inter_regular", split_x - margin - 44, 2, 19, 15)
    for ln in slines:
        draw.text((margin, ty), ln, font=sf, fill=DARK_CHARCOAL)
        ty += int(sf.size * 1.35)

    draw.text((margin, h - 56), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 17), fill=ROYAL_BLUE)
    return img


def _render_checklist_card(
    headline: str,
    subheadline: str,
    key_points: List[str],
    service_category: Optional[str],
    cta_text: str,
    size: Tuple[int, int],
    photo_path: Optional[Path],
) -> Image.Image:
    """N. Checklist Card — Ice Blue canvas, crisp White checklist sheet, overlapping circular human portrait."""
    w, h = size
    img = Image.new("RGBA", size, ICE_BLUE)
    draw = ImageDraw.Draw(img)
    margin = 64

    draw_logo_mark(img, draw, x=margin, y=48, on_dark=False)
    draw_label_badge(draw, x=margin, y=130, text=_service_tag(service_category), bg=WHITE, fg=ROYAL_BLUE, border=BORDER_BLUE)

    hf, hlines = fit_headline(draw, headline, "poppins_bold", w - margin * 2 - 220, 3, 46, 30)
    ty = 190
    for ln in hlines:
        draw.text((margin, ty), ln, font=hf, fill=DEEP_NAVY)
        ty += int(hf.size * 1.18)

    # White checklist sheet
    sheet_top = max(ty + 36, 330)
    sheet_bot = h - 108
    draw.rounded_rectangle([margin, sheet_top, w - margin, sheet_bot], radius=24, fill=WHITE, outline=BORDER_BLUE, width=2)

    # Overlapping circular human portrait top-right
    draw_masked_photo(img, photo_path, (w - margin - 210, 44, w - margin, 254), mask_type="circle", border_color=WHITE, border_width=6)

    items = (key_points or ["Audit manual workflows", "Centralize team records", "Automate routine follow-ups"])[:4]
    slot_h = (sheet_bot - sheet_top - 48) // len(items)
    for idx, item in enumerate(items):
        iy = sheet_top + 24 + idx * slot_h
        cy = iy + slot_h // 2
        # Royal Blue circle checkmark
        draw.ellipse([margin + 32, cy - 20, margin + 72, cy + 20], fill=ROYAL_BLUE)
        draw.line([(margin + 43, cy), (margin + 50, cy + 8), (margin + 62, cy - 7)], fill=WHITE, width=3)

        if idx > 0:
            draw.line([(margin + 32, iy), (w - margin - 32, iy)], fill=SOFT_GREY, width=2)

        cf, clines = fit_headline(draw, item, "poppins_semibold", w - margin * 2 - 130, 2, 24, 17)
        text_y = cy - (len(clines) * int(cf.size * 1.25)) // 2
        for ln in clines:
            draw.text((margin + 96, text_y), ln, font=cf, fill=DEEP_NAVY)
            text_y += int(cf.size * 1.25)

    draw.text((margin, h - 66), cta_text or "jeevyamtechnologies.com", font=get_brand_font("poppins_bold", 18), fill=ROYAL_BLUE)
    return img


# ==============================================================================
# 5. DESIGN QUALITY VALIDATION GATE
# ==============================================================================

_UNSUPPORTED_STAT_RE = re.compile(
    r"\b(\d{2,3}%\s+(?:increase|boost|growth|faster|more|higher|roi|retention)|"
    r"\d+\+?\s+years\s+of\s+experience|\d+\+?\s+projects\s+delivered)\b",
    re.IGNORECASE,
)


class DesignQualityReport(BaseModel):
    """Validation report for a generated Design System 2.0 creative."""

    passed: bool = Field(...)
    direction: str = Field(...)
    dimensions: Tuple[int, int] = Field(...)
    human_photo_used: bool = Field(...)
    issues: List[str] = Field(default_factory=list)


def validate_design_quality(
    direction: str,
    headline: str,
    subheadline: str,
    size: Tuple[int, int],
    human_photo_used: bool,
    verified_metrics: Optional[List[Tuple[str, str]]] = None,
) -> DesignQualityReport:
    """Verify design quality rules before accepting a creative."""
    issues: List[str] = []
    if direction not in DESIGN_DIRECTIONS:
        issues.append(f"Unknown design direction '{direction}'.")
    if size not in (SQUARE_SIZE, PORTRAIT_SIZE, LANDSCAPE_SIZE):
        issues.append(f"Unsupported creative dimensions {size}; expected {SQUARE_SIZE}, {PORTRAIT_SIZE}, or {LANDSCAPE_SIZE}.")
    if not headline or len(headline.strip()) < 6:
        issues.append("Headline is missing or too short.")
    if len(headline.split()) > 14:
        issues.append("Headline exceeds 14 words; keep image headlines concise (4-10 words).")
    if direction != "bold_typography_poster" and not human_photo_used:
        issues.append(f"Human photography is required for '{direction}' creative.")
    combined = f"{headline} {subheadline}"
    if not verified_metrics and _UNSUPPORTED_STAT_RE.search(combined):
        issues.append("Creative text contains unsupported statistics.")
    if not (_ASSETS_DIR / "mark_light.png").exists():
        issues.append("Official Jevyam logo asset missing.")

    return DesignQualityReport(
        passed=(len(issues) == 0),
        direction=direction,
        dimensions=size,
        human_photo_used=human_photo_used,
        issues=issues,
    )


# ==============================================================================
# 6. MASTER RENDER ENTRYPOINT
# ==============================================================================

def render_design_v2(
    direction: str,
    headline: str,
    subheadline: str = "",
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: str = "jeevyamtechnologies.com",
    format_type: str = "square",
    photo_path: Optional[Path] = None,
    problem_points: Optional[List[str]] = None,
    solution_points: Optional[List[str]] = None,
    verified_metrics: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[bytes, DesignQualityReport]:
    """Render a Design System 2.0 creative and return (png_bytes, DesignQualityReport)."""
    if format_type == "portrait":
        size = PORTRAIT_SIZE
    elif format_type == "landscape":
        size = LANDSCAPE_SIZE
    else:
        size = SQUARE_SIZE
    pts = [p for p in (key_points or []) if p]
    primary_photo = resolve_service_photo(service_category, photo_path=photo_path, secondary=False)
    secondary_photo = resolve_service_photo(service_category, photo_path=None, secondary=True)
    has_photo = primary_photo is not None and primary_photo.exists()

    if direction == "editorial_collage":
        img = _render_editorial_collage(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "human_centric_campaign":
        img = _render_human_centric_campaign(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "bold_typography_poster":
        img = _render_bold_typography_poster(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "split_editorial":
        img = _render_split_editorial(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "business_metrics":
        img = _render_business_metrics(headline, subheadline, pts, service_category, cta_text, size, primary_photo, verified_metrics=verified_metrics)
    elif direction == "creative_service_showcase":
        img = _render_creative_service_showcase(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "visual_storytelling":
        img = _render_visual_storytelling(headline, subheadline, pts, service_category, cta_text, size, primary_photo, problem_points=problem_points, solution_points=solution_points)
    elif direction == "multi_panel_agency":
        img = _render_multi_panel_agency(headline, subheadline, pts, service_category, cta_text, size, primary_photo, secondary_photo_path=secondary_photo)
    elif direction == "diagonal_slice":
        img = _render_diagonal_slice(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "magazine_quote":
        img = _render_magazine_quote(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "timeline_blueprint":
        img = _render_timeline_blueprint(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "floating_frame_hero":
        img = _render_floating_frame_hero(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "landscape_banner":
        img = _render_landscape_banner(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    elif direction == "checklist_card":
        img = _render_checklist_card(headline, subheadline, pts, service_category, cta_text, size, primary_photo)
    else:
        img = _render_editorial_collage(headline, subheadline, pts, service_category, cta_text, size, primary_photo)

    report = validate_design_quality(
        direction=direction if direction in DESIGN_DIRECTIONS else "editorial_collage",
        headline=headline,
        subheadline=subheadline,
        size=size,
        human_photo_used=has_photo,
        verified_metrics=verified_metrics,
    )

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue(), report


def select_alternating_v2_v3_layout(
    service_category: Optional[str] = None,
    post_id: Optional[str] = None,
    revision: int = 1,
    previous_layouts: Optional[List[str]] = None,
) -> str:
    """Alternate between Design System 2.0 (v2 diverse) and v3 (landscape_banner)."""
    v2_pool = [d for d in DESIGN_DIRECTIONS if d != "landscape_banner"]

    use_v3 = False
    if previous_layouts:
        last = previous_layouts[0]
        use_v3 = (last != "landscape_banner")
    else:
        seq = 1
        if post_id:
            m = re.search(r"(\d+)$", str(post_id).strip())
            if m:
                seq = int(m.group(1))
        use_v3 = ((seq + max(0, revision - 1)) % 2 == 0)

    if use_v3:
        return "landscape_banner"

    # Rotate cleanly across v2 directions using service + post sequence
    idx = 0
    if post_id:
        m = re.search(r"(\d+)$", str(post_id).strip())
        if m:
            idx += int(m.group(1))
    if service_category:
        idx += sum(ord(c) for c in service_category)
    idx += max(0, revision - 1)
    return v2_pool[idx % len(v2_pool)]

