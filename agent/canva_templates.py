"""Canva-style reusable creative template engine for Jevyam Technologies.

Produces agency-grade LinkedIn marketing creatives using Jevyam's official
brand identity (Deep Navy, Cobalt Blue, Electric Cyan, Clean Off-White),
crisp typography hierarchy, intentional whitespace, and zero-overlap text fitting.

Supports 6 reusable templates:
1. editorial_insight       (1200x1200)
2. problem_vs_solution     (1200x1200)
3. educational_infographic (1200x1200)
4. service_spotlight       (1200x1200)
5. linkedin_carousel       (1080x1350 multi-slide + 1200x1200 cover)
6. technical_architecture  (1200x1200)
"""

from io import BytesIO
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from agent.pillars import get_pillar_by_name

# ==============================================================================
# BRAND IDENTITY PALETTE & CONSTANTS
# ==============================================================================

SINGLE_SIZE = (1200, 1200)
CAROUSEL_SIZE = (1080, 1350)

# Core Brand Colors
NAVY_DEEP = (10, 17, 40, 255)         # #0A1128
NAVY_CARD = (17, 29, 62, 255)         # #111D3E
NAVY_BORDER = (34, 54, 102, 255)      # #223666

COBALT = (0, 102, 255, 255)           # #0066FF
CYAN = (0, 210, 255, 255)             # #00D2FF
SOFT_BLUE_BG = (239, 246, 255, 255)   # #EFF6FF
SOFT_BLUE_BORDER = (191, 219, 254, 255)

OFF_WHITE = (248, 250, 252, 255)      # #F8FAFC
PURE_WHITE = (255, 255, 255, 255)     # #FFFFFF
SLATE_100 = (241, 245, 249, 255)      # #F1F5F9
SLATE_200 = (226, 232, 240, 255)      # #E2E8F0
SLATE_500 = (100, 116, 139, 255)      # #64748B
SLATE_700 = (51, 65, 85, 255)         # #334155
SLATE_900 = (15, 23, 42, 255)         # #0F172A

PROBLEM_BG = (254, 242, 242, 255)     # #FEF2F2
PROBLEM_BORDER = (254, 202, 202, 255) # #FECACA
PROBLEM_ACCENT = (220, 38, 38, 255)   # #DC2626

SOLUTION_BG = (239, 246, 255, 255)    # #EFF6FF
SOLUTION_ACCENT = (0, 102, 255, 255)  # #0066FF

CANVA_TEMPLATES: List[str] = [
    "editorial_insight",
    "problem_vs_solution",
    "educational_infographic",
    "service_spotlight",
    "linkedin_carousel",
    "technical_architecture",
]

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_FONT_CACHE: Dict[Tuple[int, bool], Any] = {}


def _get_font(size: int, bold: bool = False) -> Any:
    """Load clean modern sans-serif font with cross-platform Windows/Linux support."""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    candidates = (
        [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
        ]
    )
    font = None
    for path in candidates:
        try:
            font = ImageFont.truetype(path, size=size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> List[str]:
    """Word-wrap text strictly within max_width pixels."""
    words = (text or "").strip().split()
    if not words:
        return []
    lines: List[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), cand, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int = 20,
    bold: bool = True,
) -> Tuple[Any, List[str]]:
    """Find largest font size between start_size and min_size that fits max_lines."""
    for sz in range(start_size, min_size - 1, -2):
        font = _get_font(sz, bold=bold)
        lines = _wrap_lines(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    font = _get_font(min_size, bold=bold)
    lines = _wrap_lines(draw, text, font, max_width)[:max_lines]
    if lines and len(lines) == max_lines:
        last = lines[-1]
        while len(last) > 3 and draw.textbbox((0, 0), last + "...", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        if last != lines[-1]:
            lines[-1] = last + "..."
    return font, lines


def _draw_official_logo(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    is_dark: bool,
    scale: float = 1.0,
) -> None:
    """Render Jevyam's official star mark + clean typography without background artifacts."""
    mark_h = int(56 * scale)
    mark_w = mark_h
    mark_file = "mark_dark.png" if is_dark else "mark_light.png"
    pasted = False

    for base_dir in (_ASSETS_DIR, Path("assets"), Path("../assets")):
        p = base_dir / mark_file
        if p.exists():
            try:
                raw = Image.open(p).convert("RGBA")
                # Clean near-transparent edge noise so no rectangular halo appears
                px = raw.getdata()
                cleaned = [
                    (r, g, b, 0 if a < 28 else a) for (r, g, b, a) in px
                ]
                raw.putdata(cleaned)
                mark_w = int(raw.width * (mark_h / raw.height))
                resized = raw.resize((mark_w, mark_h), Image.Resampling.LANCZOS)
                img.alpha_composite(resized, (x, y))
                pasted = True
                break
            except Exception:
                pass

    if not pasted:
        cx, cy = x + mark_h // 2, y + mark_h // 2
        r = mark_h // 2 - 4
        col = CYAN if is_dark else COBALT
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
        draw.line([(cx - r + 6, cy), (cx + r - 6, cy)], fill=col, width=3)
        draw.line([(cx, cy - r + 6), (cx, cy + r - 6)], fill=col, width=3)

    text_color = PURE_WHITE if is_dark else NAVY_DEEP
    sub_color = CYAN if is_dark else COBALT
    tx = x + mark_w + int(14 * scale)
    draw.text((tx, y + int(2 * scale)), "JEEVYAM", font=_get_font(int(26 * scale), bold=True), fill=text_color)
    draw.text((tx + 1, y + int(32 * scale)), "TECHNOLOGIES", font=_get_font(int(12 * scale), bold=True), fill=sub_color)


def _draw_vector_cross(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Tuple[int, int, int, int]) -> None:
    """Draw a crisp vector X icon (no font glyph dependency)."""
    draw.line([(cx - r, cy - r), (cx + r, cy + r)], fill=color, width=3)
    draw.line([(cx - r, cy + r), (cx + r, cy - r)], fill=color, width=3)


def _draw_vector_check(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: Tuple[int, int, int, int]) -> None:
    """Draw a crisp vector checkmark icon (no font glyph dependency)."""
    draw.line([(cx - r, cy), (cx - r // 4, cy + r - 2), (cx + r, cy - r + 2)], fill=color, width=3)


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    bg_color: Tuple[int, int, int, int],
    text_color: Tuple[int, int, int, int],
    border_color: Optional[Tuple[int, int, int, int]] = None,
    font_size: int = 16,
    pad_x: int = 20,
    pad_y: int = 10,
) -> int:
    """Draw a crisp rounded badge pill and return its right X coordinate."""
    font = _get_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=h // 2,
        fill=bg_color,
        outline=border_color,
        width=2 if border_color else 0,
    )
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=text_color)
    return x + w


def _draw_footer(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    cta_text: str,
    is_dark: bool,
    service_label: Optional[str] = None,
) -> None:
    """Consistent Canva-style bottom bar with logo/URL and subtle divider."""
    margin = 76
    line_y = height - 104
    line_col = NAVY_BORDER if is_dark else SLATE_200
    draw.line([(margin, line_y), (width - margin, line_y)], fill=line_col, width=2)

    url_col = CYAN if is_dark else COBALT
    muted_col = (148, 163, 184, 255) if is_dark else SLATE_500

    left_label = cta_text or "jeevyamtechnologies.com"
    draw.text((margin, height - 74), left_label, font=_get_font(20, bold=True), fill=url_col)

    right_label = service_label or "Jevyam Technologies Pvt. Ltd."
    font_r = _get_font(18, bold=False)
    rb = draw.textbbox((0, 0), right_label, font=font_r)
    draw.text((width - margin - (rb[2] - rb[0]), height - 72), right_label, font=font_r, fill=muted_col)


def _derive_points_from_caption(caption: Optional[str], limit: int = 3) -> List[str]:
    """Extract short, clean sentences from caption when explicit points aren't provided."""
    if not caption:
        return []
    # Prefer bullet lines first
    bullets = []
    for line in caption.splitlines():
        clean = line.strip()
        if clean.startswith(("•", "-", "*", "→")):
            item = clean.lstrip("•-*→ ").strip()
            if 10 <= len(item) <= 90:
                bullets.append(item)
    if bullets:
        return bullets[:limit]

    # Otherwise extract crisp sentences
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", caption.replace("\n", " "))
        if 20 <= len(s.strip()) <= 95 and "http" not in s.lower() and "#" not in s
    ]
    return sentences[:limit]


def _service_badge_text(service_category: Optional[str]) -> str:
    if not service_category:
        return "TECHNOLOGY SOLUTIONS"
    pillar = get_pillar_by_name(service_category)
    if pillar:
        return f"SERVICE {pillar['id']}  ·  {pillar['name'].upper()}"
    return service_category.upper()


# ==============================================================================
# TEMPLATE SELECTION
# ==============================================================================

def select_canva_template(
    service_category: Optional[str] = None,
    topic: Optional[str] = None,
    caption: Optional[str] = None,
    preferred_template: Optional[str] = None,
    previous_templates: Optional[List[str]] = None,
) -> str:
    """Dynamically select the best Canva template for the post's service & message."""
    if preferred_template and preferred_template in CANVA_TEMPLATES:
        return preferred_template

    text = f"{topic or ''} {caption or ''}".lower()
    svc = (service_category or "").lower()

    if any(k in text for k in (" vs ", "versus", "before", "after", "template", "spreadsheet", "problem")):
        candidate = "problem_vs_solution"
    elif any(k in text for k in ("step", "workflow", "how to", "checklist", "process", "pipeline", "automate")):
        candidate = "educational_infographic"
    elif any(k in text for k in ("architecture", "api", "database", "migration", "cloud", "infrastructure", "integration")):
        candidate = "technical_architecture"
    elif any(k in text for k in ("when does", "things to", "signs your", "guide", "ways to")):
        candidate = "linkedin_carousel"
    elif "crm" in svc or "inventory" in svc or "ai" in svc:
        candidate = "educational_infographic"
    elif "custom software" in svc or "it consultancy" in svc:
        candidate = "technical_architecture"
    elif "mobile" in svc:
        candidate = "service_spotlight"
    elif "website" in svc or "digital marketing" in svc:
        candidate = "editorial_insight"
    else:
        candidate = "editorial_insight"

    if previous_templates and candidate == previous_templates[0]:
        idx = CANVA_TEMPLATES.index(candidate)
        candidate = CANVA_TEMPLATES[(idx + 1) % len(CANVA_TEMPLATES)]

    return candidate


# ==============================================================================
# TEMPLATE 1: EDITORIAL INSIGHT (1200x1200)
# ==============================================================================

def render_editorial_insight(
    headline: str,
    subheadline: str,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, OFF_WHITE)
    draw = ImageDraw.Draw(img)
    margin = 76

    # Top accent bar
    draw.rectangle([0, 0, w, 12], fill=COBALT)

    # Header: Logo left, Service badge right
    _draw_official_logo(img, draw, x=margin, y=56, is_dark=False)
    badge = _service_badge_text(service_category)
    b_font = _get_font(14, bold=True)
    bw = draw.textbbox((0, 0), badge, font=b_font)[2] + 36
    _draw_pill(draw, x=w - margin - bw, y=64, text=badge, bg_color=SOFT_BLUE_BG, text_color=COBALT, border_color=SOFT_BLUE_BORDER, font_size=14, pad_x=18, pad_y=8)

    # Thin editorial divider
    draw.line([(margin, 144), (w - margin, 144)], fill=SLATE_200, width=2)

    # Bold Editorial Headline
    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=3, start_size=62, min_size=38, bold=True)
    y = 196
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=NAVY_DEEP)
        y += int(hl_font.size * 1.2)

    # Accent underline bar
    y += 20
    draw.rounded_rectangle([margin, y, margin + 120, y + 7], radius=3, fill=COBALT)
    y += 38

    # Supporting statement
    if subheadline:
        sub_font, sub_lines = _fit_text_block(draw, subheadline, max_width=w - margin * 2, max_lines=3, start_size=28, min_size=20, bold=False)
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=SLATE_700)
            y += int(sub_font.size * 1.38)
        y += 32

    # Key insight cards (clean minimal callouts)
    pts = [p for p in (key_points or []) if p][:3]
    if pts:
        avail_h = (h - 140) - y
        card_h = min(115, max(82, (avail_h - (len(pts) - 1) * 18) // len(pts)))
        for idx, pt in enumerate(pts):
            cy = y + idx * (card_h + 18)
            draw.rounded_rectangle([margin, cy, w - margin, cy + card_h], radius=14, fill=PURE_WHITE, outline=SLATE_200, width=2)
            draw.rounded_rectangle([margin, cy, margin + 8, cy + card_h], radius=4, fill=COBALT)
            pt_font, pt_lines = _fit_text_block(draw, pt, max_width=w - margin * 2 - 56, max_lines=2, start_size=23, min_size=17, bold=True)
            text_y = cy + (card_h - len(pt_lines) * int(pt_font.size * 1.25)) // 2
            for pl in pt_lines:
                draw.text((margin + 32, text_y), pl, font=pt_font, fill=NAVY_DEEP)
                text_y += int(pt_font.size * 1.25)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=False, service_label=service_category)
    return img


# ==============================================================================
# TEMPLATE 2: PROBLEM VS SOLUTION (1200x1200)
# ==============================================================================

def render_problem_vs_solution(
    headline: str,
    subheadline: str,
    problem_points: Optional[List[str]] = None,
    solution_points: Optional[List[str]] = None,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, OFF_WHITE)
    draw = ImageDraw.Draw(img)
    margin = 70

    # Header
    _draw_official_logo(img, draw, x=margin, y=52, is_dark=False)
    badge = _service_badge_text(service_category)
    bw = draw.textbbox((0, 0), badge, font=_get_font(14, bold=True))[2] + 36
    _draw_pill(draw, x=w - margin - bw, y=60, text=badge, bg_color=SOFT_BLUE_BG, text_color=COBALT, border_color=SOFT_BLUE_BORDER, font_size=14, pad_x=18, pad_y=8)

    # Headline
    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=2, start_size=50, min_size=34, bold=True)
    y = 148
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=NAVY_DEEP)
        y += int(hl_font.size * 1.2)

    if subheadline:
        sub_font, sub_lines = _fit_text_block(draw, subheadline, max_width=w - margin * 2, max_lines=2, start_size=22, min_size=18, bold=False)
        y += 8
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=SLATE_500)
            y += int(sub_font.size * 1.3)

    # Two-Column Comparison Cards
    col_top = max(y + 32, 310)
    col_bot = h - 132
    gap = 28
    col_w = (w - margin * 2 - gap) // 2
    left_x = margin
    right_x = margin + col_w + gap

    # Left Card: The Challenge
    draw.rounded_rectangle([left_x, col_top, left_x + col_w, col_bot], radius=20, fill=PURE_WHITE, outline=PROBLEM_BORDER, width=2)
    draw.rounded_rectangle([left_x + 24, col_top + 24, left_x + col_w - 24, col_top + 74], radius=12, fill=PROBLEM_BG)
    _draw_vector_cross(draw, cx=left_x + 52, cy=col_top + 49, r=7, color=PROBLEM_ACCENT)
    draw.text((left_x + 72, col_top + 37), "COMMON FRICTION", font=_get_font(18, bold=True), fill=PROBLEM_ACCENT)

    # Right Card: Jevyam Solution
    draw.rounded_rectangle([right_x, col_top, right_x + col_w, col_bot], radius=20, fill=NAVY_DEEP, outline=COBALT, width=2)
    draw.rounded_rectangle([right_x + 24, col_top + 24, right_x + col_w - 24, col_top + 74], radius=12, fill=NAVY_CARD)
    _draw_vector_check(draw, cx=right_x + 52, cy=col_top + 49, r=8, color=CYAN)
    draw.text((right_x + 72, col_top + 37), "JEVYAM APPROACH", font=_get_font(18, bold=True), fill=CYAN)

    probs = [p for p in (problem_points or []) if p][:3]
    sols = [s for s in (solution_points or []) if s][:3]
    if not probs and key_points:
        probs = key_points[:2]
    if not sols and key_points:
        sols = key_points[2:4] or key_points[:2]
    if not probs:
        probs = ["Manual, disconnected workflows", "Slow response and visibility gaps"]
    if not sols:
        sols = ["Purpose-built centralized system", "Reliable, automated daily execution"]

    def _draw_col_items(items: List[str], cx: int, is_sol: bool) -> None:
        item_top = col_top + 104
        avail = (col_bot - 24) - item_top
        slot_h = avail // max(1, len(items))
        for i, txt in enumerate(items):
            iy = item_top + i * slot_h
            box_bg = NAVY_CARD if is_sol else OFF_WHITE
            draw.rounded_rectangle([cx + 24, iy, cx + col_w - 24, iy + slot_h - 16], radius=12, fill=box_bg)
            fnt, lines = _fit_text_block(draw, txt, max_width=col_w - 84, max_lines=3, start_size=22, min_size=16, bold=True)
            ty = iy + (slot_h - 16 - len(lines) * int(fnt.size * 1.25)) // 2
            t_col = PURE_WHITE if is_sol else SLATE_900
            for ln in lines:
                draw.text((cx + 42, ty), ln, font=fnt, fill=t_col)
                ty += int(fnt.size * 1.25)

    _draw_col_items(probs, left_x, is_sol=False)
    _draw_col_items(sols, right_x, is_sol=True)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=False, service_label=service_category)
    return img


# ==============================================================================
# TEMPLATE 3: EDUCATIONAL INFOGRAPHIC (1200x1200)
# ==============================================================================

def render_educational_infographic(
    headline: str,
    subheadline: str,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, OFF_WHITE)
    draw = ImageDraw.Draw(img)
    margin = 72

    # Header
    _draw_official_logo(img, draw, x=margin, y=50, is_dark=False)
    badge = _service_badge_text(service_category)
    bw = draw.textbbox((0, 0), badge, font=_get_font(14, bold=True))[2] + 36
    _draw_pill(draw, x=w - margin - bw, y=58, text=badge, bg_color=SOFT_BLUE_BG, text_color=COBALT, border_color=SOFT_BLUE_BORDER, font_size=14, pad_x=18, pad_y=8)

    # Title block
    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=2, start_size=48, min_size=32, bold=True)
    y = 142
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=NAVY_DEEP)
        y += int(hl_font.size * 1.18)

    if subheadline:
        sub_font, sub_lines = _fit_text_block(draw, subheadline, max_width=w - margin * 2, max_lines=2, start_size=21, min_size=17, bold=False)
        y += 6
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=SLATE_500)
            y += int(sub_font.size * 1.28)

    # Numbered infographic steps
    steps = [s for s in (key_points or []) if s][:4]
    if not steps:
        steps = [
            "Audit current workflow bottlenecks",
            "Centralize records in one system",
            "Automate repetitive handoffs & alerts",
            "Track outcomes with clear reporting",
        ]

    steps_top = max(y + 28, 286)
    steps_bot = h - 130
    gap = 20
    step_h = (steps_bot - steps_top - gap * (len(steps) - 1)) // len(steps)

    # Vertical connector spine
    spine_x = margin + 44
    draw.line([(spine_x, steps_top + 40), (spine_x, steps_bot - 40)], fill=SOFT_BLUE_BORDER, width=4)

    for idx, step_text in enumerate(steps):
        sy = steps_top + idx * (step_h + gap)
        # Step card
        draw.rounded_rectangle([margin + 96, sy, w - margin, sy + step_h], radius=16, fill=PURE_WHITE, outline=SLATE_200, width=2)
        # Number circle on spine
        r = 34
        cy = sy + step_h // 2
        draw.ellipse([spine_x - r, cy - r, spine_x + r, cy + r], fill=COBALT if idx % 2 == 0 else NAVY_DEEP)
        num_str = f"0{idx + 1}"
        nf = _get_font(24, bold=True)
        nb = draw.textbbox((0, 0), num_str, font=nf)
        draw.text((spine_x - (nb[2] - nb[0]) // 2, cy - (nb[3] - nb[1]) // 2 - 4), num_str, font=nf, fill=PURE_WHITE)

        # Step text
        sf, slines = _fit_text_block(draw, step_text, max_width=w - margin * 2 - 148, max_lines=2, start_size=25, min_size=18, bold=True)
        ty = sy + (step_h - len(slines) * int(sf.size * 1.25)) // 2
        for sl in slines:
            draw.text((margin + 124, ty), sl, font=sf, fill=NAVY_DEEP)
            ty += int(sf.size * 1.25)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=False, service_label=service_category)
    return img


# ==============================================================================
# TEMPLATE 4: SERVICE SPOTLIGHT (1200x1200)
# ==============================================================================

def render_service_spotlight(
    headline: str,
    subheadline: str,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, NAVY_DEEP)
    draw = ImageDraw.Draw(img)
    margin = 76

    # Subtle geometric corner accent (clean, non-glowing)
    draw.rectangle([0, 0, w, 10], fill=CYAN)

    # Header
    _draw_official_logo(img, draw, x=margin, y=54, is_dark=True)
    badge = _service_badge_text(service_category)
    _draw_pill(draw, x=margin, y=156, text=badge, bg_color=NAVY_CARD, text_color=CYAN, border_color=COBALT, font_size=15, pad_x=20, pad_y=9)

    # Prominent Title
    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=3, start_size=56, min_size=36, bold=True)
    y = 228
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=PURE_WHITE)
        y += int(hl_font.size * 1.2)

    if subheadline:
        y += 14
        sub_font, sub_lines = _fit_text_block(draw, subheadline, max_width=w - margin * 2, max_lines=2, start_size=24, min_size=18, bold=False)
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=(203, 213, 225, 255))
            y += int(sub_font.size * 1.35)

    # Capability spotlight panel
    feats = [f for f in (key_points or []) if f][:3]
    if not feats:
        pillar = get_pillar_by_name(service_category or "")
        feats = (pillar.get("capabilities", [])[:3] if pillar else ["Tailored Engineering", "Clean Integration", "Ongoing Support"])

    panel_top = max(y + 36, 470)
    panel_bot = h - 148
    draw.rounded_rectangle([margin, panel_top, w - margin, panel_bot], radius=22, fill=NAVY_CARD, outline=NAVY_BORDER, width=2)

    row_h = (panel_bot - panel_top - 48) // max(1, len(feats))
    for i, feat in enumerate(feats):
        ry = panel_top + 24 + i * row_h
        if i > 0:
            draw.line([(margin + 32, ry - 4), (w - margin - 32, ry - 4)], fill=NAVY_BORDER, width=1)
        # Cyan check badge (vector)
        draw.rounded_rectangle([margin + 32, ry + (row_h - 40) // 2, margin + 72, ry + (row_h + 40) // 2], radius=10, fill=COBALT)
        _draw_vector_check(draw, cx=margin + 52, cy=ry + row_h // 2, r=9, color=PURE_WHITE)

        ff, flines = _fit_text_block(draw, feat, max_width=w - margin * 2 - 132, max_lines=2, start_size=24, min_size=17, bold=True)
        ty = ry + (row_h - len(flines) * int(ff.size * 1.25)) // 2
        for fl in flines:
            draw.text((margin + 96, ty), fl, font=ff, fill=PURE_WHITE)
            ty += int(ff.size * 1.25)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=True, service_label=service_category)
    return img


# ==============================================================================
# TEMPLATE 5: LINKEDIN CAROUSEL (1080x1350 slides + 1200x1200 cover)
# ==============================================================================

def render_carousel_slides(
    headline: str,
    subheadline: str,
    slides: Optional[List[Dict[str, str]]] = None,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
) -> List[bytes]:
    """Render a complete multi-slide 1080x1350 LinkedIn Carousel (Cover + Insights + CTA)."""
    w, h = CAROUSEL_SIZE
    margin = 76
    rendered_bytes: List[bytes] = []

    normalized_slides: List[Dict[str, str]] = []
    if slides:
        for s in slides[:4]:
            if isinstance(s, dict):
                normalized_slides.append({"title": s.get("title", ""), "body": s.get("body", "")})
            elif hasattr(s, "title"):
                normalized_slides.append({"title": s.title, "body": s.body})
    if not normalized_slides and key_points:
        for idx, kp in enumerate(key_points[:4], 1):
            normalized_slides.append({"title": f"Key Insight #{idx}", "body": kp})
    if not normalized_slides:
        normalized_slides = [
            {"title": "Identify the Bottleneck", "body": subheadline or "Pinpoint where manual handoffs slow down your daily operations."},
            {"title": "Centralize Your Workflow", "body": "Replace fragmented spreadsheets with one reliable source of truth."},
        ]

    total_slides = len(normalized_slides) + 2

    # --- Slide 1: Cover Slide (Dark Navy) ---
    cover = Image.new("RGBA", CAROUSEL_SIZE, NAVY_DEEP)
    cd = ImageDraw.Draw(cover)
    cd.rectangle([0, 0, w, 12], fill=CYAN)
    _draw_official_logo(cover, cd, x=margin, y=64, is_dark=True)
    _draw_pill(cd, x=margin, y=184, text=_service_badge_text(service_category), bg_color=NAVY_CARD, text_color=CYAN, border_color=COBALT, font_size=15)

    hl_f, hl_l = _fit_text_block(cd, headline, max_width=w - margin * 2, max_lines=4, start_size=64, min_size=40, bold=True)
    cy = 276
    for ln in hl_l:
        cd.text((margin, cy), ln, font=hl_f, fill=PURE_WHITE)
        cy += int(hl_f.size * 1.2)

    if subheadline:
        cy += 24
        sf, sl = _fit_text_block(cd, subheadline, max_width=w - margin * 2, max_lines=3, start_size=26, min_size=20, bold=False)
        for ln in sl:
            cd.text((margin, cy), ln, font=sf, fill=(203, 213, 225, 255))
            cy += int(sf.size * 1.38)

    _draw_pill(cd, x=margin, y=h - 210, text=f"SWIPE FOR {len(normalized_slides)} INSIGHTS  →", bg_color=COBALT, text_color=PURE_WHITE, font_size=18, pad_x=26, pad_y=14)
    _draw_footer(cover, cd, w, h, cta_text or "jeevyamtechnologies.com", is_dark=True, service_label=f"01 / {total_slides:02d}")
    rendered_bytes.append(_to_png_bytes(cover))

    # --- Insight Slides (Clean Off-White) ---
    for idx, sdata in enumerate(normalized_slides, 2):
        slide = Image.new("RGBA", CAROUSEL_SIZE, OFF_WHITE)
        sd = ImageDraw.Draw(slide)
        sd.rectangle([0, 0, w, 10], fill=COBALT)
        _draw_official_logo(slide, sd, x=margin, y=56, is_dark=False, scale=0.9)
        _draw_pill(sd, x=w - margin - 110, y=64, text=f"{idx:02d} / {total_slides:02d}", bg_color=SOFT_BLUE_BG, text_color=COBALT, border_color=SOFT_BLUE_BORDER, font_size=16)

        sd.text((margin, 210), f"0{idx - 1}", font=_get_font(92, bold=True), fill=SOFT_BLUE_BORDER)
        tf, tl = _fit_text_block(sd, sdata["title"], max_width=w - margin * 2, max_lines=3, start_size=48, min_size=32, bold=True)
        sy = 330
        for ln in tl:
            sd.text((margin, sy), ln, font=tf, fill=NAVY_DEEP)
            sy += int(tf.size * 1.22)

        sy += 24
        sd.rounded_rectangle([margin, sy, margin + 96, sy + 6], radius=3, fill=COBALT)
        sy += 36

        bf, bl = _fit_text_block(sd, sdata["body"], max_width=w - margin * 2, max_lines=6, start_size=30, min_size=22, bold=False)
        for ln in bl:
            sd.text((margin, sy), ln, font=bf, fill=SLATE_700)
            sy += int(bf.size * 1.42)

        _draw_footer(slide, sd, w, h, cta_text or "jeevyamtechnologies.com", is_dark=False, service_label=service_category)
        rendered_bytes.append(_to_png_bytes(slide))

    # --- Final CTA Slide (Deep Navy) ---
    cta_slide = Image.new("RGBA", CAROUSEL_SIZE, NAVY_DEEP)
    fd = ImageDraw.Draw(cta_slide)
    fd.rectangle([0, 0, w, 12], fill=CYAN)
    _draw_official_logo(cta_slide, fd, x=margin, y=64, is_dark=True)

    cf, cl = _fit_text_block(fd, f"Need help with {service_category or 'your software systems'}?", max_width=w - margin * 2, max_lines=3, start_size=54, min_size=36, bold=True)
    fy = 360
    for ln in cl:
        fd.text((margin, fy), ln, font=cf, fill=PURE_WHITE)
        fy += int(cf.size * 1.25)

    fy += 28
    sf, sl = _fit_text_block(fd, "Practical engineering, transparent scoping, and systems built around your operations.", max_width=w - margin * 2, max_lines=3, start_size=26, min_size=20, bold=False)
    for ln in sl:
        fd.text((margin, fy), ln, font=sf, fill=(203, 213, 225, 255))
        fy += int(sf.size * 1.4)

    _draw_pill(fd, x=margin, y=fy + 48, text=cta_text or "Visit jeevyamtechnologies.com", bg_color=COBALT, text_color=PURE_WHITE, font_size=22, pad_x=32, pad_y=16)
    _draw_footer(cta_slide, fd, w, h, "Jevyam Technologies Pvt. Ltd.", is_dark=True, service_label=f"{total_slides:02d} / {total_slides:02d}")
    rendered_bytes.append(_to_png_bytes(cta_slide))

    return rendered_bytes


def render_linkedin_carousel_cover(
    headline: str,
    subheadline: str,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    """1200x1200 LinkedIn Carousel-style stacked-card preview for single-image feeds."""
    w, h = size
    img = Image.new("RGBA", size, NAVY_DEEP)
    draw = ImageDraw.Draw(img)
    margin = 76

    draw.rectangle([0, 0, w, 10], fill=CYAN)
    _draw_official_logo(img, draw, x=margin, y=54, is_dark=True)
    _draw_pill(draw, x=w - margin - 210, y=62, text="INSIGHT SERIES  →", bg_color=NAVY_CARD, text_color=CYAN, border_color=COBALT, font_size=14)

    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=2, start_size=50, min_size=34, bold=True)
    y = 160
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=PURE_WHITE)
        y += int(hl_font.size * 1.2)

    pts = [p for p in (key_points or []) if p][:3]
    if not pts:
        pts = [subheadline or "Practical operational insights for growing teams", "Structured execution without software bloat", "Built around your actual business workflow"]

    # Stacked preview cards mimicking carousel deck
    card_top = max(y + 42, 330)
    card_h = 185
    for idx, pt in enumerate(pts):
        offset_x = idx * 18
        cy = card_top + idx * (card_h + 22)
        cx1 = margin + offset_x
        cx2 = w - margin - (len(pts) - 1 - idx) * 18
        bg = PURE_WHITE if idx == 0 else (SLATE_100 if idx == 1 else SOFT_BLUE_BG)
        draw.rounded_rectangle([cx1, cy, cx2, cy + card_h], radius=18, fill=bg, outline=COBALT, width=2)
        _draw_pill(draw, x=cx1 + 28, y=cy + 24, text=f"SLIDE 0{idx + 1}", bg_color=COBALT, text_color=PURE_WHITE, font_size=13, pad_x=14, pad_y=6)
        pf, pl = _fit_text_block(draw, pt, max_width=(cx2 - cx1) - 64, max_lines=2, start_size=26, min_size=18, bold=True)
        ty = cy + 78
        for ln in pl:
            draw.text((cx1 + 28, ty), ln, font=pf, fill=NAVY_DEEP)
            ty += int(pf.size * 1.28)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=True, service_label=service_category)
    return img


# ==============================================================================
# TEMPLATE 6: TECHNICAL ARCHITECTURE (1200x1200)
# ==============================================================================

def render_technical_architecture(
    headline: str,
    subheadline: str,
    architecture_nodes: Optional[List[str]] = None,
    key_points: Optional[List[str]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    size: Tuple[int, int] = SINGLE_SIZE,
) -> Image.Image:
    w, h = size
    img = Image.new("RGBA", size, OFF_WHITE)
    draw = ImageDraw.Draw(img)
    margin = 72

    # Clean blueprint dots (subtle, light)
    for gx in range(margin, w - margin + 1, 48):
        for gy in range(280, h - 140, 48):
            draw.ellipse([gx - 1, gy - 1, gx + 1, gy + 1], fill=SLATE_200)

    _draw_official_logo(img, draw, x=margin, y=50, is_dark=False)
    badge = _service_badge_text(service_category)
    bw = draw.textbbox((0, 0), badge, font=_get_font(14, bold=True))[2] + 36
    _draw_pill(draw, x=w - margin - bw, y=58, text=badge, bg_color=SOFT_BLUE_BG, text_color=COBALT, border_color=SOFT_BLUE_BORDER, font_size=14, pad_x=18, pad_y=8)

    hl_font, hl_lines = _fit_text_block(draw, headline, max_width=w - margin * 2, max_lines=2, start_size=46, min_size=32, bold=True)
    y = 142
    for line in hl_lines:
        draw.text((margin, y), line, font=hl_font, fill=NAVY_DEEP)
        y += int(hl_font.size * 1.18)

    if subheadline:
        sub_font, sub_lines = _fit_text_block(draw, subheadline, max_width=w - margin * 2, max_lines=2, start_size=21, min_size=17, bold=False)
        y += 8
        for line in sub_lines:
            draw.text((margin, y), line, font=sub_font, fill=SLATE_500)
            y += int(sub_font.size * 1.28)

    nodes = [n for n in (architecture_nodes or key_points or []) if n][:4]
    if not nodes:
        nodes = ["Client Portal / App", "REST API Gateway", "Central Database", "Automated Workflows"]
    while len(nodes) < 3:
        nodes.append("Monitoring & Backups")

    # Clean 2x2 or 3-node connected architecture blueprint
    diag_top = max(y + 36, 300)
    diag_bot = h - 140
    box_w = 450
    box_h = 180
    left_x = margin + 10
    right_x = w - margin - 10 - box_w
    row1_y = diag_top + 20
    row2_y = diag_bot - box_h - 20

    coords = [
        (left_x, row1_y, "01 · INPUT / INTERFACE"),
        (right_x, row1_y, "02 · API / PROCESSING"),
        (right_x, row2_y, "03 · DATA / STORAGE"),
        (left_x, row2_y, "04 · OUTPUT / AUTOMATION"),
    ][:len(nodes)]

    # Draw clean directional connectors between nodes
    if len(coords) >= 2:
        # 1 -> 2 (top horizontal)
        y_mid1 = row1_y + box_h // 2
        draw.line([(left_x + box_w, y_mid1), (right_x, y_mid1)], fill=COBALT, width=4)
        draw.polygon([(right_x, y_mid1), (right_x - 14, y_mid1 - 8), (right_x - 14, y_mid1 + 8)], fill=COBALT)
    if len(coords) >= 3:
        # 2 -> 3 (right vertical)
        x_mid_r = right_x + box_w // 2
        draw.line([(x_mid_r, row1_y + box_h), (x_mid_r, row2_y)], fill=COBALT, width=4)
        draw.polygon([(x_mid_r, row2_y), (x_mid_r - 8, row2_y - 14), (x_mid_r + 8, row2_y - 14)], fill=COBALT)
    if len(coords) == 4:
        # 3 -> 4 (bottom horizontal right-to-left)
        y_mid2 = row2_y + box_h // 2
        draw.line([(right_x, y_mid2), (left_x + box_w, y_mid2)], fill=COBALT, width=4)
        draw.polygon([(left_x + box_w, y_mid2), (left_x + box_w + 14, y_mid2 - 8), (left_x + box_w + 14, y_mid2 + 8)], fill=COBALT)

    for idx, (nx, ny, layer_tag) in enumerate(coords):
        is_primary = (idx == 1)
        bg = NAVY_DEEP if is_primary else PURE_WHITE
        border = COBALT if is_primary else SLATE_200
        tag_col = CYAN if is_primary else COBALT
        txt_col = PURE_WHITE if is_primary else NAVY_DEEP

        draw.rounded_rectangle([nx, ny, nx + box_w, ny + box_h], radius=18, fill=bg, outline=border, width=2)
        draw.text((nx + 28, ny + 26), layer_tag, font=_get_font(14, bold=True), fill=tag_col)
        nf, nl = _fit_text_block(draw, nodes[idx], max_width=box_w - 56, max_lines=2, start_size=28, min_size=20, bold=True)
        ty = ny + 68
        for ln in nl:
            draw.text((nx + 28, ty), ln, font=nf, fill=txt_col)
            ty += int(nf.size * 1.25)

    _draw_footer(img, draw, w, h, cta_text or "jeevyamtechnologies.com", is_dark=False, service_label=service_category)
    return img


# ==============================================================================
# MASTER DISPATCHER
# ==============================================================================

def _to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_canva_template(
    template_id: str,
    headline: str,
    subheadline: str = "",
    key_points: Optional[List[str]] = None,
    problem_points: Optional[List[str]] = None,
    solution_points: Optional[List[str]] = None,
    architecture_nodes: Optional[List[str]] = None,
    carousel_slides: Optional[List[Any]] = None,
    service_category: Optional[str] = None,
    cta_text: Optional[str] = None,
    caption: Optional[str] = None,
) -> bytes:
    """Render any of the 6 Canva-style templates and return 1200x1200 PNG bytes."""
    derived = key_points or _derive_points_from_caption(caption, limit=4)

    if template_id == "editorial_insight":
        img = render_editorial_insight(headline, subheadline, key_points=derived, service_category=service_category, cta_text=cta_text)
    elif template_id == "problem_vs_solution":
        img = render_problem_vs_solution(
            headline, subheadline,
            problem_points=problem_points,
            solution_points=solution_points,
            key_points=derived,
            service_category=service_category,
            cta_text=cta_text,
        )
    elif template_id == "educational_infographic":
        img = render_educational_infographic(headline, subheadline, key_points=derived, service_category=service_category, cta_text=cta_text)
    elif template_id == "service_spotlight":
        img = render_service_spotlight(headline, subheadline, key_points=derived, service_category=service_category, cta_text=cta_text)
    elif template_id == "linkedin_carousel":
        img = render_linkedin_carousel_cover(headline, subheadline, key_points=derived, service_category=service_category, cta_text=cta_text)
    elif template_id == "technical_architecture":
        img = render_technical_architecture(
            headline, subheadline,
            architecture_nodes=architecture_nodes,
            key_points=derived,
            service_category=service_category,
            cta_text=cta_text,
        )
    else:
        img = render_editorial_insight(headline, subheadline, key_points=derived, service_category=service_category, cta_text=cta_text)

    return _to_png_bytes(img)
