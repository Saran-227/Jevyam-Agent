"""Preview-only generator for Jevyam Technologies Design System 2.0.

Generates 8 diverse agency-grade creatives across all 8 Jevyam services and
8 creative directions into data/preview_v2/ for founder & admin review.
Does NOT touch production workflows, Supabase, Telegram, or LinkedIn.
"""

from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from agent.design_system import render_design_v2


SAMPLES = [
    {
        "filename": "01_website_editorial_collage.png",
        "direction": "editorial_collage",
        "service_category": "Website Design & Development",
        "headline": "Your Website Should Win Trust Before You Speak",
        "subheadline": "Slow templates and cluttered pages quietly push serious buyers to competitors.",
        "key_points": ["Fast mobile page speed", "Clear conversion hierarchy"],
        "format_type": "square",
    },
    {
        "filename": "02_crm_human_campaign.png",
        "direction": "human_centric_campaign",
        "service_category": "CRM Solutions",
        "headline": "Stop Losing Warm Leads Inside Scattered Inboxes",
        "subheadline": "Give your sales team one clear pipeline with automated follow-ups.",
        "key_points": ["Centralized lead tracking", "Timely quotation reminders"],
        "format_type": "square",
    },
    {
        "filename": "03_custom_software_bold_poster.png",
        "direction": "bold_typography_poster",
        "service_category": "Custom Software Development",
        "headline": "Outgrow Spreadsheets With Purpose-Built Software",
        "subheadline": "Stop forcing unique daily operations into rigid off-the-shelf tools.",
        "key_points": [],
        "format_type": "square",
    },
    {
        "filename": "04_inventory_split_editorial.png",
        "direction": "split_editorial",
        "service_category": "Inventory Management Systems",
        "headline": "Know What Is In Stock Without Guessing",
        "subheadline": "Real-time warehouse tracking, raw material reconciliation, and reorder alerts.",
        "key_points": ["Multi-location stock visibility", "Automated low-stock alerts"],
        "format_type": "portrait",
    },
    {
        "filename": "05_marketing_business_metrics.png",
        "direction": "business_metrics",
        "service_category": "Digital Marketing",
        "headline": "Traffic Means Nothing Without Clear Conversion",
        "subheadline": "Align technical SEO, targeted search campaigns, and focused landing pages.",
        "key_points": ["Technical SEO Foundation", "Focused Landing Pages", "Tracked Lead Inquiries"],
        "format_type": "square",
    },
    {
        "filename": "06_mobile_service_showcase.png",
        "direction": "creative_service_showcase",
        "service_category": "Mobile App Development",
        "headline": "Put Your Operations in Every Team Member's Pocket",
        "subheadline": "Android and iOS apps built for field teams, vendors, and customers.",
        "key_points": ["Customer Self-Service Portals", "Field Inspection Logging", "Reliable Offline Sync"],
        "format_type": "square",
    },
    {
        "filename": "07_ai_visual_storytelling.png",
        "direction": "visual_storytelling",
        "service_category": "AI & Business Automation",
        "headline": "Automate Repetitive Work, Keep Humans in Control",
        "subheadline": "Practical workflow automation for document parsing, support, and internal handoffs.",
        "problem_points": ["Manual invoice & data re-entry", "Slow routine customer replies"],
        "solution_points": ["Automated document extraction", "24/7 guided support workflows"],
        "format_type": "square",
    },
    {
        "filename": "08_it_multi_panel_agency.png",
        "direction": "multi_panel_agency",
        "service_category": "IT Consultancy & Support",
        "headline": "Build Infrastructure That Scales Without Surprises",
        "subheadline": "Architecture reviews, safe database migrations, backups, and ongoing support.",
        "key_points": ["Zero-downtime migration planning", "Automated backup & security audits"],
        "format_type": "portrait",
    },
    {
        "filename": "09_crm_diagonal_slice.png",
        "direction": "diagonal_slice",
        "service_category": "CRM Solutions",
        "headline": "Turn Scattered Inquiries Into a Clear Pipeline",
        "subheadline": "Track every lead, quotation, and follow-up in one place.",
        "key_points": [],
        "format_type": "square",
    },
    {
        "filename": "10_website_magazine_quote.png",
        "direction": "magazine_quote",
        "service_category": "Website Design & Development",
        "headline": "Your corporate website should answer buyer questions in seconds, not test their patience.",
        "subheadline": "Clean architecture, technical SEO, and mobile-first speed built for commercial inquiries.",
        "key_points": [],
        "format_type": "square",
    },
    {
        "filename": "11_custom_software_timeline.png",
        "direction": "timeline_blueprint",
        "service_category": "Custom Software Development",
        "headline": "How Custom Software Replaces Manual Workarounds",
        "subheadline": "Three practical steps from spreadsheet chaos to a unified internal tool.",
        "key_points": [
            "Map exact team workflows & bottlenecks",
            "Build a centralized web or desktop app",
            "Connect billing, stock & reporting APIs",
        ],
        "format_type": "portrait",
    },
    {
        "filename": "12_mobile_floating_hero.png",
        "direction": "floating_frame_hero",
        "service_category": "Mobile App Development",
        "headline": "Give Customers & Field Teams a Faster Way to Work",
        "subheadline": "Clean Android and iOS apps integrated directly with your backend.",
        "key_points": [],
        "format_type": "square",
    },
    {
        "filename": "13_marketing_landscape_banner.png",
        "direction": "landscape_banner",
        "service_category": "Digital Marketing",
        "headline": "Better Landing Pages Turn Paid Clicks Into Conversations",
        "subheadline": "Align search campaigns, technical SEO, and clear conversion paths.",
        "key_points": [],
        "format_type": "landscape",
    },
    {
        "filename": "14_inventory_checklist_portrait.png",
        "direction": "checklist_card",
        "service_category": "Inventory Management Systems",
        "headline": "What to Automate in Warehouse & Stock Control",
        "subheadline": "Eliminate manual counts and late reorder surprises.",
        "key_points": [
            "Real-time multi-warehouse stock levels",
            "Raw material & finished goods reconciliation",
            "Automated low-stock reorder alerts",
            "Supplier purchase order tracking",
        ],
        "format_type": "portrait",
    },
]


def main() -> int:
    out_dir = root_dir / "data" / "preview_v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_passed = True
    for s in SAMPLES:
        png_bytes, report = render_design_v2(
            direction=s["direction"],
            headline=s["headline"],
            subheadline=s["subheadline"],
            key_points=s.get("key_points"),
            service_category=s["service_category"],
            format_type=s.get("format_type", "square"),
            problem_points=s.get("problem_points"),
            solution_points=s.get("solution_points"),
        )
        out_path = out_dir / s["filename"]
        out_path.write_bytes(png_bytes)
        print(
            f"[{'PASS' if report.passed else 'FAIL'}] {s['filename']} | "
            f"{report.dimensions} | photo={report.human_photo_used} | issues={report.issues}"
        )
        if not report.passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
