"""Official Service Pillars and Content Rotation Engine for Jevyam Technologies.

Defines the eight official service categories, 10 official content formats, exact service URLs,
and an intelligent rotation system ensuring balanced LinkedIn content coverage across all agency offerings.
"""

from typing import Any, Dict, List, Optional, Tuple


OFFICIAL_SERVICE_PILLARS: List[Dict[str, Any]] = [
    {
        "id": "01",
        "name": "Inventory Management Systems",
        "slug": "inventory_management",
        "url": "https://www.jeevyamtechnologies.com/services/inventory-management.html",
        "core_focus": "Stock, warehouse, and supply chain control tailored to operational reality.",
        "capabilities": [
            "Stock and warehouse management across multiple locations",
            "Real-time purchase and sales tracking",
            "Raw material and finished goods reconciliation",
            "Scrap tracking and automatic scrap rate calculation",
            "Supplier and purchase logging with vendor purchase order lifecycles",
            "Low-stock alerts, reorder triggers, and CSV/management reports",
        ],
        "content_opportunities": [
            "Problems caused by manual inventory tracking and outdated spreadsheets",
            "Stock mismatches, stockouts, and warehouse inefficiencies",
            "Raw material and finished goods reconciliation",
            "Purchase and supplier management workflows",
            "How inventory systems improve operational business visibility",
        ],
        "business_pain_points": [
            "Working capital locked up in dead stock or untracked inventory",
            "Stockouts causing missed customer delivery deadlines and lost contracts",
            "Discrepancies between physical warehouse stock and spreadsheet counts",
            "Untracked scrap and wastage eating into gross operating margins",
        ],
        "target_audience": "Operations Directors, Warehouse Managers, Manufacturing Heads, COOs",
        "visual_themes": [
            "Warehouse stock dashboard",
            "Inventory tracking interface",
            "Raw material and finished goods visualization",
            "Stock alerts and warehouse management cards",
        ],
        "suggested_layouts": ["process_flow", "data_visualization", "split_screen_comparison", "layered_cards"],
    },
    {
        "id": "02",
        "name": "CRM Solutions",
        "slug": "crm_solutions",
        "url": "https://www.jeevyamtechnologies.com/services/crm-solutions.html",
        "core_focus": "Pipeline visibility, customer relationship nurturing, and sales operation velocity.",
        "capabilities": [
            "Customer and vendor central registry and profile management",
            "Lead tracking, qualification, and stage-by-stage deal pipelines",
            "Quotations, proposal generation, and automated follow-ups",
            "Order management and delivery status workflows",
            "Workflow automation for sales and support teams",
            "Interaction history, communications logging, and team task assignments",
        ],
        "content_opportunities": [
            "Leads getting lost in messy spreadsheets and fragmented inboxes",
            "Missed customer follow-ups and delayed quotation delivery",
            "Disorganized sales pipelines lacking stage-by-stage visibility",
            "Customer relationship management as an operational discipline",
            "Better coordination and accountability between sales team members",
        ],
        "business_pain_points": [
            "Inbound commercial leads falling through the cracks",
            "Sales reps forgetting timely customer follow-ups and quote deadlines",
            "Scattered customer data across WhatsApp chats and personal notebooks",
            "Inaccurate revenue forecasts due to fragmented deal visibility",
        ],
        "target_audience": "Sales Directors, Business Development Leaders, Founders, Managing Directors",
        "visual_themes": [
            "Sales pipeline dashboard",
            "Customer relationship interface",
            "Lead management cards",
            "Customer follow-up workflow diagram",
        ],
        "suggested_layouts": ["process_flow", "timeline_roadmap", "layered_cards", "minimalist_editorial"],
    },
    {
        "id": "03",
        "name": "Custom Software Development",
        "slug": "custom_software",
        "url": "https://www.jeevyamtechnologies.com/services/custom-software.html",
        "core_focus": "Purpose-built business software engineered around exact organizational workflows.",
        "capabilities": [
            "Custom business applications solving unique operational bottlenecks",
            "Scalable web and responsive desktop applications",
            "Local database engines, embedded storage, and robust data persistence",
            "Operational workflow automation scripts and background jobs",
            "API and third-party system integrations",
            "Maintainable, modular, and cleanly documented software architecture",
        ],
        "content_opportunities": [
            "Limitations and high recurring costs of generic off-the-shelf software",
            "Business-specific software requirements that generic SaaS cannot solve",
            "Replacing repetitive manual processes with custom internal tools",
            "Integrating disconnected business systems that refuse to talk to each other",
            "Building software around existing company workflows rather than forcing workarounds",
        ],
        "business_pain_points": [
            "Rigid off-the-shelf software forcing teams into awkward workarounds",
            "Disparate tools that don't communicate, requiring manual double entry",
            "Outgrown spreadsheet operations leading to costly operational errors",
            "Legacy desktop systems slowing down team productivity and scaling",
        ],
        "target_audience": "CTOs, Technical Co-Founders, COOs, Operations Heads, Managing Directors",
        "visual_themes": [
            "Custom business application interface",
            "Connected system architecture diagram",
            "Desktop and web application mockups",
            "Workflow automation diagrams",
        ],
        "suggested_layouts": ["isometric_infrastructure", "process_flow", "dark_cyber_tech", "split_screen_comparison"],
    },
    {
        "id": "04",
        "name": "Website Design & Development",
        "slug": "website_development",
        "url": "https://www.jeevyamtechnologies.com/services/website-development.html",
        "core_focus": "High-performance digital presence that converts visitors into qualified commercial leads.",
        "capabilities": [
            "Responsive corporate websites and brand showcases",
            "High-converting e-commerce websites and platforms",
            "Customer portals and product catalogs",
            "CMS websites with WordPress and custom admin dashboards",
            "Performance optimization and Core Web Vitals tuning",
            "Technical SEO, schema markup, and ongoing website maintenance",
        ],
        "content_opportunities": [
            "Why a corporate website needs to generate qualified business inquiries, not just look pretty",
            "Slow loading times, high bounce rates, and poor user experience",
            "E-commerce storefronts and interactive digital product catalogs",
            "Corporate website modernization and responsive design across all viewports",
            "Website performance optimization, Core Web Vitals, and technical SEO",
        ],
        "business_pain_points": [
            "Outdated corporate websites undermining enterprise brand credibility",
            "Slow page load times causing high visitor abandonment",
            "Poor mobile usability hurting conversion rates from mobile visitors",
            "Non-technical teams unable to update content without breaking the layout",
        ],
        "target_audience": "Marketing Directors, Commercial Heads, Founders, CEOs, Growth Leaders",
        "visual_themes": [
            "Premium corporate website mockups",
            "E-commerce storefront visualization",
            "Responsive desktop and mobile comparisons",
            "Website performance and UI design concepts",
        ],
        "suggested_layouts": ["split_screen_comparison", "minimalist_editorial", "product_announcement", "magazine_cover"],
    },
    {
        "id": "05",
        "name": "Mobile App Development",
        "slug": "mobile_app_development",
        "url": "https://www.jeevyamtechnologies.com/services/mobile-apps.html",
        "core_focus": "Intuitive mobile experiences empowering field teams and delighting customers.",
        "capabilities": [
            "Native and cross-platform Android applications",
            "Native and cross-platform iOS applications",
            "Customer and vendor self-service mobile portals",
            "Field utility applications and field operator data logging",
            "App Store and Google Play store publishing",
            "Continuous application support, updates, and maintenance",
        ],
        "content_opportunities": [
            "Mobile-first operational workflows for modern businesses",
            "Customer and vendor self-service mobile applications",
            "Field team productivity and real-time site reporting",
            "Replacing paper-based logs and clipboard inspections with mobile tools",
            "Building business-critical applications for Android and iOS",
        ],
        "business_pain_points": [
            "Field technicians and inspectors relying on paper clipboards and manual retyping",
            "Lack of a direct, branded mobile interface for high-value enterprise customers",
            "Unsynchronized field data leading to invoice delays and client disputes",
            "Mobile applications crashing or failing without reliable offline capability",
        ],
        "target_audience": "Product Managers, Operations Executives, Field Service Directors, Founders",
        "visual_themes": [
            "Realistic smartphone mockups",
            "Mobile business dashboards",
            "Customer and vendor application screens",
            "Field operator mobile interfaces",
        ],
        "suggested_layouts": ["product_announcement", "split_screen_comparison", "process_flow", "minimalist_editorial"],
    },
    {
        "id": "06",
        "name": "Digital Marketing",
        "slug": "digital_marketing",
        "url": "https://www.jeevyamtechnologies.com/services/digital-marketing.html",
        "core_focus": "Measurable online growth, targeted acquisition, and commercial brand authority.",
        "capabilities": [
            "Search engine optimization (SEO) and local search presence",
            "Google Search and Display Ads with strict budget management",
            "Social media management and B2B LinkedIn content creation",
            "Strategic content creation and brand positioning",
            "Conversion tracking, analytics dashboards, and commercial ROI measurement",
            "Continuous performance optimization and campaign iteration",
        ],
        "content_opportunities": [
            "Improving online visibility and organic search discovery",
            "Technical SEO and dominating local search rankings",
            "B2B LinkedIn marketing that builds commercial pipeline, not just likes",
            "Paid search advertising strategy and avoiding wasted ad spend",
            "Content consistency and positioning as an industry authority",
            "Measuring marketing performance and real commercial ROI",
        ],
        "business_pain_points": [
            "Wasting marketing budget on vanity impressions with zero commercial leads",
            "Inconsistent digital presence failing to build market authority and trust",
            "Competitors consistently outranking the company for high-intent queries",
            "Inability to track which marketing channels actually generate revenue",
        ],
        "target_audience": "Growth Heads, Marketing Directors, Business Owners, Founders, Commercial Leads",
        "visual_themes": [
            "SEO analytics dashboards",
            "Search performance visualizations",
            "Social media campaign concepts",
            "Digital growth and conversion analytics",
        ],
        "suggested_layouts": ["data_visualization", "timeline_roadmap", "geometric_abstract", "magazine_cover"],
    },
    {
        "id": "07",
        "name": "AI & Business Automation",
        "slug": "ai_automation",
        "url": "https://www.jeevyamtechnologies.com/services/ai-automation.html",
        "core_focus": "Pragmatic automation and intelligent tools eliminating repetitive operational friction.",
        "capabilities": [
            "24/7 intelligent customer support chatbots and conversational agents",
            "Automated document, receipt, and invoice parsing pipelines",
            "Language translation pipelines and multilingual content workflows",
            "Custom business intelligence scripts and automated data extraction",
            "Document and data automation eliminating routine transcription",
            "Tailored AI workflows engineered for specific company operational bottlenecks",
        ],
        "content_opportunities": [
            "Automating repetitive administrative and back-office work",
            "Automated document, invoice, and receipt processing",
            "AI-powered customer support that answers routine questions instantly",
            "Practical business applications of AI versus empty industry hype",
            "Reducing manual data entry errors and speeding turnaround times",
            "Building custom automation workflows that connect existing business tools",
        ],
        "business_pain_points": [
            "Staff spending hours every week manually transcribing PDFs and invoices",
            "Support inboxes flooded with identical routine questions around the clock",
            "Delayed management reporting due to manual data aggregation across tools",
            "Confusion from AI hype without knowing what practically works in production",
        ],
        "target_audience": "COOs, IT Directors, Support Operations Heads, Managing Directors, Founders",
        "visual_themes": [
            "AI chatbot interfaces",
            "Document processing workflows",
            "Automated data extraction concepts",
            "Connected business automation diagrams",
        ],
        "suggested_layouts": ["process_flow", "dark_cyber_tech", "isometric_infrastructure", "layered_cards"],
    },
    {
        "id": "08",
        "name": "IT Consultancy & Support",
        "slug": "it_consultancy",
        "url": "https://www.jeevyamtechnologies.com/services/it-consultancy.html",
        "core_focus": "Strategic technical guidance, infrastructure stability, and operational peace of mind.",
        "capabilities": [
            "Software architecture planning and system design reviews",
            "Legacy database migration, schema refactoring, and cloud modernization",
            "Comprehensive IT security audits and vulnerability assessments",
            "Software maintenance and performance monitoring",
            "Cloud hosting setup, managed environments, and backup automation",
            "Data privacy safeguards and on-call technical maintenance",
        ],
        "content_opportunities": [
            "Legacy system modernization and phasing out brittle software",
            "Database migration without data loss or prolonged downtime",
            "Cloud infrastructure planning, scalability, and disaster recovery",
            "Automated backup and business continuity best practices",
            "Data privacy and security assessments for modern businesses",
            "Ongoing software maintenance and senior technical support",
        ],
        "business_pain_points": [
            "Aging legacy software holding back company expansion and hiring",
            "Fear of catastrophic data loss due to untested manual backup routines",
            "Unidentified security vulnerabilities and compliance risks",
            "Lack of dedicated senior engineering leadership to guide technology investments",
        ],
        "target_audience": "CEOs, Managing Directors, CTOs, IT Heads, Enterprise Leaders",
        "visual_themes": [
            "Cloud infrastructure diagrams",
            "Database migration concepts",
            "Secure enterprise architecture blueprints",
            "Backup and monitoring dashboards",
        ],
        "suggested_layouts": ["isometric_infrastructure", "dark_cyber_tech", "split_screen_comparison", "process_flow"],
    },
]

# The 10 Official Content Formats
OFFICIAL_CONTENT_FORMATS: List[str] = [
    "Problem → Solution",
    "Service Spotlight",
    "Educational Post",
    "Before vs After",
    "Business Pain Point",
    "Feature Breakdown",
    "Industry Scenario",
    "Myth vs Reality",
    "Question-Based Engagement",
    "Solution Showcase",
]

# Alias map to support backwards compatibility
CONTENT_FORMAT_ALIASES: Dict[str, str] = {
    "problem to practical solution": "Problem → Solution",
    "common operational mistakes": "Business Pain Point",
    "educational explainer": "Educational Post",
    "industry-specific use case": "Industry Scenario",
    "technology insight": "Educational Post",
    "service spotlight": "Service Spotlight",
    "before-and-after workflow concept": "Before vs After",
    "business discussion prompt": "Question-Based Engagement",
    "feature breakdown": "Feature Breakdown",
    "myth vs reality": "Myth vs Reality",
    "solution showcase": "Solution Showcase",
}


def normalize_content_format(raw_format: Optional[str]) -> str:
    """Normalize a content format string to one of the 10 official formats."""
    if not raw_format:
        return "Problem → Solution"
    clean = raw_format.strip()
    if clean in OFFICIAL_CONTENT_FORMATS:
        return clean
    clean_lower = clean.lower()
    for alias, canonical in CONTENT_FORMAT_ALIASES.items():
        if alias in clean_lower or clean_lower in alias:
            return canonical
    return "Problem → Solution"


def get_pillar_by_name(name_or_slug: str) -> Optional[Dict[str, Any]]:
    """Match a pillar by exact name, slug, URL, id, or substring."""
    if not name_or_slug:
        return None
    clean = str(name_or_slug).strip().lower()
    for p in OFFICIAL_SERVICE_PILLARS:
        if p["slug"].lower() == clean or p["name"].lower() == clean or p["id"] == clean:
            return p
        if clean in p["name"].lower() or p["name"].lower() in clean:
            return p
        if clean in p.get("url", "").lower():
            return p
    return None


def get_service_url(pillar_name_or_slug: str) -> str:
    """Get the official website URL for a service pillar."""
    pillar = get_pillar_by_name(pillar_name_or_slug)
    if pillar and "url" in pillar:
        return pillar["url"]
    return "https://www.jeevyamtechnologies.com/"


def calculate_pillar_rotation(
    previous_posts: List[Any],
    include_format: bool = False,
) -> Any:
    """Analyze recent posts to determine the next prioritized service pillar and content format.

    Rules:
    1. Strictly excludes the immediately previous post's service pillar to prevent consecutive repeats.
    2. Cycles through all eight official pillars in order:
       01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 07 -> 08, then repeats.
    3. Accounts for historical coverage counts, prioritizing least-covered pillars.
    4. Rotates content format to avoid consecutive identical formats.

    Returns:
        If include_format is False (default for backwards compatibility):
            Tuple of (recommended_pillar_dict, recent_covered_pillars_list).
        If include_format is True:
            Tuple of (recommended_pillar_dict, recommended_content_format, recent_covered_pillars_list).
    """
    pillar_counts: Dict[str, int] = {p["name"]: 0 for p in OFFICIAL_SERVICE_PILLARS}
    recent_pillars_ordered: List[str] = []
    recent_formats_ordered: List[str] = []

    for post in previous_posts:
        content_type = ""
        topic = ""
        service_category = ""
        content_format = ""

        if isinstance(post, dict):
            content_type = post.get("content_type", "") or ""
            topic = post.get("topic", "") or ""
            service_category = post.get("service_category", "") or ""
            content_format = post.get("content_format", "") or ""
            # Check image brief if present
            brief = post.get("image_brief") or {}
            if isinstance(brief, dict):
                service_category = service_category or brief.get("service_pillar") or brief.get("service_category", "")
                content_format = content_format or brief.get("content_format", "")
        else:
            content_type = getattr(post, "content_type", "") or ""
            topic = getattr(post, "topic", "") or ""
            service_category = getattr(post, "service_category", "") or ""
            content_format = getattr(post, "content_format", "") or ""
            brief = getattr(post, "image_brief", {}) or {}
            if isinstance(brief, dict):
                service_category = service_category or brief.get("service_pillar") or brief.get("service_category", "")
                content_format = content_format or brief.get("content_format", "")

        # Match pillar
        matched_pillar = None
        if service_category:
            p = get_pillar_by_name(service_category)
            if p:
                matched_pillar = p["name"]

        if not matched_pillar:
            for p in OFFICIAL_SERVICE_PILLARS:
                if p["name"].lower() in content_type.lower() or p["slug"].lower() in content_type.lower():
                    matched_pillar = p["name"]
                    break
                if p["name"].lower() in topic.lower():
                    matched_pillar = p["name"]
                    break

        if matched_pillar:
            pillar_counts[matched_pillar] += 1
            recent_pillars_ordered.append(matched_pillar)

        # Match format
        if content_format:
            recent_formats_ordered.append(normalize_content_format(content_format))
        elif " | " in content_type:
            parts = content_type.split(" | ", 1)
            if len(parts) > 1:
                recent_formats_ordered.append(normalize_content_format(parts[1]))

    # Determine immediate previous pillar (cannot be repeated immediately)
    last_pillar = recent_pillars_ordered[0] if recent_pillars_ordered else None
    last_format = recent_formats_ordered[0] if recent_formats_ordered else None

    # Filter out immediately preceding pillar from immediate candidates if we have other pillars
    eligible_pillars = [
        p for p in OFFICIAL_SERVICE_PILLARS
        if p["name"] != last_pillar
    ]
    if not eligible_pillars:
        eligible_pillars = OFFICIAL_SERVICE_PILLARS

    # Sort eligible by count ascending, then by official order
    sorted_eligible = sorted(
        eligible_pillars,
        key=lambda p: (pillar_counts[p["name"]], OFFICIAL_SERVICE_PILLARS.index(p)),
    )
    recommended_pillar = sorted_eligible[0]

    # Select recommended content format (rotate away from last format)
    eligible_formats = [f for f in OFFICIAL_CONTENT_FORMATS if f != last_format]
    # Pick next format in sequence
    format_idx = 0
    if last_format in OFFICIAL_CONTENT_FORMATS:
        format_idx = (OFFICIAL_CONTENT_FORMATS.index(last_format) + 1) % len(OFFICIAL_CONTENT_FORMATS)
        rec_format = OFFICIAL_CONTENT_FORMATS[format_idx]
    else:
        rec_format = eligible_formats[0] if eligible_formats else OFFICIAL_CONTENT_FORMATS[0]

    # Deduplicated list of recent pillars for reporting
    seen = set()
    deduped_recent: List[str] = []
    for p_name in recent_pillars_ordered:
        if p_name not in seen:
            seen.add(p_name)
            deduped_recent.append(p_name)

    if include_format:
        return recommended_pillar, rec_format, deduped_recent
    return recommended_pillar, deduped_recent


def get_next_content_target(previous_posts: List[Any]) -> Dict[str, Any]:
    """Return dictionary with recommended pillar, format, service url, and history."""
    p, fmt, recent = calculate_pillar_rotation(previous_posts, include_format=True)
    return {
        "pillar": p,
        "format": fmt,
        "recent_pillars": recent,
        "service_url": p.get("url", "https://www.jeevyamtechnologies.com/"),
    }


def format_pillars_context_for_prompt() -> str:
    """Format the 8 official pillars for injection into strategist prompt."""
    lines = []
    for p in OFFICIAL_SERVICE_PILLARS:
        lines.append(f"### SERVICE {p['id']} — {p['name']}")
        lines.append(f"Official URL: {p['url']}")
        lines.append(f"Core Focus: {p['core_focus']}")
        lines.append("Official Capabilities:")
        for cap in p["capabilities"]:
            lines.append(f"  - {cap}")
        lines.append("Content Opportunities:")
        for opp in p.get("content_opportunities", []):
            lines.append(f"  - {opp}")
        lines.append(f"Target Audience: {p['target_audience']}")
        lines.append("")
    return "\n".join(lines).strip()
