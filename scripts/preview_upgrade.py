"""Preview-only script for Jevyam Technologies upgraded content & Canva creative engine.

Generates 3 sample posts from different service pillars using live Gemini (without touching
Supabase, LinkedIn, or Telegram) and renders all 6 Canva-style templates + 1080x1350
carousel slides into data/preview_upgrade/ for visual inspection.
"""

import json
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from agent.canva_templates import (
    CANVA_TEMPLATES,
    render_canva_template,
    render_carousel_slides,
)
from agent.image_generator import generate_image_brief
from agent.knowledge import load_company_knowledge
from agent.pillars import get_pillar_by_name
from agent.quality_validator import validate_post_quality
from agent.strategist import ContentIdea
from agent.writer import generate_linkedin_post
from integrations.gemini import get_gemini_client


SAMPLE_IDEAS = [
    ContentIdea(
        topic="Why a slow business website quietly loses qualified customer inquiries",
        angle="Slow load times and template bloat hurt search visibility and buyer trust before a prospect ever reads your offer.",
        content_type="Website Design & Development | Problem → Solution",
        service_category="Website Design & Development",
        content_format="Problem → Solution",
        target_audience="Founders, Managing Directors, Marketing Heads",
        reason="Directly addresses commercial lead loss on corporate websites.",
    ),
    ContentIdea(
        topic="How automated follow-ups stop inbound sales leads from slipping away",
        angle="Most B2B teams don't have a lead generation problem—they have a follow-up and pipeline visibility problem.",
        content_type="CRM Solutions | Educational Post",
        service_category="CRM Solutions",
        content_format="Educational Post",
        target_audience="Sales Directors, Founders, Business Development Leads",
        reason="Addresses everyday CRM pipeline leakage.",
    ),
    ContentIdea(
        topic="When should a growing business move from spreadsheets to custom software?",
        angle="Spreadsheets work early on, but manual copy-pasting across departments creates errors and slows down fulfillment.",
        content_type="Custom Software Development | Before vs After",
        service_category="Custom Software Development",
        content_format="Before vs After",
        target_audience="COOs, Operations Managers, Founders",
        reason="Helps growing businesses recognize the inflection point for custom software.",
    ),
]


def main() -> int:
    out_dir = root_dir / "data" / "preview_upgrade"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = get_gemini_client()
    knowledge = load_company_knowledge()
    results = []

    for idx, idea in enumerate(SAMPLE_IDEAS, 1):
        print(f"\n[{idx}/3] Generating post for: {idea.service_category} ...")
        post = generate_linkedin_post(
            client=client,
            company_knowledge=knowledge,
            idea=idea,
            previous_posts=[],
        )
        q_res = validate_post_quality(
            topic=idea.topic,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            call_to_action=post.call_to_action,
            service_category=idea.service_category,
        )
        if not q_res.passed:
            print(f"  Quality gate flagged issues (score={q_res.score}): {q_res.issues}. Regenerating...")
            post = generate_linkedin_post(
                client=client,
                company_knowledge=knowledge,
                idea=idea,
                previous_posts=[],
                quality_feedback="\n".join(q_res.issues),
            )
            q_res = validate_post_quality(
                topic=idea.topic,
                hook=post.hook,
                caption=post.caption,
                hashtags=post.hashtags,
                call_to_action=post.call_to_action,
                service_category=idea.service_category,
            )

        brief = generate_image_brief(
            client=client,
            topic=idea.topic,
            angle=idea.angle,
            hook=post.hook,
            caption=post.caption,
            brand_voice=knowledge.brand_voice,
            service_category=idea.service_category,
        )

        template_id = brief.layout if brief.layout in CANVA_TEMPLATES else "editorial_insight"
        png_bytes = render_canva_template(
            template_id=template_id,
            headline=brief.headline or brief.text_on_image,
            subheadline=brief.subheadline or "",
            key_points=brief.key_points,
            problem_points=brief.problem_points,
            solution_points=brief.solution_points,
            architecture_nodes=brief.architecture_nodes,
            carousel_slides=brief.carousel_slides,
            service_category=idea.service_category,
            cta_text=brief.cta_text or "jeevyamtechnologies.com",
            caption=post.caption,
        )
        img_path = out_dir / f"sample_{idx}_{template_id}.png"
        img_path.write_bytes(png_bytes)

        results.append({
            "service_category": idea.service_category,
            "topic": idea.topic,
            "quality_score": q_res.score,
            "quality_passed": q_res.passed,
            "quality_issues": q_res.issues,
            "hook": post.hook,
            "caption": post.caption,
            "hashtags": post.hashtags,
            "template_id": template_id,
            "image_path": str(img_path),
            "headline": brief.headline or brief.text_on_image,
        })
        print(f"  Saved {img_path.name} (quality={q_res.score}, template={template_id})")

    # Also render all 6 templates + 1080x1350 carousel slides for complete verification
    carousel_bytes = render_carousel_slides(
        headline="5 Signs Your Business Has Outgrown Spreadsheets",
        subheadline="When manual sheets start costing more time than they save.",
        slides=[
            {"title": "Version Confusion Across Teams", "body": "Multiple copies of the same sheet circulate via email and WhatsApp."},
            {"title": "Manual Double Data Entry", "body": "Staff re-type orders from sales into inventory and billing every day."},
            {"title": "Zero Real-Time Visibility", "body": "Founders wait until week-end reconciliation to spot stock or cash gaps."},
        ],
        service_category="Custom Software Development",
    )
    for s_idx, s_bytes in enumerate(carousel_bytes, 1):
        (out_dir / f"carousel_slide_{s_idx}.png").write_bytes(s_bytes)

    (out_dir / "preview_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nPreview complete! Output saved to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
