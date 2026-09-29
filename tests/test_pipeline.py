"""Unit tests for pipeline orchestration and regeneration."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from agent.exceptions import DuplicateContentError
from agent.image_generator import ImageBrief
from agent.pipeline import LinkedInDraft, regenerate_draft, run_content_pipeline


@pytest.fixture
def mock_gemini_client():
    client = MagicMock()

    idea_json = json.dumps(
        {
            "topic": "Event-Driven Automation Architecture",
            "angle": "Why webhooks with idempotent queues beat brittle cron scripts",
            "content_type": "software engineering",
            "target_audience": "Tech Leads and Backend Engineers",
            "reason": "Provides actionable backend architecture insights.",
        }
    )

    writer_json = json.dumps(
        {
            "hook": "Cron jobs are fine until silent failures cascade across your stack.",
            "caption": "Cron jobs are fine until silent failures cascade across your stack.\n\nMoving to an event-driven architecture with idempotent task queues transforms system reliability.\n\nAt Jevyam Technologies, we design fault-tolerant automation pipelines.\n\nHow do you handle retries and idempotency in your internal systems?",
            "hashtags": ["#SoftwareEngineering", "#Automation", "#CloudArchitecture", "#BackendDevelopment", "#DevOps"],
            "call_to_action": "How do you handle retries and idempotency in your internal systems?",
        }
    )

    brief_json = json.dumps(
        {
            "visual_concept": "Clean architectural flow from event trigger through message queue to worker nodes",
            "style": "Minimalist dark slate 2D system blueprint",
            "composition": "Horizontal pipeline sequence with highlighted failure boundaries",
            "color_direction": "Deep charcoal background with emerald and cyan status nodes",
            "text_on_image": "Idempotent Event Architecture",
            "aspect_ratio": "1:1",
        }
    )

    # Return responses in sequence for Strategist, Writer, ImageBrief
    resp_idea = MagicMock()
    resp_idea.text = idea_json
    resp_writer = MagicMock()
    resp_writer.text = writer_json
    resp_brief = MagicMock()
    resp_brief.text = brief_json

    client.models.generate_content.side_effect = [resp_idea, resp_writer, resp_brief]
    return client


def test_run_content_pipeline_success(mock_gemini_client, tmp_path: Path):
    draft = run_content_pipeline(
        client=mock_gemini_client,
        posts_dir=tmp_path,
        current_date="2026-09-29",
    )

    assert isinstance(draft, LinkedInDraft)
    assert draft.post_id == "JVY-20260929-001"
    assert draft.topic == "Event-Driven Automation Architecture"
    assert draft.revision == 1
    assert draft.status == "DRAFT"
    assert len(draft.hashtags) == 5
    assert (tmp_path / "JVY-20260929-001.json").exists()


def test_pipeline_duplicate_detection_retry(tmp_path: Path):
    """Strategist returns duplicate on attempt 1, fresh topic on attempt 2."""
    client = MagicMock()

    # Pre-populate previous post
    existing_draft = LinkedInDraft(
        post_id="JVY-20260928-001",
        generated_at="2026-09-28T12:00:00",
        topic="Event-Driven Automation Architecture",
        angle="Why webhooks beat cron",
        content_type="software engineering",
        target_audience="Engineers",
        hook="Old hook",
        caption="Old caption",
        hashtags=["#Old"],
        call_to_action="Old CTA",
        visual_concept="Old visual",
        image_brief=ImageBrief(
            visual_concept="V",
            style="S",
            composition="C",
            color_direction="CD",
            text_on_image="T",
        ),
    )
    (tmp_path / "JVY-20260928-001.json").write_text(existing_draft.model_dump_json(), encoding="utf-8")

    # Call 1: duplicate topic
    dup_idea_resp = MagicMock()
    dup_idea_resp.text = json.dumps(
        {
            "topic": "Event-Driven Automation Architecture",
            "angle": "Why webhooks beat cron",
            "content_type": "software engineering",
            "target_audience": "Engineers",
            "reason": "Duplicate attempt",
        }
    )

    # Call 2: fresh topic
    fresh_idea_resp = MagicMock()
    fresh_idea_resp.text = json.dumps(
        {
            "topic": "Evaluating Small Specialized Models vs General LLMs",
            "angle": "Cost-performance trade-offs for latency-critical tasks",
            "content_type": "technology insight",
            "target_audience": "CTOs",
            "reason": "Fresh topic",
        }
    )

    # Writer and Brief for fresh topic
    writer_resp = MagicMock()
    writer_resp.text = json.dumps(
        {
            "hook": "Bigger is rarely better when your API latency SLA is 200ms.",
            "caption": "Bigger is rarely better when your API latency SLA is 200ms.\n\nFine-tuned 8B models consistently outperform generic giants on classification.\n\nWhat model size powers your production stack?",
            "hashtags": ["#AI", "#MachineLearning", "#CloudArchitecture", "#SoftwareEngineering", "#TechLeadership"],
            "call_to_action": "What model size powers your production stack?",
        }
    )

    brief_resp = MagicMock()
    brief_resp.text = json.dumps(
        {
            "visual_concept": "Benchmark latency graph comparing model sizes",
            "style": "Minimalist graphic",
            "composition": "Centered chart",
            "color_direction": "Slate grey and cyan",
            "text_on_image": "Right-Sizing LLMs",
            "aspect_ratio": "1:1",
        }
    )

    client.models.generate_content.side_effect = [
        dup_idea_resp,
        fresh_idea_resp,
        writer_resp,
        brief_resp,
    ]

    draft = run_content_pipeline(
        client=client,
        posts_dir=tmp_path,
        current_date="2026-09-29",
        max_retries=3,
    )

    assert draft.topic == "Evaluating Small Specialized Models vs General LLMs"
    assert draft.post_id == "JVY-20260929-001"


def test_pipeline_duplicate_fails_after_max_retries(tmp_path: Path):
    """Strategist repeatedly returns duplicate -> raises DuplicateContentError."""
    client = MagicMock()

    # Pre-populate
    existing_draft = LinkedInDraft(
        post_id="JVY-20260928-001",
        generated_at="2026-09-28T12:00:00",
        topic="Event-Driven Automation Architecture",
        angle="Angle",
        content_type="software engineering",
        target_audience="Engineers",
        hook="Old hook",
        caption="Old caption",
        hashtags=["#Old"],
        call_to_action="Old CTA",
        visual_concept="V",
        image_brief=ImageBrief(
            visual_concept="V",
            style="S",
            composition="C",
            color_direction="CD",
            text_on_image="T",
        ),
    )
    (tmp_path / "JVY-20260928-001.json").write_text(existing_draft.model_dump_json(), encoding="utf-8")

    dup_resp = MagicMock()
    dup_resp.text = json.dumps(
        {
            "topic": "Event-Driven Automation Architecture",
            "angle": "Angle",
            "content_type": "software engineering",
            "target_audience": "Engineers",
            "reason": "Duplicate",
        }
    )
    client.models.generate_content.side_effect = [dup_resp, dup_resp, dup_resp]

    with pytest.raises(DuplicateContentError) as exc_info:
        run_content_pipeline(
            client=client,
            posts_dir=tmp_path,
            max_retries=3,
        )

    assert "Failed to generate a non-repetitive topic" in str(exc_info.value)


def test_regenerate_draft(tmp_path: Path):
    """Verify draft regeneration increments revision and saves updated draft."""
    client = MagicMock()

    initial_draft = LinkedInDraft(
        post_id="JVY-20260929-001",
        generated_at="2026-09-29T10:00:00",
        topic="Initial Topic",
        angle="Initial Angle",
        content_type="educational",
        target_audience="Engineers",
        hook="Initial Hook",
        caption="Initial Caption",
        hashtags=["#AI"],
        call_to_action="Initial CTA",
        visual_concept="Initial Visual",
        image_brief=ImageBrief(
            visual_concept="V",
            style="S",
            composition="C",
            color_direction="CD",
            text_on_image="T",
        ),
        revision=1,
    )
    (tmp_path / "JVY-20260929-001.json").write_text(initial_draft.model_dump_json(), encoding="utf-8")

    # Mock response for regeneration
    new_idea_resp = MagicMock()
    new_idea_resp.text = json.dumps(
        {
            "topic": "Pivoted Topic: Data Governance in RAG",
            "angle": "Role-based access control inside vector embeddings",
            "content_type": "technology insight",
            "target_audience": "Security and Engineering Leaders",
            "reason": "Addresses feedback requesting deeper enterprise security focus.",
        }
    )

    new_writer_resp = MagicMock()
    new_writer_resp.text = json.dumps(
        {
            "hook": "Vector search without access control is a security breach waiting to happen.",
            "caption": "Vector search without access control is a security breach waiting to happen.\n\nImplementing tenant isolation and ACLs at ingestion prevents unauthorized data leakage.\n\nHow does your team enforce document security in RAG?",
            "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech", "#SoftwareEngineering", "#CloudSecurity"],
            "call_to_action": "How does your team enforce document security in RAG?",
        }
    )

    new_brief_resp = MagicMock()
    new_brief_resp.text = json.dumps(
        {
            "visual_concept": "Shield and permission matrix overlay on vector database",
            "style": "Clean isometric diagram",
            "composition": "Centered security gatekeeper concept",
            "color_direction": "Charcoal and shield blue",
            "text_on_image": "Securing Enterprise Vectors",
            "aspect_ratio": "1:1",
        }
    )

    client.models.generate_content.side_effect = [
        new_idea_resp,
        new_writer_resp,
        new_brief_resp,
    ]

    new_draft = regenerate_draft(
        rejected_draft=initial_draft,
        rejection_reason="Too generic; make it specifically about security and data governance in enterprise RAG.",
        client=client,
        posts_dir=tmp_path,
    )

    assert new_draft.post_id == initial_draft.post_id
    assert new_draft.revision == 2
    assert new_draft.topic == "Pivoted Topic: Data Governance in RAG"
    assert new_draft.hook == "Vector search without access control is a security breach waiting to happen."

    # Verify storage was updated with revision 2
    saved_json = json.loads((tmp_path / "JVY-20260929-001.json").read_text(encoding="utf-8"))
    assert saved_json["revision"] == 2
    assert saved_json["topic"] == "Pivoted Topic: Data Governance in RAG"
