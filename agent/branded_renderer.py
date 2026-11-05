"""Zero-cost, Python-based diverse branded image generator for Jevyam Technologies.

Generates 12+ genuinely distinct 1200x1200 LinkedIn graphics matching the
official Jeevyam Technologies visual identity using Pillow drawing primitives,
gradients, geometry, clean typography, and the official brand star mark.
"""

from io import BytesIO
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

# ==============================================================================
# BRAND CONSTANTS & COLOR PALETTES
# ==============================================================================

CANVAS_SIZE = (1200, 1200)

# Primary Brand Palettes
NAVY_DEEP = (10, 17, 40, 255)            # #0A1128
NAVY_MID = (17, 28, 56, 255)             # #111C38
OBSIDIAN = (5, 9, 22, 255)               # #050916
CHARCOAL = (15, 23, 42, 255)             # #0F172A

LIGHT_CANVAS = (248, 250, 252, 255)      # #F8FAFC
CLEAN_WHITE = (255, 255, 255, 255)       # #FFFFFF
SLATE_BORDER = (226, 232, 240, 255)      # #E2E8F0

# Electric Accents
ACCENT_BLUE = (0, 102, 255, 255)         # #0066FF (Cobalt)
ACCENT_CYAN = (0, 210, 255, 255)         # #00D2FF (Electric Cyan)
ACCENT_DEEP_BLUE = (37, 99, 235, 255)    # #2563EB (Tech Royal Blue)
ACCENT_TEAL = (20, 184, 166, 255)        # #14B8A6 (Teal)
ACCENT_PURPLE = (124, 58, 237, 255)      # #7C3AED (Deep Violet)
ACCENT_CORAL = (244, 63, 94, 255)        # #F43F5E (Alert Coral)

# Text Colors
TEXT_DARK_PRIMARY = (255, 255, 255, 255)
TEXT_DARK_SECONDARY = (148, 163, 184, 255)  # #94A3B8
TEXT_DARK_MUTED = (100, 116, 139, 255)      # #64748B

TEXT_LIGHT_PRIMARY = (10, 17, 40, 255)
TEXT_LIGHT_SECONDARY = (71, 85, 105, 255)   # #475569
TEXT_LIGHT_MUTED = (148, 163, 184, 255)

# Asset paths
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Available 12 Diverse Layout Keys
ALL_LAYOUTS: List[str] = [
    "dark_cyber_tech",
    "minimalist_editorial",
    "split_screen_comparison",
    "data_visualization",
    "isometric_infrastructure",
    "timeline_roadmap",
    "process_flow",
    "magazine_cover",
    "geometric_abstract",
    "quote_insight",
    "layered_cards",
    "product_announcement",
]

# ==============================================================================
# FONT LOADER
# ==============================================================================

_FONT_CACHE: Dict[Tuple[int, bool], Any] = {}


def get_font(size: int, bold: bool = False) -> Any:
    """Load the best available modern sans-serif font, with caching and fallback."""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font_candidates: List[str] = []
    if bold:
        font_candidates.extend([
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "arialbd.ttf",
        ])
    else:
        font_candidates.extend([
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
            "arial.ttf",
        ])

    font: Optional[Any] = None
    for path in font_candidates:
        if os.path.exists(path) or not os.path.isabs(path):
            try:
                font = ImageFont.truetype(path, size=size)
                break
            except Exception:
                continue

    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

    _FONT_CACHE[key] = font
    return font


# ==============================================================================
# DRAWING PRIMITIVES & LOGO SYSTEM
# ==============================================================================

def create_gradient_canvas(
    size: Tuple[int, int],
    top_color: Tuple[int, int, int, int],
    bottom_color: Tuple[int, int, int, int],
) -> Image.Image:
    """Create a vertical gradient image canvas."""
    width, height = size
    base = Image.new("RGBA", size, top_color)
    top_r, top_g, top_b, top_a = top_color
    bot_r, bot_g, bot_b, bot_a = bottom_color

    draw = ImageDraw.Draw(base)
    for y in range(height):
        factor = y / max(1, height - 1)
        r = int(top_r + (bot_r - top_r) * factor)
        g = int(top_g + (bot_g - top_g) * factor)
        b = int(top_b + (bot_b - top_b) * factor)
        a = int(top_a + (bot_a - top_a) * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b, a))

    return base


def create_radial_spotlight_canvas(
    size: Tuple[int, int],
    bg_color: Tuple[int, int, int, int],
    spot_color: Tuple[int, int, int],
    center: Tuple[int, int],
    radius: int = 600,
) -> Image.Image:
    """Create a canvas with a radiant top/center spotlight flare."""
    base = Image.new("RGBA", size, bg_color)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = center
    steps = 30
    for i in range(steps, 0, -1):
        cur_r = int(radius * (i / steps))
        alpha = int(75 * ((1.0 - (i / steps)) ** 2))
        if alpha <= 0:
            continue
        draw.ellipse([cx - cur_r, cy - cur_r, cx + cur_r, cy + cur_r], fill=(*spot_color, alpha))
    base.alpha_composite(overlay)
    return base


def draw_glow_circle(
    img: Image.Image,
    cx: int,
    cy: int,
    radius: int,
    color: Tuple[int, int, int],
    max_alpha: int = 70,
) -> None:
    """Draw a soft multi-ring radial glow onto an RGBA image."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    r_val, g_val, b_val = color[:3]

    steps = 25
    for i in range(steps, 0, -1):
        cur_radius = int(radius * (i / steps))
        alpha = int(max_alpha * ((1 - (i / steps)) ** 1.8))
        if alpha <= 0:
            continue
        draw.ellipse(
            [cx - cur_radius, cy - cur_radius, cx + cur_radius, cy + cur_radius],
            fill=(r_val, g_val, b_val, alpha),
        )

    img.alpha_composite(overlay)


def _draw_vector_digital_cross_fallback(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int = 32,
    is_dark: bool = True,
) -> None:
    """Vector fallback for Jeevyam digital cross mark if image file is not found."""
    color_core = ACCENT_CYAN if is_dark else ACCENT_DEEP_BLUE
    color_arm = ACCENT_BLUE
    # Central diamond star
    d = radius // 2
    draw.polygon([(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)], fill=color_core)
    # Radiating digital data bars
    for offset in range(6, radius + 12, 6):
        draw.line([(cx, cy - offset), (cx, cy - offset - 4)], fill=color_arm, width=3)
        draw.line([(cx, cy + offset), (cx, cy + offset + 4)], fill=color_arm, width=3)
        draw.line([(cx - offset, cy), (cx - offset - 4, cy)], fill=color_arm, width=3)
        draw.line([(cx + offset, cy), (cx + offset + 4, cy)], fill=color_arm, width=3)


def draw_jevyam_logo(
    draw: ImageDraw.ImageDraw,
    x: int = 80,
    y: int = 70,
    is_dark: bool = True,
    img: Optional[Image.Image] = None,
) -> int:
    """Draw the official Jeevyam Technologies logo mark and typography.

    Loads the user-provided brand star mark from assets if available,
    with a crisp vector digital cross fallback for isolated environments.
    Returns the right-edge X coordinate of the logo block.
    """
    mark_w = 76
    mark_h = 70
    mark_pasted = False

    if img is not None:
        mark_file = "mark_dark.png" if is_dark else "mark_light.png"
        for candidate_dir in (_ASSETS_DIR, Path("assets"), Path("../assets")):
            p = candidate_dir / mark_file
            if p.exists():
                try:
                    mark_img = Image.open(p).convert("RGBA")
                    w = int(mark_img.width * (mark_h / mark_img.height))
                    res = mark_img.resize((w, mark_h), Image.Resampling.LANCZOS)
                    img.paste(res, (x, y - 6), res)
                    mark_w = w
                    mark_pasted = True
                    break
                except Exception:
                    pass

    if not mark_pasted:
        _draw_vector_digital_cross_fallback(draw, cx=x + 36, cy=y + 28, radius=30, is_dark=is_dark)
        mark_w = 72

    # Clean official typography
    text_color = TEXT_DARK_PRIMARY if is_dark else TEXT_LIGHT_PRIMARY
    sub_color = ACCENT_CYAN if is_dark else ACCENT_DEEP_BLUE

    font_brand = get_font(32, bold=True)
    font_tag = get_font(13, bold=True)

    text_x = x + mark_w + 16
    draw.text((text_x, y - 4), "JEEVYAM", font=font_brand, fill=text_color)
    draw.text((text_x + 2, y + 34), "T E C H N O L O G I E S", font=font_tag, fill=sub_color)

    return text_x + 210


def draw_tagline(
    draw: ImageDraw.ImageDraw,
    text: str = "BUILD  ·  AUTOMATE  ·  SCALE",
    x_right: int = 1120,
    y: int = 75,
    is_dark: bool = True,
) -> None:
    """Render tracked, elegant header tagline on the top-right."""
    font = get_font(15, bold=True)
    color = TEXT_DARK_MUTED if is_dark else TEXT_LIGHT_MUTED
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text((x_right - text_w, y), text, font=font, fill=color)


def draw_icon(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    icon_type: str,
    color: Tuple[int, int, int, int],
    size: int = 28,
) -> None:
    """Draw a vector technical icon primitive."""
    hs = size // 2
    itype = icon_type.lower()

    if "gear" in itype or "auto" in itype:
        draw.ellipse([cx - hs + 4, cy - hs + 4, cx + hs - 4, cy + hs - 4], outline=color, width=3)
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=color)
        for angle in (0, 45, 90, 135):
            rad = math.radians(angle)
            dx = int(math.cos(rad) * hs)
            dy = int(math.sin(rad) * hs)
            draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=color, width=3)
    elif "bulb" in itype or "innov" in itype:
        draw.ellipse([cx - hs + 2, cy - hs, cx + hs - 2, cy + 2], outline=color, width=3)
        draw.rectangle([cx - hs // 3, cy + 2, cx + hs // 3, cy + hs - 2], fill=color)
        draw.line([cx - hs // 4, cy + hs, cx + hs // 4, cy + hs], fill=color, width=2)
    elif "growth" in itype or "stat" in itype or "chart" in itype or "data" in itype:
        bar_w = size // 4
        gap = 2
        draw.rectangle([cx - hs, cy + hs // 3, cx - hs + bar_w, cy + hs], fill=color)
        draw.rectangle([cx - hs // 4, cy - hs // 4, cx - hs // 4 + bar_w, cy + hs], fill=color)
        draw.rectangle([cx + hs // 2 - gap, cy - hs, cx + hs // 2 - gap + bar_w, cy + hs], fill=color)
    elif "code" in itype or "dev" in itype:
        draw.line([(cx - 4, cy - hs), (cx - hs, cy), (cx - 4, cy + hs)], fill=color, width=3)
        draw.line([(cx + 4, cy - hs), (cx + hs, cy), (cx + 4, cy + hs)], fill=color, width=3)
        draw.line([(cx - 2, cy + hs - 4), (cx + 2, cy - hs + 4)], fill=color, width=2)
    elif "rocket" in itype or "scale" in itype or "impact" in itype:
        draw.polygon([(cx, cy - hs - 2), (cx + hs, cy + hs), (cx, cy + hs // 2), (cx - hs, cy + hs)], fill=color)
    elif "shield" in itype or "security" in itype:
        draw.polygon([(cx, cy - hs), (cx + hs, cy - hs // 2), (cx + hs, cy + 2), (cx, cy + hs), (cx - hs, cy + 2), (cx - hs, cy - hs // 2)], outline=color, width=3)
    elif "check" in itype:
        draw.line([(cx - hs + 2, cy), (cx - 2, cy + hs - 2), (cx + hs, cy - hs + 2)], fill=color, width=4)
    elif "search" in itype or "need" in itype or "insight" in itype:
        cr = hs - 4
        draw.ellipse([cx - hs, cy - hs, cx - hs + cr * 2, cy - hs + cr * 2], outline=color, width=3)
        draw.line([(cx + 2, cy + 2), (cx + hs, cy + hs)], fill=color, width=4)
    elif "chip" in itype or "ai" in itype or "tech" in itype:
        draw.rectangle([cx - hs + 3, cy - hs + 3, cx + hs - 3, cy + hs - 3], outline=color, width=3)
        draw.rectangle([cx - hs // 3, cy - hs // 3, cx + hs // 3, cy + hs // 3], fill=color)
        for offset in (-hs // 2, hs // 2):
            draw.line([(cx + offset, cy - hs), (cx + offset, cy - hs + 3)], fill=color, width=2)
            draw.line([(cx + offset, cy + hs - 3), (cx + offset, cy + hs)], fill=color, width=2)
            draw.line([(cx - hs, cy + offset), (cx - hs + 3, cy + offset)], fill=color, width=2)
            draw.line([(cx + hs - 3, cy + offset), (cx + hs, cy + offset)], fill=color, width=2)
    else:
        draw.ellipse([cx - hs // 2, cy - hs // 2, cx + hs // 2, cy + hs // 2], fill=color)


# ==============================================================================
# TEXT WRAPPING & HEADLINE FORMATTING
# ==============================================================================

def clean_headline_text(raw_title: str) -> str:
    """Normalize raw post titles into clean, punchy headline text."""
    if not raw_title:
        return "Building Technology for Tomorrow"
    clean = raw_title.strip().strip("\"'").replace("  ", " ")
    clean = re.sub(r"^(Topic|Headline|Title):\s*", "", clean, flags=re.IGNORECASE)
    clean = clean.replace("**", "").replace("*", "").replace("`", "")
    return clean.strip()


def wrap_text_to_lines(
    arg1: Any,
    arg2: Any = None,
    arg3: Any = None,
    max_width: int = 500,
    max_lines: Optional[int] = None,
    **kwargs: Any,
) -> List[str]:
    """Wrap text to fit within max_width pixels.

    Supports both signatures:
    - wrap_text_to_lines(draw, text, font, max_width)
    - wrap_text_to_lines(text, font, max_width, max_lines=None, draw=None)
    """
    if isinstance(arg1, ImageDraw.ImageDraw):
        draw = arg1
        text = str(arg2 or "")
        font = arg3
        limit_w = max_width
    else:
        text = str(arg1 or "")
        font = arg2
        limit_w = int(arg3 if arg3 is not None else max_width)
        draw = kwargs.get("draw")

    if draw is None:
        draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current_line: List[str] = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= limit_w:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(" ".join(current_line))

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]

    return lines


def draw_two_tone_headline(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    x: int,
    y: int,
    font: Any,
    base_color: Tuple[int, int, int, int],
    highlight_color: Tuple[int, int, int, int],
    highlight_words: Optional[List[str]] = None,
    line_spacing: int = 16,
) -> int:
    """Render multi-line headline where key anchor words receive an electric accent color."""
    default_highlights = {
        "impact", "intelligence", "ai", "solutions", "scalable", "scale",
        "automate", "automation", "future", "execution", "clarity", "power",
        "speed", "reliable", "smart", "insights", "tomorrow", "growth", "zero",
    }
    hl_set = {w.lower() for w in (highlight_words or [])} | default_highlights

    cur_y = y
    space_bbox = draw.textbbox((0, 0), " ", font=font)
    space_w = space_bbox[2] - space_bbox[0]

    for line in lines:
        cur_x = x
        words = line.split(" ")
        for word in words:
            clean_word = re.sub(r"[^\w]", "", word).lower()
            is_hl = clean_word in hl_set
            col = highlight_color if is_hl else base_color

            draw.text((cur_x, cur_y), word, font=font, fill=col)
            w_bbox = draw.textbbox((0, 0), word, font=font)
            cur_x += (w_bbox[2] - w_bbox[0]) + space_w

        line_h = draw.textbbox((0, 0), line or "A", font=font)[3] - draw.textbbox((0, 0), line or "A", font=font)[1]
        cur_y += line_h + line_spacing

    return cur_y


def extract_content_summary(
    title: Optional[str] = None,
    caption: Optional[str] = None,
    visual_concept: Optional[str] = None,
    topic: Optional[str] = None,
) -> Tuple[str, str]:
    """Extract a concise headline and 1-2 sentence subtitle from post data."""
    headline = ""
    if title and title.strip():
        headline = clean_headline_text(title)
    elif topic and topic.strip():
        headline = clean_headline_text(topic)
    elif visual_concept and "text_on_image" in visual_concept.lower():
        match = re.search(r"text_on_image['\"]?:\s*['\"]([^'\"]+)['\"]", visual_concept, re.IGNORECASE)
        if match:
            headline = match.group(1).strip()

    if not headline:
        headline = "Enterprise AI & Scalable Automation"

    subtitle = ""
    if caption and caption.strip():
        sentences = re.split(r"(?<=[.!?])\s+", caption.strip())
        for sent in sentences:
            clean_s = sent.strip().strip("\"'")
            if 20 <= len(clean_s) <= 150:
                subtitle = clean_s
                break
        if not subtitle and sentences:
            subtitle = sentences[0][:140] + ("..." if len(sentences[0]) > 140 else "")

    if not subtitle:
        subtitle = "Custom AI solutions to accelerate your enterprise business growth."

    return headline, subtitle


# ==============================================================================
# DETERMINISTIC LAYOUT SELECTION & SERVICE ROTATION
# ==============================================================================

OFFICIAL_SERVICE_TAGLINES: Dict[str, str] = {
    "Inventory Management Systems": "SERVICE 01  ·  INVENTORY MANAGEMENT",
    "CRM Solutions": "SERVICE 02  ·  CRM SOLUTIONS",
    "Custom Software Development": "SERVICE 03  ·  CUSTOM SOFTWARE",
    "Website Design & Development": "SERVICE 04  ·  WEB DEVELOPMENT",
    "Mobile App Development": "SERVICE 05  ·  MOBILE APPS",
    "Digital Marketing": "SERVICE 06  ·  DIGITAL MARKETING",
    "AI & Business Automation": "SERVICE 07  ·  AI & AUTOMATION",
    "IT Consultancy & Support": "SERVICE 08  ·  IT CONSULTING",
}


def format_service_tagline(service_name_or_cand: Optional[str]) -> str:
    """Resolve clean tracked header tagline for official service."""
    if not service_name_or_cand:
        return "BUILD  ·  AUTOMATE  ·  SCALE"
    clean = service_name_or_cand.strip()
    for s_name, tag in OFFICIAL_SERVICE_TAGLINES.items():
        if s_name.lower() in clean.lower() or clean.lower() in s_name.lower():
            return tag
    return "BUILD  ·  AUTOMATE  ·  SCALE"


def detect_optimal_layout(
    title: str,
    caption: str,
    visual_concept: Optional[str] = None,
    preferred_layout: Optional[str] = None,
    previous_layouts: Optional[List[str]] = None,
    revision: int = 1,
    post_id: Optional[str] = None,
    service_category: Optional[str] = None,
) -> str:
    """Determine the most compelling visual layout based on content intent.

    Features:
    - 12 distinct layout styles supported.
    - Deterministic ranking based on semantic keywords and service pillar affinities.
    - Automatic exclusion of previous revision layouts to ensure visual variety.
    - Deterministic offset based on post revision (no random flapping).
    """
    # 1. Direct override
    if preferred_layout and preferred_layout.lower().strip() not in ("auto", "none", ""):
        cand = preferred_layout.lower().strip()
        # Aliases
        alias_map = {
            "tech": "dark_cyber_tech",
            "tech_announcement": "dark_cyber_tech",
            "announcement": "product_announcement",
            "stats": "data_visualization",
            "stats_insight": "data_visualization",
            "metrics": "data_visualization",
            "workflow": "process_flow",
            "process": "process_flow",
            "diagram": "process_flow",
            "company": "layered_cards",
            "company_message": "layered_cards",
            "marketing": "geometric_abstract",
            "editorial": "minimalist_editorial",
            "minimal": "minimalist_editorial",
            "comparison": "split_screen_comparison",
            "vs": "split_screen_comparison",
            "infrastructure": "isometric_infrastructure",
            "isometric": "isometric_infrastructure",
            "roadmap": "timeline_roadmap",
            "timeline": "timeline_roadmap",
            "magazine": "magazine_cover",
            "quote": "quote_insight",
            "cards": "layered_cards",
            "launch": "product_announcement",
            "product": "product_announcement",
        }
        resolved = alias_map.get(cand, cand)
        if resolved in ALL_LAYOUTS:
            return resolved

    combined = f"{service_category or ''} {title} {caption} {visual_concept or ''}".lower()

    # 2. Score all 12 layouts semantically with service-specific boosts
    scores: Dict[str, float] = {k: 1.0 for k in ALL_LAYOUTS}

    # Service-specific primary layout affinities
    if any(k in combined for k in ("inventory", "warehouse", "stock", "scrap", "raw material", "finished goods", "reconciliation")):
        scores["process_flow"] += 14.0
        scores["data_visualization"] += 12.0
        scores["split_screen_comparison"] += 10.0
        scores["layered_cards"] += 9.0
    elif any(k in combined for k in ("crm", "sales pipeline", "lead", "quotation", "deal", "follow-up", "vendor registry")):
        scores["process_flow"] += 14.0
        scores["timeline_roadmap"] += 12.0
        scores["layered_cards"] += 11.0
        scores["minimalist_editorial"] += 9.0
    elif any(k in combined for k in ("custom software", "business application", "desktop tool", "database engine", "api integration", "bespoke")):
        scores["isometric_infrastructure"] += 14.0
        scores["process_flow"] += 12.0
        scores["dark_cyber_tech"] += 11.0
        scores["split_screen_comparison"] += 10.0
    elif any(k in combined for k in ("website", "web design", "e-commerce", "storefront", "portal", "core web vitals", "technical seo", "bounce rate")):
        scores["split_screen_comparison"] += 14.0
        scores["minimalist_editorial"] += 12.0
        scores["product_announcement"] += 11.0
        scores["magazine_cover"] += 10.0
    elif any(k in combined for k in ("mobile app", "android", "ios", "smartphone", "cross-platform", "field operator", "app store")):
        scores["product_announcement"] += 14.0
        scores["split_screen_comparison"] += 12.0
        scores["process_flow"] += 11.0
        scores["minimalist_editorial"] += 10.0
    elif any(k in combined for k in ("digital marketing", "search engine optimization", "google ads", "social media", "search ranking", "conversion tracking", "roi measurement")):
        scores["data_visualization"] += 14.0
        scores["timeline_roadmap"] += 12.0
        scores["geometric_abstract"] += 11.0
        scores["magazine_cover"] += 10.0
    elif any(k in combined for k in ("ai & business automation", "automation", "chatbot", "document parsing", "invoice", "receipt", "translation pipeline")):
        scores["process_flow"] += 14.0
        scores["dark_cyber_tech"] += 12.0
        scores["isometric_infrastructure"] += 11.0
        scores["layered_cards"] += 10.0
    elif any(k in combined for k in ("it consultancy", "consultancy", "database migration", "security audit", "cloud hosting", "backup automation", "disaster recovery")):
        scores["isometric_infrastructure"] += 14.0
        scores["dark_cyber_tech"] += 12.0
        scores["split_screen_comparison"] += 11.0
        scores["process_flow"] += 10.0

    # Topic-specific semantic keywords
    if any(k in combined for k in ("vs", "versus", "compare", "comparison", "before", "after", "legacy", "migration", "difference")):
        scores["split_screen_comparison"] += 12.0
    if any(k in combined for k in ("99.", "%", "metric", "stat", "uptime", "benchmark", "roi", "numbers", "throughput", "latency")):
        scores["data_visualization"] += 12.0
    if any(k in combined for k in ("pipeline", "workflow", "process", "ingest", "stages", "step", "lifecycle", "flow")):
        scores["process_flow"] += 12.0
    if any(k in combined for k in ("roadmap", "timeline", "milestone", "phases", "journey", "future", "evolution", "quarter")):
        scores["timeline_roadmap"] += 11.0
    if any(k in combined for k in ("architecture", "infrastructure", "backend", "distributed", "kubernetes", "database", "cluster", "cube")):
        scores["isometric_infrastructure"] += 11.0
    if any(k in combined for k in ("cyber", "security", "zero-trust", "devops", "neural", "token", "auth", "crypto", "vulnerability")):
        scores["dark_cyber_tech"] += 10.0
    if any(k in combined for k in ("launch", "announcing", "release", "introducing", "unveiling", "new feature", "announcement")):
        scores["product_announcement"] += 11.0
    if any(k in combined for k in ("report", "review", "edition", "trend", "industry", "future of", "magazine", "special")):
        scores["magazine_cover"] += 10.0
    if any(k in combined for k in ("quote", "philosophy", "wisdom", "leader", "thought", "perspective", "belief", "lesson")):
        scores["quote_insight"] += 10.0
    if any(k in combined for k in ("pillars", "principles", "framework", "cards", "modular", "stack", "core values")):
        scores["layered_cards"] += 9.0
    if any(k in combined for k in ("impact", "scale", "innovate", "transform", "creative", "vision", "geometric")):
        scores["geometric_abstract"] += 8.0
    if any(k in combined for k in ("editorial", "minimal", "clean", "essay", "deep dive", "analysis", "opinion")):
        scores["minimalist_editorial"] += 8.0

    # 3. Sort layouts by score descending
    ranked = sorted(ALL_LAYOUTS, key=lambda l: scores[l], reverse=True)

    # 4. Filter out recently used layouts if previous_layouts provided
    prev_set = set(previous_layouts or [])
    available = [l for l in ranked if l not in prev_set]
    if not available:
        available = ranked

    # 5. Deterministic selection with revision rotation
    # If revision == 1 and top candidate scored higher than baseline, pick the best match
    if revision == 1 and scores[available[0]] > 1.0:
        return available[0]

    # For subsequent revisions (or when no keywords match), rotate deterministically across top candidates
    seed = (hash(post_id or title) & 0x7FFFFFFF) + (revision - 1)
    top_candidates = available[:3]
    return top_candidates[seed % len(top_candidates)]


# ==============================================================================
# 12 DISTINCT LAYOUT RENDERERS
# ==============================================================================

# 1. Dark Cyber / Neon Tech
def render_dark_cyber_tech_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
    tagline: Optional[str] = None,
    service_category: Optional[str] = None,
    **kwargs: Any,
) -> Image.Image:
    """1. Dark cyber/neon technology layout with glowing matrix grid and technical core."""
    img = create_gradient_canvas(CANVAS_SIZE, (4, 7, 17, 255), (10, 19, 43, 255))
    draw = ImageDraw.Draw(img)

    # Circuit traces & cyber grid
    for x in range(0, 1200, 150):
        draw.line([(x, 0), (x, 1200)], fill=(20, 35, 75, 45), width=1)
    for y in range(0, 1200, 150):
        draw.line([(0, y), (1200, y)], fill=(20, 35, 75, 45), width=1)

    # Top Header
    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text=tagline or "CYBER  ·  NEURAL  ·  SYSTEMS", x_right=1120, y=75, is_dark=True)

    # Tech badge
    badge_label = f"[ {service_category.upper()[:28]} // ENTERPRISE ]" if service_category else "[ SYSTEM_CORE // HIGH_AVAILABILITY ]"
    badge_w = 420 if service_category else 380
    draw.rounded_rectangle([80, 180, 80 + badge_w, 218], radius=8, fill=(17, 28, 56, 220), outline=ACCENT_CYAN, width=1)
    font_mono = get_font(13, bold=True)
    draw.text((96, 191), badge_label, font=font_mono, fill=ACCENT_CYAN)

    # Headline
    font_hl = get_font(52, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=680)
    end_y = draw_two_tone_headline(draw, hl_lines[:3], x=80, y=240, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Subtitle
    font_sub = get_font(21, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=650)
    for sl in sub_lines[:3]:
        draw.text((80, end_y + 10), sl, font=font_sub, fill=TEXT_DARK_SECONDARY)
        end_y += 32

    # Central Cyber Core Graphic (Right side)
    cx, cy = 940, 500
    draw_glow_circle(img, cx, cy, 220, (0, 210, 255), max_alpha=50)

    # Hexagonal data matrix
    for r in (180, 130, 80):
        hex_pts = []
        for i in range(6):
            ang = math.radians(i * 60 + 30)
            hex_pts.append((cx + int(r * math.cos(ang)), cy + int(r * math.sin(ang))))
        draw.polygon(hex_pts, outline=(0, 210, 255, 180), width=2)

    draw.ellipse([cx - 45, cy - 45, cx + 45, cy + 45], fill=(0, 102, 255, 230), outline=ACCENT_CYAN, width=3)
    draw_icon(draw, cx, cy, "chip", (255, 255, 255, 255), size=40)

    # Connected capability pills at bottom
    pts = (key_points or ["Autonomous Guardrails", "Deterministic Routing", "Zero-Trust Mesh"])[:3]
    pill_y = 960
    pill_w = 320
    for idx, p in enumerate(pts):
        px = 80 + idx * (pill_w + 40)
        draw.rounded_rectangle([px, pill_y, px + pill_w, pill_y + 110], radius=16, fill=(12, 22, 48, 220), outline=(45, 75, 135, 255), width=2)
        draw_icon(draw, px + 40, pill_y + 55, ["shield", "chip", "rocket"][idx % 3], ACCENT_CYAN, size=32)
        font_pill = get_font(20, bold=True)
        draw.text((px + 75, pill_y + 42), p[:22], font=font_pill, fill=TEXT_DARK_PRIMARY)

    return img


# 2. Minimalist Editorial Typography
def render_minimalist_editorial_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
    tagline: Optional[str] = None,
    service_category: Optional[str] = None,
    **kwargs: Any,
) -> Image.Image:
    """2. Minimalist editorial layout with generous negative space and stark typography."""
    img = create_gradient_canvas(CANVAS_SIZE, (253, 253, 254, 255), (243, 244, 246, 255))
    draw = ImageDraw.Draw(img)

    # Top Header
    draw_jevyam_logo(draw, x=90, y=80, is_dark=False, img=img)
    draw_tagline(draw, text=tagline or "ISSUE 26  ·  PERSPECTIVE", x_right=1110, y=85, is_dark=False)

    # Editorial rule line
    draw.line([(90, 180), (1110, 180)], fill=(203, 213, 225, 255), width=1)

    # Section index callout
    font_num = get_font(18, bold=True)
    callout_label = f"AGENCY OFFERING // {service_category.upper()[:28]}" if service_category else "01 / ESSAY"
    draw.text((90, 215), callout_label, font=font_num, fill=ACCENT_DEEP_BLUE)

    # Headline
    font_hl = get_font(56, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=1000)
    end_y = 265
    for line in hl_lines[:3]:
        draw.text((90, end_y), line, font=font_hl, fill=TEXT_LIGHT_PRIMARY)
        end_y += 72

    # Editorial Pullquote Box with thick vertical accent bar
    box_y = end_y + 45
    draw.rectangle([90, box_y, 96, box_y + 140], fill=ACCENT_BLUE)
    font_quote = get_font(24, bold=False)
    q_lines = wrap_text_to_lines(draw, f"\"{subtitle}\"", font_quote, max_width=920)
    cur_qy = box_y + 12
    for ql in q_lines[:3]:
        draw.text((125, cur_qy), ql, font=font_quote, fill=TEXT_LIGHT_SECONDARY)
        cur_qy += 38

    # Bottom Editorial Takeaways
    pts = (key_points or ["Architecture precedes implementation", "Idempotency prevents data loss"])[:2]
    foot_y = 860
    draw.line([(90, foot_y - 30), (1110, foot_y - 30)], fill=(226, 232, 240, 255), width=1)

    for idx, pt in enumerate(pts):
        col_x = 90 + idx * 520
        draw.text((col_x, foot_y), f"({chr(65 + idx)})", font=get_font(18, bold=True), fill=ACCENT_DEEP_BLUE)
        font_tk = get_font(20, bold=False)
        t_lines = wrap_text_to_lines(draw, pt, font_tk, max_width=440)
        for j, tl in enumerate(t_lines[:2]):
            draw.text((col_x + 40, foot_y + j * 30), tl, font=font_tk, fill=TEXT_LIGHT_PRIMARY)

    return img


# 3. Split-Screen Comparison
def render_split_screen_comparison_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
    tagline: Optional[str] = None,
    service_category: Optional[str] = None,
    **kwargs: Any,
) -> Image.Image:
    """3. Split-screen comparison layout: Left (Legacy) vs Right (Jevyam AI)."""
    img = Image.new("RGBA", CANVAS_SIZE, (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    # Right half: Electric cobalt gradient
    right_half = create_gradient_canvas((600, 1200), (0, 70, 180, 255), (10, 25, 75, 255))
    img.paste(right_half, (600, 0))

    # Top Header across full banner
    draw_jevyam_logo(draw, x=70, y=60, is_dark=True, img=img)
    draw_tagline(draw, text=tagline or "ARCHITECTURAL COMPARISON", x_right=1130, y=65, is_dark=True)

    # Headline spanning top
    font_hl = get_font(44, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=1060)
    top_end_y = draw_two_tone_headline(draw, hl_lines[:2], x=70, y=160, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Center vertical boundary line
    draw.line([(600, top_end_y + 40), (600, 1100)], fill=(255, 255, 255, 60), width=2)

    # VS Circle badge
    vs_y = (top_end_y + 40 + 1100) // 2
    draw.ellipse([555, vs_y - 45, 645, vs_y + 45], fill=(10, 17, 40, 255), outline=ACCENT_CYAN, width=3)
    draw.text((580, vs_y - 18), "VS", font=get_font(26, bold=True), fill=TEXT_DARK_PRIMARY)

    # Left Column: Legacy Approach
    left_x = 70
    draw.text((left_x, top_end_y + 60), "LEGACY WORKFLOW", font=get_font(22, bold=True), fill=ACCENT_CORAL)
    legacy_pts = ["Manual spreadsheet tracking", "Fragmented, disconnected tools", "Human error & data mismatches", "Slow turnaround & lost leads"]
    for i, lp in enumerate(legacy_pts):
        cy = top_end_y + 140 + i * 140
        draw.rounded_rectangle([left_x, cy, 540, cy + 105], radius=12, fill=(24, 34, 58, 220), outline=(244, 63, 94, 120), width=1)
        draw.text((left_x + 20, cy + 35), "✕", font=get_font(28, bold=True), fill=ACCENT_CORAL)
        draw.text((left_x + 60, cy + 38), lp, font=get_font(19, bold=False), fill=TEXT_DARK_SECONDARY)

    # Right Column: Jevyam Solution
    right_x = 660
    right_header = f"JEVYAM {service_category.upper()[:22]}" if service_category else "JEVYAM MODERN SOLUTION"
    draw.text((right_x, top_end_y + 60), right_header, font=get_font(22, bold=True), fill=ACCENT_CYAN)
    modern_pts = (key_points or ["Automated digital workflows", "Centralized data persistence", "Tailored operational logic", "High-visibility management dashboards"])[:4]
    while len(modern_pts) < 4:
        modern_pts.append("Sub-second live telemetry")

    for i, mp in enumerate(modern_pts):
        cy = top_end_y + 140 + i * 140
        draw.rounded_rectangle([right_x, cy, 1130, cy + 105], radius=12, fill=(17, 38, 90, 220), outline=ACCENT_CYAN, width=2)
        draw.text((right_x + 20, cy + 35), "✓", font=get_font(28, bold=True), fill=ACCENT_CYAN)
        draw.text((right_x + 60, cy + 38), mp[:35], font=get_font(19, bold=True), fill=TEXT_DARK_PRIMARY)

    return img


# 4. Data Visualization / Statistics
def render_data_visualization_layout(
    title: str,
    subtitle: str,
    stats: Optional[List[Tuple[str, str]]] = None,
    tagline: Optional[str] = None,
    service_category: Optional[str] = None,
    **kwargs: Any,
) -> Image.Image:
    """4. Data visualization & statistics layout with hero KPI and comparison bar chart."""
    img = create_gradient_canvas(CANVAS_SIZE, (10, 17, 40, 255), (4, 8, 20, 255))
    draw = ImageDraw.Draw(img)

    # Header
    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text=tagline or "BENCHMARK  ·  ANALYTICS", x_right=1120, y=75, is_dark=True)

    # Headline
    font_hl = get_font(48, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=680)
    end_y = draw_two_tone_headline(draw, hl_lines[:2], x=80, y=170, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Hero KPI Box (Left)
    kpi_val = "99.9%"
    kpi_label = "Production Reliability"
    if stats and len(stats) > 0:
        kpi_val, kpi_label = stats[0]

    draw.rounded_rectangle([80, end_y + 40, 480, end_y + 420], radius=20, fill=(17, 28, 56, 220), outline=(45, 75, 135, 255), width=2)
    draw_glow_circle(img, 280, end_y + 200, 140, (0, 210, 255), max_alpha=40)
    font_kpi = get_font(96, bold=True)
    draw.text((120, end_y + 110), kpi_val, font=font_kpi, fill=ACCENT_CYAN)
    font_lbl = get_font(24, bold=True)
    draw.text((120, end_y + 245), kpi_label[:26], font=font_lbl, fill=TEXT_DARK_PRIMARY)
    draw.text((120, end_y + 290), "Enterprise verified SLA metric", font=get_font(18, bold=False), fill=TEXT_DARK_MUTED)

    # Comparison Bar Chart (Right)
    chart_x = 520
    chart_y = end_y + 40
    chart_w = 600
    chart_h = 380

    draw.rounded_rectangle([chart_x, chart_y, chart_x + chart_w, chart_y + chart_h], radius=20, fill=(12, 22, 46, 200), outline=(35, 60, 110, 255), width=1)
    draw.text((chart_x + 30, chart_y + 25), "THROUGHPUT PERFORMANCE INDEX", font=get_font(16, bold=True), fill=TEXT_DARK_MUTED)

    bars = [("Legacy", 35, (71, 85, 105, 255)), ("Custom ETL", 62, (0, 102, 255, 255)), ("Jevyam AI", 98, (0, 210, 255, 255))]
    base_line = chart_y + chart_h - 70
    for idx, (b_name, b_val, b_col) in enumerate(bars):
        bx = chart_x + 70 + idx * 170
        bw = 85
        bh = int((b_val / 100.0) * 200)
        by = base_line - bh
        draw.rounded_rectangle([bx, by, bx + bw, base_line], radius=8, fill=b_col)
        draw.text((bx + 12, by - 36), f"{b_val}%", font=get_font(22, bold=True), fill=TEXT_DARK_PRIMARY)
        draw.text((bx + 6, base_line + 15), b_name, font=get_font(16, bold=False), fill=TEXT_DARK_SECONDARY)

    # Bottom Stat Cards
    c_y = end_y + 470
    card_items = stats[1:4] if stats and len(stats) > 1 else [("10x", "Throughput Velocity"), ("0%", "Silent Data Loss"), ("45%", "Cost Reduction")]
    card_w = 326
    for idx, (c_val, c_lbl) in enumerate(card_items[:3]):
        cx = 80 + idx * (card_w + 30)
        draw.rounded_rectangle([cx, c_y, cx + card_w, c_y + 170], radius=16, fill=(17, 28, 56, 220), outline=ACCENT_BLUE, width=1)
        draw.text((cx + 25, c_y + 25), c_val, font=get_font(48, bold=True), fill=ACCENT_CYAN)
        draw.text((cx + 25, c_y + 95), c_lbl[:22], font=get_font(20, bold=True), fill=TEXT_DARK_PRIMARY)

    return img


# 5. Isometric Infrastructure Illustration
def render_isometric_infrastructure_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
) -> Image.Image:
    """5. Isometric infrastructure illustration with tiered 3D architectural cubes."""
    img = create_gradient_canvas(CANVAS_SIZE, (8, 14, 36, 255), (4, 8, 20, 255))
    draw = ImageDraw.Draw(img)

    # Blueprint technical grid
    for x in range(0, 1200, 80):
        draw.line([(x, 0), (x, 1200)], fill=(25, 45, 95, 30), width=1)
    for y in range(0, 1200, 80):
        draw.line([(0, y), (1200, y)], fill=(25, 45, 95, 30), width=1)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text="SYSTEM  ·  INFRASTRUCTURE", x_right=1120, y=75, is_dark=True)

    # Headline
    font_hl = get_font(50, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=680)
    end_y = draw_two_tone_headline(draw, hl_lines[:3], x=80, y=180, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Subtitle
    font_sub = get_font(21, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=650)
    for sl in sub_lines[:2]:
        draw.text((80, end_y + 15), sl, font=font_sub, fill=TEXT_DARK_SECONDARY)
        end_y += 32

    # Isometric 3D Cubes (Right side)
    def draw_iso_cube(top_cx: int, top_cy: int, size: int, col_top: Tuple, col_left: Tuple, col_right: Tuple) -> None:
        dx = int(size * 0.866)
        dy = int(size * 0.5)
        # Top face
        draw.polygon([(top_cx, top_cy), (top_cx + dx, top_cy + dy), (top_cx, top_cy + 2 * dy), (top_cx - dx, top_cy + dy)], fill=col_top)
        # Left face
        draw.polygon([(top_cx - dx, top_cy + dy), (top_cx, top_cy + 2 * dy), (top_cx, top_cy + 2 * dy + size), (top_cx - dx, top_cy + dy + size)], fill=col_left)
        # Right face
        draw.polygon([(top_cx, top_cy + 2 * dy), (top_cx + dx, top_cy + dy), (top_cx + dx, top_cy + dy + size), (top_cx, top_cy + 2 * dy + size)], fill=col_right)

    draw_glow_circle(img, 920, 520, 260, (0, 210, 255), max_alpha=60)
    # Tier 1 (Base platform)
    draw_iso_cube(920, 560, size=90, col_top=(17, 38, 90, 255), col_left=(10, 24, 60, 255), col_right=(14, 30, 75, 255))
    # Tier 2 (Worker tier)
    draw_iso_cube(920, 440, size=75, col_top=(0, 102, 255, 255), col_left=(0, 75, 190, 255), col_right=(0, 85, 215, 255))
    # Tier 3 (Glowing Apex cube)
    draw_iso_cube(920, 320, size=60, col_top=(0, 230, 255, 255), col_left=(0, 175, 220, 255), col_right=(0, 195, 240, 255))

    # Connection lines
    draw.line([(920, 250), (920, 320)], fill=ACCENT_CYAN, width=3)
    draw.ellipse([915, 245, 925, 255], fill=ACCENT_CYAN)

    # 3 Infrastructure Pillars at Bottom
    pts = (key_points or ["Idempotent Pipelines", "Distributed Consensus", "Resilient Recovery"])[:3]
    card_y = 940
    card_w = 320
    for idx, p in enumerate(pts):
        cx = 80 + idx * (card_w + 40)
        draw.rounded_rectangle([cx, card_y, cx + card_w, card_y + 130], radius=16, fill=(14, 25, 55, 220), outline=ACCENT_BLUE, width=1)
        draw_icon(draw, cx + 40, card_y + 65, ["chip", "growth", "gear"][idx % 3], ACCENT_CYAN, size=32)
        draw.text((cx + 80, card_y + 50), p[:22], font=get_font(20, bold=True), fill=TEXT_DARK_PRIMARY)

    return img


# 6. Timeline / Roadmap
def render_timeline_roadmap_layout(
    title: str,
    subtitle: str,
    steps: Optional[List[str]] = None,
) -> Image.Image:
    """6. Timeline & roadmap layout with chronological milestones and progress line."""
    img = create_gradient_canvas(CANVAS_SIZE, (248, 250, 252, 255), (237, 242, 247, 255))
    draw = ImageDraw.Draw(img)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=False, img=img)
    draw_tagline(draw, text="EVOLUTION  ·  ROADMAP", x_right=1120, y=75, is_dark=False)

    font_hl = get_font(46, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=1000)
    end_y = 160
    for l in hl_lines[:2]:
        draw.text((80, end_y), l, font=font_hl, fill=TEXT_LIGHT_PRIMARY)
        end_y += 58

    # Central Timeline Progress Spine
    spine_x = 220
    draw.line([(spine_x, end_y + 60), (spine_x, 1080)], fill=ACCENT_BLUE, width=6)

    milestones = (steps or [
        "Phase 01: Systems Discovery & Auditing",
        "Phase 02: Resilient Cloud Architecture Design",
        "Phase 03: Autonomous Multi-Agent Integration",
        "Phase 04: Production Scale & Live Telemetry",
    ])[:4]

    for idx, ms in enumerate(milestones):
        my = end_y + 60 + idx * 210
        # Node circle
        draw.ellipse([spine_x - 22, my + 15, spine_x + 22, my + 59], fill=ACCENT_BLUE, outline=(255, 255, 255, 255), width=4)
        draw.text((spine_x - 8, my + 23), str(idx + 1), font=get_font(18, bold=True), fill=(255, 255, 255, 255))

        # Milestone Card
        card_x = spine_x + 60
        draw.rounded_rectangle([card_x, my, 1120, my + 140], radius=16, fill=CLEAN_WHITE, outline=SLATE_BORDER, width=2)
        draw.text((card_x + 30, my + 25), f"STAGE 0{idx + 1}", font=get_font(15, bold=True), fill=ACCENT_DEEP_BLUE)
        draw.text((card_x + 30, my + 60), ms[:55], font=get_font(22, bold=True), fill=TEXT_LIGHT_PRIMARY)

    return img


# 7. Process Flow Diagram
def render_process_flow_layout(
    title: str,
    subtitle: str,
    steps: Optional[List[str]] = None,
) -> Image.Image:
    """7. Process flow diagram with connected directional pipeline stages."""
    img = create_gradient_canvas(CANVAS_SIZE, (11, 19, 43, 255), (6, 10, 24, 255))
    draw = ImageDraw.Draw(img)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text="INGESTION  ·  TRANSFORM  ·  DEPLOY", x_right=1120, y=75, is_dark=True)

    font_hl = get_font(48, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=1000)
    end_y = draw_two_tone_headline(draw, hl_lines[:2], x=80, y=170, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    st_list = (steps or [
        "1. Ingest Raw Event Payloads",
        "2. Deterministic Agent Routing",
        "3. Automated Verification Gate",
        "4. Live Production Execution",
    ])[:4]

    # Render vertical stacked pipeline blocks with glowing chevron connectors
    start_y = end_y + 40
    step_h = 135
    for idx, s in enumerate(st_list):
        sy = start_y + idx * (step_h + 35)
        # Stage Box
        draw.rounded_rectangle([80, sy, 1120, sy + step_h], radius=18, fill=(17, 28, 56, 220), outline=ACCENT_BLUE if idx % 2 == 0 else ACCENT_CYAN, width=2)
        # Step number badge
        draw.rounded_rectangle([110, sy + 35, 175, sy + 100], radius=12, fill=ACCENT_BLUE, outline=ACCENT_CYAN, width=1)
        draw.text((128, sy + 48), f"0{idx + 1}", font=get_font(24, bold=True), fill=TEXT_DARK_PRIMARY)

        # Step Text
        draw.text((210, sy + 38), s[:55], font=get_font(24, bold=True), fill=TEXT_DARK_PRIMARY)
        draw.text((210, sy + 78), "Idempotent workflow node with live telemetry verification", font=get_font(17, bold=False), fill=TEXT_DARK_SECONDARY)

        # Connector Arrow below (except last)
        if idx < len(st_list) - 1:
            arr_y = sy + step_h
            draw.line([(600, arr_y), (600, arr_y + 30)], fill=ACCENT_CYAN, width=3)
            draw.polygon([(594, arr_y + 24), (606, arr_y + 24), (600, arr_y + 32)], fill=ACCENT_CYAN)

    return img


# 8. Bold Magazine Cover
def render_magazine_cover_layout(
    title: str,
    subtitle: str,
    features: Optional[List[str]] = None,
) -> Image.Image:
    """8. Bold publication magazine cover with masthead, teaser cards, and barcode."""
    img = create_radial_spotlight_canvas(CANVAS_SIZE, (4, 7, 16, 255), (0, 102, 255), (1000, 200), radius=550)
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([40, 40, 1160, 1160], outline=(45, 75, 135, 160), width=2)

    # Magazine Masthead
    draw.text((80, 75), "JEVYAM TECH REVIEW", font=get_font(28, bold=True), fill=TEXT_DARK_PRIMARY)
    draw_tagline(draw, text="VOL. 26 // SPECIAL AI ISSUE", x_right=1120, y=85, is_dark=True)
    draw.line([(80, 130), (1120, 130)], fill=(0, 210, 255, 180), width=3)

    # Massive hero title
    font_hl = get_font(60, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=980)
    end_y = draw_two_tone_headline(draw, hl_lines[:3], x=80, y=170, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN, line_spacing=20)

    # Left Side: Subtitle
    font_sub = get_font(24, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=640)
    for sl in sub_lines[:3]:
        draw.text((80, end_y + 20), sl, font=font_sub, fill=TEXT_DARK_SECONDARY)
        end_y += 36

    # Right Side Story Highlights
    story_x = 760
    draw.rounded_rectangle([story_x, 480, 1120, 850], radius=16, fill=(17, 28, 56, 200), outline=ACCENT_BLUE, width=1)
    draw.text((story_x + 25, 510), "INSIDE THIS BRIEF", font=get_font(16, bold=True), fill=ACCENT_CYAN)

    stories = (features or ["Multi-Agent Failure Boundaries", "Zero-Cost Visual Rendering", "Idempotent Event Systems"])[:3]
    for idx, st in enumerate(stories):
        sy = 560 + idx * 85
        draw.text((story_x + 25, sy), f"// 0{idx + 1}", font=get_font(15, bold=True), fill=ACCENT_DEEP_BLUE)
        draw.text((story_x + 25, sy + 24), st[:30], font=get_font(19, bold=True), fill=TEXT_DARK_PRIMARY)

    # Bottom Executive Banner with Barcode
    bar_y = 960
    draw.line([(80, bar_y - 20), (1120, bar_y - 20)], fill=(45, 75, 135, 140), width=1)

    # Barcode graphics
    bc_x = 80
    for w_idx in (2, 4, 1, 3, 5, 2, 6, 2, 4, 1, 3, 5, 2, 4, 1):
        draw.rectangle([bc_x, bar_y + 10, bc_x + w_idx, bar_y + 60], fill=(255, 255, 255, 200))
        bc_x += w_idx + 4
    draw.text((80, bar_y + 70), "ISBN 978-0-JEVYAM-2026", font=get_font(12, bold=False), fill=TEXT_DARK_MUTED)

    draw_jevyam_logo(draw, x=750, y=bar_y + 10, is_dark=True, img=img)

    return img


# 9. Geometric Abstract Composition
def render_geometric_abstract_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
) -> Image.Image:
    """9. Dynamic angled geometric ribbons and glassmorphism abstract layout."""
    img = create_gradient_canvas(CANVAS_SIZE, (4, 7, 20, 255), (14, 26, 60, 255))
    draw = ImageDraw.Draw(img)

    # Diagonal polygon shards
    draw.polygon([(850, 0), (1200, 0), (1200, 450), (600, 0)], fill=(0, 102, 255, 50))
    draw.polygon([(700, 1200), (1200, 600), (1200, 1200)], fill=(0, 210, 255, 40))
    draw.polygon([(1000, 0), (1200, 0), (1200, 800)], fill=(20, 184, 166, 30))

    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text="VISION  ·  IMPACT  ·  SCALE", x_right=1120, y=75, is_dark=True)

    # Hero Headline
    font_hl = get_font(52, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=750)
    end_y = draw_two_tone_headline(draw, hl_lines[:3], x=80, y=190, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Glassmorphism Card
    card_y = end_y + 40
    draw.rounded_rectangle([80, card_y, 760, card_y + 240], radius=24, fill=(17, 28, 56, 210), outline=ACCENT_CYAN, width=2)
    font_sub = get_font(23, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=630)
    for idx, sl in enumerate(sub_lines[:4]):
        draw.text((120, card_y + 35 + idx * 38), sl, font=font_sub, fill=TEXT_DARK_PRIMARY)

    # 3 Floating angled pills at bottom
    pts = (key_points or ["Autonomous Intelligence", "Resilient State Mesh", "Verified Enterprise Impact"])[:3]
    pill_y = 960
    pill_w = 320
    for idx, p in enumerate(pts):
        px = 80 + idx * (pill_w + 40)
        draw.rounded_rectangle([px, pill_y, px + pill_w, pill_y + 110], radius=16, fill=(12, 22, 48, 220), outline=ACCENT_BLUE, width=1)
        draw_icon(draw, px + 40, pill_y + 55, ["rocket", "chip", "bulb"][idx % 3], ACCENT_CYAN, size=32)
        draw.text((px + 75, pill_y + 42), p[:22], font=get_font(20, bold=True), fill=TEXT_DARK_PRIMARY)

    return img


# 10. Quote / Thought Leadership Insight
def render_quote_insight_layout(
    title: str,
    subtitle: str,
    key_points: Optional[List[str]] = None,
) -> Image.Image:
    """10. Executive thought-leadership quote card with giant cyan quotation marks."""
    img = create_gradient_canvas(CANVAS_SIZE, (10, 17, 40, 255), (5, 9, 22, 255))
    draw = ImageDraw.Draw(img)

    draw_glow_circle(img, 600, 500, 320, (0, 210, 255), max_alpha=40)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text="THOUGHT LEADERSHIP", x_right=1120, y=75, is_dark=True)

    # Giant decorative quotation mark “
    draw.text((80, 150), "“", font=get_font(180, bold=True), fill=ACCENT_CYAN)

    # Main Quote Text
    quote_text = title if len(title) > len(subtitle) else subtitle
    font_quote = get_font(42, bold=True)
    q_lines = wrap_text_to_lines(draw, quote_text, font_quote, max_width=1000)
    qy = 350
    for ql in q_lines[:4]:
        draw.text((100, qy), ql, font=font_quote, fill=TEXT_DARK_PRIMARY)
        qy += 62

    # Closing quotation mark ”
    draw.text((1000, qy - 40), "”", font=get_font(140, bold=True), fill=(0, 210, 255, 120))

    # Horizontal divider rule with center diamond
    div_y = qy + 90
    draw.line([(100, div_y), (1100, div_y)], fill=(45, 75, 135, 180), width=2)
    draw.polygon([(600, div_y - 8), (608, div_y), (600, div_y + 8), (592, div_y)], fill=ACCENT_CYAN)

    # Attribution block
    draw.text((100, div_y + 40), "JEVYAM TECHNOLOGIES", font=get_font(24, bold=True), fill=TEXT_DARK_PRIMARY)
    draw.text((100, div_y + 80), "Engineering & AI Practice · Autonomous Systems Blueprint", font=get_font(18, bold=False), fill=ACCENT_CYAN)

    return img


# 11. Layered Cards / Stack
def render_layered_cards_layout(
    title: str,
    subtitle: str,
    features: Optional[List[str]] = None,
) -> Image.Image:
    """11. Layered overlapping cards creating tangible depth and visual elevation."""
    img = create_gradient_canvas(CANVAS_SIZE, (241, 245, 249, 255), (226, 232, 240, 255))
    draw = ImageDraw.Draw(img)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=False, img=img)
    draw_tagline(draw, text="FOUNDATION  ·  PILLARS", x_right=1120, y=75, is_dark=False)

    font_hl = get_font(48, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=900)
    end_y = 160
    for l in hl_lines[:2]:
        draw.text((80, end_y), l, font=font_hl, fill=TEXT_LIGHT_PRIMARY)
        end_y += 60

    # 3 Cascading Layered Cards
    # Card 3 (Bottom background card)
    draw.rounded_rectangle([130, end_y + 70, 1070, end_y + 470], radius=24, fill=(210, 220, 235, 140), outline=SLATE_BORDER, width=2)
    # Card 2 (Middle card)
    draw.rounded_rectangle([105, end_y + 45, 1095, end_y + 445], radius=24, fill=(235, 240, 248, 200), outline=SLATE_BORDER, width=2)
    # Card 1 (Front active card)
    card_x1, card_y1 = 80, end_y + 20
    card_x2, card_y2 = 1120, end_y + 420
    draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=24, fill=CLEAN_WHITE, outline=ACCENT_BLUE, width=3)

    # Active Card Content
    draw.text((card_x1 + 45, card_y1 + 40), "CORE PLATFORM CAPABILITIES", font=get_font(18, bold=True), fill=ACCENT_DEEP_BLUE)
    font_sub = get_font(23, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=940)
    for idx, sl in enumerate(sub_lines[:2]):
        draw.text((card_x1 + 45, card_y1 + 80 + idx * 36), sl, font=font_sub, fill=TEXT_LIGHT_SECONDARY)

    # 3 Feature highlights inside bottom of front card
    f_list = (features or ["Custom Microservice Development", "Autonomous Agent Workflows", "Data-Driven Enterprise Analytics"])[:3]
    for idx, f in enumerate(f_list):
        fx = card_x1 + 45 + idx * 330
        draw.rounded_rectangle([fx, card_y1 + 190, fx + 300, card_y1 + 350], radius=16, fill=(248, 250, 252, 255), outline=SLATE_BORDER, width=1)
        draw_icon(draw, fx + 35, card_y1 + 235, ["code", "chip", "growth"][idx % 3], ACCENT_DEEP_BLUE, size=30)
        draw.text((fx + 75, card_y1 + 225), f[:22], font=get_font(18, bold=True), fill=TEXT_LIGHT_PRIMARY)
        draw.text((fx + 35, card_y1 + 280), "Production grade execution with telemetry", font=get_font(14, bold=False), fill=TEXT_LIGHT_MUTED)

    return img


# 12. Product Announcement
def render_product_announcement_layout(
    title: str,
    subtitle: str,
    features: Optional[List[str]] = None,
) -> Image.Image:
    """12. Radiant spotlight product release announcement."""
    img = create_radial_spotlight_canvas(CANVAS_SIZE, (4, 8, 24, 255), (0, 210, 255), (600, 100), radius=550)
    draw = ImageDraw.Draw(img)

    draw_jevyam_logo(draw, x=80, y=70, is_dark=True, img=img)
    draw_tagline(draw, text="NEW RELEASE  ·  ANNOUNCING", x_right=1120, y=75, is_dark=True)

    # Announcement Badge Pill
    draw.rounded_rectangle([80, 175, 430, 220], radius=22, fill=(17, 28, 56, 230), outline=ACCENT_CYAN, width=2)
    draw.text((105, 187), "★  OFFICIAL RELEASE ANNOUNCEMENT", font=get_font(14, bold=True), fill=ACCENT_CYAN)

    # Headline
    font_hl = get_font(52, bold=True)
    hl_lines = wrap_text_to_lines(draw, title, font_hl, max_width=1000)
    end_y = draw_two_tone_headline(draw, hl_lines[:3], x=80, y=250, font=font_hl, base_color=TEXT_DARK_PRIMARY, highlight_color=ACCENT_CYAN)

    # Subtitle
    font_sub = get_font(22, bold=False)
    sub_lines = wrap_text_to_lines(draw, subtitle, font_sub, max_width=950)
    for sl in sub_lines[:2]:
        draw.text((80, end_y + 15), sl, font=font_sub, fill=TEXT_DARK_SECONDARY)
        end_y += 34

    # Central Showcase Terminal Card
    showcase_y = end_y + 40
    draw.rounded_rectangle([80, showcase_y, 1120, showcase_y + 360], radius=20, fill=(12, 22, 46, 220), outline=ACCENT_BLUE, width=2)

    # Terminal Header bar
    draw.rounded_rectangle([80, showcase_y, 1120, showcase_y + 48], radius=18, fill=(20, 35, 70, 255))
    # Red, yellow, green terminal dots
    for i, col in enumerate([(244, 63, 94), (234, 179, 8), (34, 197, 94)]):
        draw.ellipse([105 + i * 22, showcase_y + 18, 119 + i * 22, showcase_y + 32], fill=col)
    draw.text((185, showcase_y + 16), "jevyam-agent // runtime v2.0-verified", font=get_font(13, bold=True), fill=TEXT_DARK_MUTED)

    # Showcase Features inside Terminal
    feats = (features or ["Idempotent Task Queues with Zero Re-Delivery", "Native Supabase Storage & Postgres Verification", "Automated Telegram Interactive Founder Approval"])[:3]
    for idx, f in enumerate(feats):
        fy = showcase_y + 75 + idx * 85
        draw.text((110, fy), f"$ engine --enable {f.lower().replace(' ', '-')[:30]}", font=get_font(18, bold=True), fill=ACCENT_CYAN)
        draw.text((110, fy + 30), f"✓ Initialized successfully with sub-second failover", font=get_font(15, bold=False), fill=TEXT_DARK_SECONDARY)

    return img


# Backwards-compatible aliases
render_tech_announcement_layout = render_dark_cyber_tech_layout
render_stats_insight_layout = render_data_visualization_layout
render_workflow_layout = render_process_flow_layout
render_company_message_layout = render_layered_cards_layout


# ==============================================================================
# MASTER RENDERER DISPATCH FUNCTION
# ==============================================================================

def render_branded_image(
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    layout: Optional[str] = "auto",
    topic: Optional[str] = None,
    caption: Optional[str] = None,
    visual_concept: Optional[str] = None,
    key_points: Optional[List[str]] = None,
    stats: Optional[List[Tuple[str, str]]] = None,
    output_path: Optional[Union[str, Path]] = None,
    previous_layouts: Optional[List[str]] = None,
    revision: int = 1,
    post_id: Optional[str] = None,
) -> bytes:
    """Master high-level renderer returning 1200x1200 PNG bytes.

    Zero-cost, Python-based, fully deterministic, supports 12 diverse layouts.
    """
    clean_title, clean_subtitle = extract_content_summary(
        title=title,
        caption=caption,
        visual_concept=visual_concept,
        topic=topic,
    )
    if subtitle:
        clean_subtitle = subtitle

    chosen_layout = detect_optimal_layout(
        title=clean_title,
        caption=caption or clean_subtitle,
        visual_concept=visual_concept,
        preferred_layout=layout,
        previous_layouts=previous_layouts,
        revision=revision,
        post_id=post_id,
    )

    # Dispatch to specific layout function
    if chosen_layout == "dark_cyber_tech":
        img = render_dark_cyber_tech_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "minimalist_editorial":
        img = render_minimalist_editorial_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "split_screen_comparison":
        img = render_split_screen_comparison_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "data_visualization":
        img = render_data_visualization_layout(clean_title, clean_subtitle, stats=stats)
    elif chosen_layout == "isometric_infrastructure":
        img = render_isometric_infrastructure_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "timeline_roadmap":
        img = render_timeline_roadmap_layout(clean_title, clean_subtitle, steps=key_points)
    elif chosen_layout == "process_flow":
        img = render_process_flow_layout(clean_title, clean_subtitle, steps=key_points)
    elif chosen_layout == "magazine_cover":
        img = render_magazine_cover_layout(clean_title, clean_subtitle, features=key_points)
    elif chosen_layout == "geometric_abstract":
        img = render_geometric_abstract_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "quote_insight":
        img = render_quote_insight_layout(clean_title, clean_subtitle, key_points=key_points)
    elif chosen_layout == "layered_cards":
        img = render_layered_cards_layout(clean_title, clean_subtitle, features=key_points)
    elif chosen_layout == "product_announcement":
        img = render_product_announcement_layout(clean_title, clean_subtitle, features=key_points)
    else:
        img = render_dark_cyber_tech_layout(clean_title, clean_subtitle, key_points=key_points)

    rgb_img = img.convert("RGB")
    buf = BytesIO()
    rgb_img.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(png_bytes)

    return png_bytes
