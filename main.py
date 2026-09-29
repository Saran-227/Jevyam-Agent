"""Main entry point for Jevyam Technologies AI Marketing Agent."""

import argparse
import sys
from agent.exceptions import (
    DuplicateContentError,
    JevyamAgentError,
    MissingGeminiApiKeyError,
    MissingKnowledgeFileError,
)
from agent.pipeline import run_content_pipeline


def print_banner() -> None:
    print("=" * 50)
    print("JEVYAM AI CONTENT AGENT")
    print("=" * 50)


def display_draft(draft) -> None:
    print_banner()
    print(f"\nPost ID:\n{draft.post_id}")
    print(f"\nContent Type:\n{draft.content_type}")
    print(f"\nTarget Audience:\n{draft.target_audience}")
    print(f"\nTopic:\n{draft.topic}")
    print(f"\nAngle:\n{draft.angle}")
    print(f"\nHook:\n{draft.hook}")
    print(f"\nCaption:\n{draft.caption}")
    print(f"\nHashtags:\n{' '.join(draft.hashtags)}")
    print(f"\nVisual Concept:\n{draft.visual_concept}")
    print("\nImage Brief:")
    print(f"  Style: {draft.image_brief.style}")
    print(f"  Composition: {draft.image_brief.composition}")
    print(f"  Color Direction: {draft.image_brief.color_direction}")
    print(f"  Text on Image: {draft.image_brief.text_on_image}")
    print(f"  Aspect Ratio: {draft.image_brief.aspect_ratio}")
    print(f"\nRevision:\n{draft.revision}")
    print(f"\nStatus:\n{draft.status}")
    print("\n" + "=" * 50)
    print(f"Draft successfully saved to: data/posts/{draft.post_id}.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jevyam AI Content Marketing Agent - Phase 1 Content Engine"
    )
    parser.add_argument(
        "--activity",
        type=str,
        default=None,
        help="Optional recent company activity or focus area",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Custom date string (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode using simulated Gemini responses (useful for offline testing)",
    )
    args = parser.parse_args()

    client = None
    if args.mock:
        from unittest.mock import MagicMock
        import json
        from agent.strategist import ContentIdea
        from agent.writer import LinkedInPostContent
        from agent.image_generator import ImageBrief

        client = MagicMock()
        mock_ideas = [
            {
                "topic": "Why Larger Context Windows Don't Replace Preprocessing",
                "angle": "Relying purely on brute-force context windows causes latency spikes and retrieval degradation",
                "content_type": "technology insight",
                "target_audience": "CTOs and Lead Engineers",
                "reason": "Addresses real-world production engineering trade-offs in modern LLM architecture.",
            },
            {
                "topic": "Event-Driven Automation Architecture with Idempotent Queues",
                "angle": "Why webhooks with idempotent queues beat brittle cron scripts in enterprise automation",
                "content_type": "software engineering",
                "target_audience": "Tech Leads and Backend Engineers",
                "reason": "Provides actionable backend architecture insights for modern reliability.",
            },
            {
                "topic": "Human-in-the-Loop AI: The Safety Boundary Enterprise Needs",
                "angle": "Autonomous agents need guardrails and human verification before irreversible state changes",
                "content_type": "AI",
                "target_audience": "Founders and Operations Leaders",
                "reason": "Reinforces pragmatic AI deployment over reckless automation.",
            },
        ]
        idea_cursor = {"index": 0}

        def mock_generate_content(*call_args, **call_kwargs):
            config = call_kwargs.get("config")
            schema = getattr(config, "response_schema", None)
            resp = MagicMock()

            if schema == ContentIdea:
                data = mock_ideas[idea_cursor["index"] % len(mock_ideas)]
                idea_cursor["index"] += 1
                resp.text = json.dumps(data)
            elif schema == LinkedInPostContent:
                resp.text = json.dumps({
                    "hook": "Reliable automation starts with idempotent workflows, not brittle cron scripts.",
                    "caption": "Reliable automation starts with idempotent workflows, not brittle cron scripts.\n\nWhen scaling internal operations, silent cron failures cascade across your infrastructure.\n\nAt Jevyam Technologies, we build event-driven pipelines with dead-letter queues and human verification checkpoints.\n\nHow does your team ensure fault tolerance in automation?",
                    "hashtags": ["#SoftwareEngineering", "#Automation", "#CloudArchitecture", "#DevOps", "#TechLeadership"],
                    "call_to_action": "How does your team ensure fault tolerance in automation?",
                })
            elif schema == ImageBrief:
                resp.text = json.dumps({
                    "visual_concept": "Clean architectural flow from event trigger through message queue to worker nodes",
                    "style": "Minimalist isometric dark-mode technical blueprint",
                    "composition": "Horizontal pipeline sequence with highlighted failure boundaries",
                    "color_direction": "Deep charcoal background with cyan data nodes and emerald status indicators",
                    "text_on_image": "Idempotent Event Architecture",
                    "aspect_ratio": "1:1",
                })
            else:
                resp.text = "{}"
            return resp

        client.models.generate_content.side_effect = mock_generate_content

    try:
        draft = run_content_pipeline(
            client=client,
            current_date=args.date,
            recent_activity=args.activity,
        )
        display_draft(draft)
        return 0

    except MissingGeminiApiKeyError as e:
        print("\n[ERROR] Missing Gemini API Key.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        print("Please configure GEMINI_API_KEY in your .env file.", file=sys.stderr)
        print("Tip: You can also test offline with mock data using: python main.py --mock", file=sys.stderr)
        return 1

    except MissingKnowledgeFileError as e:
        print("\n[ERROR] Missing Company Knowledge File.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        return 1

    except DuplicateContentError as e:
        print(f"\n[ERROR] Duplicate Content Detected: {e}", file=sys.stderr)
        return 1

    except JevyamAgentError as e:
        print(f"\n[ERROR] Jevyam Agent Error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(130)
    except DuplicateContentError as e:
        print(f"\n[ERROR] Duplicate Content Detected: {e}", file=sys.stderr)
        sys.exit(1)
    except JevyamAgentError as e:
        print(f"\n[ERROR] Jevyam Agent Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
