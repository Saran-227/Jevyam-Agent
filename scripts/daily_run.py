"""Daily automated run entry point for Jevyam Technologies AI Marketing Agent (Phase 6).

Usage:
    python scripts/daily_run.py --dry-run
    python scripts/daily_run.py --live
    python scripts/daily_run.py --dry-run --force
    python scripts/daily_run.py --mock-gemini --in-memory
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.exceptions import ConfigurationError, DailyOrchestrationError
from agent.orchestrator import DailyOrchestrator, DailyRunResult
from agent.scheduler import DailyScheduler, SchedulerStateStore
from config.settings import settings
from database.repositories import get_repository_manager


def configure_logging(verbose: bool = False) -> None:
    """Configure clean, structured logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Remove existing handlers to avoid duplicates
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)


def create_mock_gemini_client() -> Any:
    """Create a simulated Gemini AI client for completely offline/mock testing."""
    from agent.strategist import ContentIdea
    from agent.writer import LinkedInPostContent
    from agent.image_generator import ImageBrief

    client = MagicMock()
    mock_ideas = [
        {
            "topic": "Why Vector Search Needs Hybrid Keyword Inverted Indexes",
            "angle": "Information retrieval trade-offs in modern RAG systems",
            "content_type": "software engineering",
            "target_audience": "CTOs and Lead Engineers",
            "reason": "Clear architectural insights on retrieval reliability.",
        },
        {
            "topic": "Deterministic State Machines for AI Agent Safety",
            "angle": "Bounding agentic executions with finite state machines",
            "content_type": "AI and engineering",
            "target_audience": "Founders and Engineering Leaders",
            "reason": "Reinforces pragmatic AI deployment safety.",
        },
        {
            "topic": "Decoupled Message Queuing with Dead-Letter Handling",
            "angle": "Reliable queue worker architectures in fintech",
            "content_type": "software engineering",
            "target_audience": "Tech Leads and Backend Engineers",
            "reason": "Enterprise queue reliability principles.",
        },
        {
            "topic": "Why Event-Driven Microservices Beat Monolithic Cron Pipelines",
            "angle": "Event-driven automation architectures decouple state and prevent silent job dropouts",
            "content_type": "software engineering",
            "target_audience": "CTOs, Technical Leads, and Infrastructure Engineers",
            "reason": "Highlights enterprise engineering reliability and modern cloud architecture principles.",
        },
        {
            "topic": "Deterministic Guardrails for Production LLM Deployments",
            "angle": "Why probabilistic LLM outputs must be bounded by deterministic schema and human validation",
            "content_type": "AI and engineering",
            "target_audience": "Founders, Engineering Leaders, and Operations Heads",
            "reason": "Reinforces pragmatic AI deployment over reckless unmonitored automation.",
        },


    ]

    idea_cursor = {"index": 0}

    def mock_generate_content(*args, **kwargs):
        config = kwargs.get("config")
        schema = getattr(config, "response_schema", None)
        response_mock = MagicMock()

        if schema == ContentIdea:
            idx = idea_cursor["index"] % len(mock_ideas)
            idea = dict(mock_ideas[idx])
            idea_cursor["index"] += 1
            response_mock.text = json.dumps(idea)
        elif schema == LinkedInPostContent:
            post = {
                "hook": "Brittle batch cron jobs fail silently. Event-driven architectures don't.",
                "caption": (
                    "When mission-critical enterprise workflows depend on scheduled cron jobs, "
                    "a single timeout or API hiccup can stall downstream operations without notice.\n\n"
                    "At Jevyam Technologies, we design automation systems around event queues, "
                    "idempotent workers, and explicit verification loops. If a worker fails, "
                    "dead-letter queues guarantee no state is ever dropped.\n\n"
                    "Reliability is not an accident—it is an architectural choice."
                ),
                "hashtags": ["#SoftwareEngineering", "#SystemDesign", "#CloudArchitecture", "#JevyamTech", "#Automation"],
                "call_to_action": "How does your engineering team guarantee idempotency across distributed workflows?",
            }
            response_mock.text = json.dumps(post)
        elif schema == ImageBrief:
            brief = {
                "visual_concept": "Minimalist diagram contrasting brittle cron jobs with resilient distributed queues",
                "style": "Dark mode modern enterprise technical diagram",
                "composition": "Two-column split view with glowing cyan and emerald signal lines",
                "color_direction": "Deep slate blue (#0B1120), electric cyan accent, and emerald success nodes",
                "text_on_image": "Idempotent Architectures",
                "aspect_ratio": "1200:627",
            }
            response_mock.text = json.dumps(brief)
        else:
            response_mock.text = json.dumps({"status": "ok"})

        return response_mock

    client.models.generate_content = MagicMock(side_effect=mock_generate_content)
    return client


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jevyam AI Marketing Agent - Daily Scheduled Automation (Phase 6)"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mode",
        type=str,
        choices=["mock", "live"],
        default=None,
        help="Execution mode: 'mock' (default) or 'live'",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in mock/dry-run mode (safe: no real WhatsApp messages, no LinkedIn posts)",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Run in LIVE mode (requires valid WhatsApp, Gemini, Supabase, and LinkedIn credentials)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass daily idempotency check to force generation of a new post for today",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date string (YYYY-MM-DD). Defaults to today's date",
    )
    parser.add_argument(
        "--activity",
        type=str,
        default=None,
        help="Optional company context or focus area for this post",
    )
    parser.add_argument(
        "--mock-gemini",
        action="store_true",
        help="Use simulated Gemini AI responses (useful for offline testing without API key)",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="Use in-memory repository rather than Supabase (useful for offline testing)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["telegram", "whatsapp"],
        default=None,
        help="Approval provider to use ('telegram' or 'whatsapp')",
    )
    parser.add_argument(
        "--posts-dir",
        type=str,
        default=None,
        help="Custom directory path for local JSON posts storage/export",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    configure_logging(verbose=args.verbose)

    # If --provider is explicitly passed, override settings
    if args.provider:
        settings.APPROVAL_PROVIDER = args.provider

    # Determine execution mode
    if args.live:
        mode = "live"
    elif args.dry_run:
        mode = "mock"
    elif args.mode:
        mode = args.mode
    else:
        # Default to mock unless DRY_RUN is explicitly false in settings
        mode = "live" if not settings.DRY_RUN else "mock"

    gemini_client = None
    if args.mock_gemini:
        gemini_client = create_mock_gemini_client()

    try:
        posts_dir_path = Path(args.posts_dir) if args.posts_dir else None
        repo_mgr = get_repository_manager(use_in_memory=args.in_memory)
        state_store = SchedulerStateStore(repository=repo_mgr.scheduler_runs)

        orchestrator = DailyOrchestrator(
            repo_manager=repo_mgr,
            gemini_client=gemini_client,
            use_in_memory_db=args.in_memory,
            posts_dir=posts_dir_path,
        )
        scheduler = DailyScheduler(
            orchestrator=orchestrator,
            state_store=state_store,
            max_retries=3,
            retry_delay_seconds=2.0,
        )
        result: DailyRunResult = scheduler.execute_daily_run(
            target_date_str=args.date,
            force=args.force,
            mode=mode,
        )

        if result.success:
            if result.is_skipped:
                print(f"\n[IDEMPOTENT SKIP] {result.message}")
            else:
                print(f"\n[SUCCESS] {result.message}")
                print(f"  Post ID:        {result.post_id}")
                print(f"  Revision:       {result.revision_number}")
                print(f"  Status:         {result.status}")
                print(f"  Approval URL:   {result.approval_url}")
                if result.telegram_message_id:
                    print(f"  Telegram Msg ID:{result.telegram_message_id}")
                if result.whatsapp_message_id:
                    print(f"  WhatsApp Msg ID:{result.whatsapp_message_id}")
            return 0

        else:
            print(f"\n[FAILURE] {result.message}")
            return 1

    except ConfigurationError as ce:
        print(f"\n[CONFIGURATION ERROR] {ce}", file=sys.stderr)
        return 1
    except DailyOrchestrationError as oe:
        print(f"\n[ORCHESTRATION ERROR] {oe}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
