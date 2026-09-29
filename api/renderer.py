"""HTML template rendering engine for approval interfaces."""

import html
from pathlib import Path
from typing import Optional

from api.schemas import ApprovalPageResponse

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def render_error_page(title: str, message: str) -> str:
    """Render friendly error page."""
    template_path = TEMPLATES_DIR / "error.html"
    raw_template = template_path.read_text(encoding="utf-8")

    return (
        raw_template.replace("{{title}}", html.escape(title))
        .replace("{{message}}", html.escape(message))
    )


def render_approval_page(data: ApprovalPageResponse, token: str) -> str:
    """Render responsive founder approval interface."""
    template_path = TEMPLATES_DIR / "approval.html"
    raw_template = template_path.read_text(encoding="utf-8")

    # Render Visual Block
    if data.image_url:
        visual_block = f'<img src="{html.escape(data.image_url)}" alt="Post Visual" class="image-preview" />'
    else:
        concept = html.escape(data.visual_concept or "Visual design brief generated.")
        brief = data.image_brief or {}
        style = html.escape(str(brief.get("style", "Enterprise technical aesthetic")))
        colors = html.escape(str(brief.get("color_direction", "Neutral dark slate with tech accents")))
        text_on_img = html.escape(str(brief.get("text_on_image", "None")))
        ratio = html.escape(str(brief.get("aspect_ratio", "1:1")))

        visual_block = f"""
        <div class="visual-placeholder">
            <div class="visual-placeholder-header">
                <span>🎨 Visual Brief (Image generation provider active in later phase)</span>
            </div>
            <div class="visual-concept-body">
                <strong>Concept:</strong> {concept}
            </div>
            <div class="visual-specs">
                <div><strong>Style:</strong> {style}</div>
                <div><strong>Colors:</strong> {colors}</div>
                <div><strong>Text on Graphic:</strong> {text_on_img}</div>
                <div><strong>Aspect Ratio:</strong> {ratio}</div>
            </div>
        </div>
        """

    # Render Hashtags Block
    hashtags_html = "".join(
        f'<span class="hashtag-pill">{html.escape(tag)}</span>' for tag in data.hashtags
    )

    rendered = (
        raw_template.replace("{{post_id}}", html.escape(data.post_id))
        .replace("{{revision_number}}", str(data.revision_number))
        .replace("{{content_type}}", html.escape(data.content_type.replace("_", " ").title()))
        .replace("{{topic}}", html.escape(data.topic))
        .replace("{{angle}}", html.escape(data.angle))
        .replace("{{visual_block}}", visual_block)
        .replace("{{hook}}", html.escape(data.hook))
        .replace("{{caption}}", html.escape(data.caption))
        .replace("{{hashtags_block}}", hashtags_html)
        .replace("{{call_to_action}}", html.escape(data.call_to_action))
        .replace("{{approval_token}}", html.escape(token))
    )

    return rendered
