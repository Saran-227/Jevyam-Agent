"""Standalone smoke test for 12 diverse Jevyam Technologies branded image layouts.

Renders 12 distinct branded layouts locally using Pillow:
1. Dark cyber/neon technology
2. Minimalist editorial typography
3. Split-screen comparison
4. Data visualization / statistics
5. Isometric infrastructure illustration
6. Timeline / roadmap
7. Process flow diagram
8. Bold magazine cover
9. Geometric abstract composition
10. Quote / insight card
11. Layered cards
12. Product announcement

Does NOT call Gemini, Supabase, Telegram, WhatsApp, or LinkedIn.
Validates PNG dimensions (1200x1200) and headers.
"""

import sys
from pathlib import Path
from PIL import Image

# Ensure project root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from agent.branded_renderer import render_branded_image, ALL_LAYOUTS


def run_smoke_test() -> int:
    output_dir = root_dir / "data" / "smoke_images"
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {
            "layout": "dark_cyber_tech",
            "filename": "01_dark_cyber_tech.png",
            "title": "Zero-Trust Neural Orchestration",
            "caption": "Deep-tech autonomous systems running on resilient distributed event backbones.",
            "visual_concept": "High-availability cyber matrix core with glowing neon traces",
            "key_points": ["Deterministic Routing", "Memory Isolation", "Zero-Latency Failover"],
        },
        {
            "layout": "minimalist_editorial",
            "filename": "02_minimalist_editorial.png",
            "title": "The Architecture of Silent Reliability",
            "caption": "True enterprise robustness is not about reacting to incidents, but designing systems where failure is structurally impossible.",
            "visual_concept": "Minimalist editorial essay with clean typography and margin rules",
            "key_points": ["State boundaries precede code", "Idempotency over retry loops"],
        },
        {
            "layout": "split_screen_comparison",
            "filename": "03_split_screen_comparison.png",
            "title": "Legacy Batch Cron vs Modern Event Mesh",
            "caption": "How leading engineering organizations eliminate brittle scheduling with idempotent agents.",
            "visual_concept": "Comparison split screen showing legacy fragility vs modern AI resilience",
            "key_points": ["Sub-second event loops", "Self-healing worker nodes", "Zero duplicate writes", "Live audit telemetry"],
        },
        {
            "layout": "data_visualization",
            "filename": "04_data_visualization.png",
            "title": "Proven Enterprise Performance Metrics",
            "caption": "Benchmarked across mission-critical enterprise workflows in banking and cloud infrastructure.",
            "visual_concept": "99.9% reliability KPI paired with bar chart comparison",
            "stats": [("99.99%", "System Availability"), ("10x", "Throughput Velocity"), ("0%", "Silent Data Loss"), ("45%", "Infrastructure Savings")],
        },
        {
            "layout": "isometric_infrastructure",
            "filename": "05_isometric_infrastructure.png",
            "title": "Distributed Multi-Agent Architecture",
            "caption": "Tiered architectural blueprint from API ingress through stateful event queues to vector database consensus.",
            "visual_concept": "Layered 3D isometric platform cubes connected with glowing cyan trace lines",
            "key_points": ["Idempotent Queues", "Vector Consensus", "Resilient State Mesh"],
        },
        {
            "layout": "timeline_roadmap",
            "filename": "06_timeline_roadmap.png",
            "title": "Enterprise AI Transformation Journey",
            "caption": "From systems auditing to production-scale multi-agent deployments.",
            "visual_concept": "Chronological milestone roadmap with 4 progress stages",
            "key_points": [
                "Phase 01: Architecture & Security Audit",
                "Phase 02: Resilient State & Pipeline Blueprint",
                "Phase 03: Autonomous Agent Orchestration",
                "Phase 04: Production Scale & Live Telemetry",
            ],
        },
        {
            "layout": "process_flow",
            "filename": "07_process_flow.png",
            "title": "From Data Ingestion to Verified Execution",
            "caption": "A 4-stage pipeline that guarantees message deduplication and deterministic outcomes.",
            "visual_concept": "Connected horizontal pipeline containers with directional chevrons",
            "key_points": [
                "1. Real-time Event Ingestion & Schema Parse",
                "2. Dynamic Agent Task Decomposition",
                "3. Policy & Security Verification Gate",
                "4. Idempotent Target State Execution",
            ],
        },
        {
            "layout": "magazine_cover",
            "filename": "08_magazine_cover.png",
            "title": "The Autonomous Enterprise // Special Report",
            "caption": "How AI marketing and operational agents are reshaping B2B technology operations in 2026.",
            "visual_concept": "Bold publication cover with masthead, teaser box, and barcode",
            "key_points": ["Multi-Agent Guardrails", "Zero-Cost Visual Rendering", "Idempotent Event Systems"],
        },
        {
            "layout": "geometric_abstract",
            "filename": "09_geometric_abstract.png",
            "title": "Turning Abstract Ideas into Scalable Impact",
            "caption": "We build custom technology systems that help modern enterprises move faster and build with confidence.",
            "visual_concept": "Dynamic angled geometric ribbons, radar rings, and translucent glass card",
            "key_points": ["Precision Engineering", "Scalable Foundations", "Measurable Business Value"],
        },
        {
            "layout": "quote_insight",
            "filename": "10_quote_insight.png",
            "title": "Simplicity is the prerequisite for reliability.",
            "caption": "When distributed workflows become complex, elegance in failure isolation is what separates enduring platforms from fragile scripts.",
            "visual_concept": "Executive quote card with giant electric cyan quotation marks",
            "key_points": ["Executive Insight", "System Design Philosophy"],
        },
        {
            "layout": "layered_cards",
            "filename": "11_layered_cards.png",
            "title": "Three Foundational Pillars of Modern Engineering",
            "caption": "Our core principles for building resilient, future-proof enterprise software solutions.",
            "visual_concept": "Layered cascading cards with offset angles and drop shadows",
            "key_points": ["Custom Cloud Architecture", "Autonomous Multi-Agent AI", "Data-Driven Platform Growth"],
        },
        {
            "layout": "product_announcement",
            "filename": "12_product_announcement.png",
            "title": "Announcing Jevyam Agent Runtime v2.0",
            "caption": "A zero-cost, fully autonomous marketing and operational agent engine for LinkedIn company pages.",
            "visual_concept": "Radiant spotlight launch graphic with terminal code showcase card",
            "key_points": ["Zero-Cost Image Generator", "Supabase Persistent Audit", "Interactive Telegram Approval"],
        },
    ]

    print("=" * 75)
    print("JEVYAM TECHNOLOGIES BRANDED IMAGE GENERATOR - 12 LAYOUT SMOKE TEST")
    print("=" * 75)

    all_passed = True
    for idx, sample in enumerate(samples, 1):
        target_path = output_dir / sample["filename"]
        print(f"\n[{idx}/12] Generating layout '{sample['layout']}' -> {target_path.name}...")

        try:
            png_bytes = render_branded_image(
                title=sample["title"],
                caption=sample["caption"],
                visual_concept=sample["visual_concept"],
                key_points=sample.get("key_points"),
                stats=sample.get("stats"),
                layout=sample["layout"],
                output_path=target_path,
            )

            # Verification
            assert target_path.exists(), f"Output file does not exist: {target_path}"
            assert target_path.stat().st_size > 0, "Output file is empty"
            assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid PNG header"

            with Image.open(target_path) as img:
                w, h = img.size
                fmt = img.format
                assert (w, h) == (1200, 1200), f"Expected (1200, 1200), got ({w}, {h})"
                assert fmt == "PNG", f"Expected PNG, got {fmt}"

            print(f"       Status: OK")
            print(f"       Dimensions: {w}x{h} ({fmt})")
            print(f"       Size: {len(png_bytes) / 1024:.1f} KB")
            print(f"       Path: {target_path.resolve()}")

        except Exception as e:
            print(f"       Status: FAILED -> {e}")
            all_passed = False

    print("\n" + "=" * 75)
    if all_passed:
        print(f"ALL {len(samples)} DIVERSE SMOKE TEST IMAGES GENERATED & VALIDATED.")
        print(f"Output Directory: {output_dir.resolve()}")
        print("=" * 75)
        return 0
    else:
        print("SMOKE TEST FAILED.")
        print("=" * 75)
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
