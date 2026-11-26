"""Preview v3 generator: Landscape Banner (1200x628) across all 8 Jevyam service fields.

Generates 8 agency-grade landscape creatives in data/preview_v3/ without
modifying production workflows, Supabase, Telegram, or LinkedIn.
"""

from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from agent.design_system import render_design_v2


FIELDS_SAMPLES = [
    {
        "filename": "01_inventory_management.png",
        "service_category": "Inventory Management Systems",
        "headline": "Real-Time Stock Control Across Every Warehouse",
        "subheadline": "Eliminate spreadsheet mismatches, track raw materials, and automate reorder alerts.",
    },
    {
        "filename": "02_crm_solutions.png",
        "service_category": "CRM Solutions",
        "headline": "Stop Losing Warm Leads Inside Scattered Inboxes",
        "subheadline": "Centralize inquiries, quotations, and automated follow-ups in one sales pipeline.",
    },
    {
        "filename": "03_custom_software.png",
        "service_category": "Custom Software Development",
        "headline": "Purpose-Built Software Around Your Exact Workflow",
        "subheadline": "Replace manual workarounds and disconnected spreadsheets with reliable internal tools.",
    },
    {
        "filename": "04_website_development.png",
        "service_category": "Website Design & Development",
        "headline": "Fast Corporate Websites Built to Convert Buyers",
        "subheadline": "Clean UI, technical SEO, and mobile-first speed that earns trust before you speak.",
    },
    {
        "filename": "05_mobile_apps.png",
        "service_category": "Mobile App Development",
        "headline": "Put Field Operations & Client Portals on Mobile",
        "subheadline": "Intuitive Android and iOS apps built for customers, vendors, and on-site teams.",
    },
    {
        "filename": "06_digital_marketing.png",
        "service_category": "Digital Marketing",
        "headline": "Better Landing Pages Turn Clicks Into Conversations",
        "subheadline": "Align technical SEO, targeted search campaigns, and clear conversion paths.",
    },
    {
        "filename": "07_ai_automation.png",
        "service_category": "AI & Business Automation",
        "headline": "Automate Repetitive Work, Keep Humans in Control",
        "subheadline": "Practical document parsing, support chatbots, and workflow automation for daily ops.",
    },
    {
        "filename": "08_it_consultancy.png",
        "service_category": "IT Consultancy & Support",
        "headline": "Scalable Architecture & Safe System Migrations",
        "subheadline": "Security audits, database migrations, automated backups, and ongoing technical support.",
    },
]


def main() -> int:
    out_dir = root_dir / "data" / "preview_v3"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_passed = True
    for s in FIELDS_SAMPLES:
        png_bytes, report = render_design_v2(
            direction="landscape_banner",
            headline=s["headline"],
            subheadline=s["subheadline"],
            service_category=s["service_category"],
            format_type="landscape",
        )
        (out_dir / s["filename"]).write_bytes(png_bytes)
        print(
            f"[{'PASS' if report.passed else 'FAIL'}] {s['filename']} | "
            f"{report.dimensions} | photo={report.human_photo_used} | issues={report.issues}"
        )
        if not report.passed:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
