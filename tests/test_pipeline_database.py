"""Tests verifying Phase 2 pipeline interaction with the database repository layer."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from agent.image_generator import ImageBrief
from agent.pipeline import regenerate_draft, run_content_pipeline
from database.models import Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager


@pytest.fixture
def mock_gemini_client():
    client = MagicMock()
    idea_json = json.dumps({
        "topic": "Zero-Trust Security for Vector Databases",
        "angle": "Why tenant isolation must be enforced at embedding time, not retrieval time",
        "content_type": "technology insight",
        "target_audience": "CISOs and Lead Architects",
        "reason": "Addresses high-priority security concerns for enterprise AI deployments.",
    })
    writer_json = json.dumps({
        "hook": "Vector embeddings without tenant access control are a data breach in waiting.",
        "caption": "Vector embeddings without tenant access control are a data breach in waiting.\n\nEnforcing strict isolation prevents cross-tenant data leakage in enterprise RAG.\n\nAt Jevyam Technologies, we build secure data bridges.\n\nHow do you isolate sensitive documents in your vector index?",
        "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech", "#CloudArchitecture", "#DataSecurity"],
        "call_to_action": "How do you isolate sensitive documents in your vector index?",
    })
    brief_json = json.dumps({
        "visual_concept": "Cryptographic shield encasing vector clusters with role badges",
        "style": "Minimalist isometric blueprint",
        "composition": "Centered focal shield with isolated data layers",
        "color_direction": "Deep slate with cobalt security barriers",
        "text_on_image": "Zero-Trust Vectors",
        "aspect_ratio": "1:1",
    })

    resp1 = MagicMock()
    resp1.text = idea_json
    resp2 = MagicMock()
    resp2.text = writer_json
    resp3 = MagicMock()
    resp3.text = brief_json
    client.models.generate_content.side_effect = [resp1, resp2, resp3]
    return client


def test_pipeline_persists_post_and_revision(mock_gemini_client, tmp_path: Path):
    """Verify that run_content_pipeline persists both a Post and PostRevision."""
    repo_manager = create_in_memory_repository_manager()

    draft = run_content_pipeline(
        client=mock_gemini_client,
        posts_dir=tmp_path,
        repo_manager=repo_manager,
        current_date="2026-09-29",
    )

    # 1. Verify Post master record
    post = repo_manager.posts.get_by_post_id(draft.post_id)
    assert post is not None
    assert post.status == PostStatus.DRAFT
    assert post.current_revision == 1
    assert post.topic == "Zero-Trust Security for Vector Databases"

    # 2. Verify PostRevision historical record
    revisions = repo_manager.revisions.get_by_post_id(draft.post_id)
    assert len(revisions) == 1
    assert revisions[0].revision_number == 1
    assert revisions[0].topic == post.topic
    assert revisions[0].hook == post.hook


def test_pipeline_duplicate_detection_from_database(tmp_path: Path):
    """Verify repetition engine detects duplicate against previous posts stored in database."""
    repo_manager = create_in_memory_repository_manager()

    # Pre-populate historical post in repository
    existing_post = Post(
        post_id="JVY-20260928-001",
        content_type="technology insight",
        topic="Zero-Trust Security for Vector Databases",
        angle="Angle",
        target_audience="CTOs",
        hook="Old hook",
        caption="Old caption",
        hashtags=["#Old"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=ImageBrief(
            visual_concept="V",
            style="S",
            composition="C",
            color_direction="CD",
            text_on_image="T",
        ),
    )
    repo_manager.posts.create(existing_post)

    client = MagicMock()
    # Attempt 1: duplicate of DB post
    dup_idea = MagicMock()
    dup_idea.text = json.dumps({
        "topic": "Zero-Trust Security for Vector Databases",
        "angle": "Angle",
        "content_type": "technology insight",
        "target_audience": "CTOs",
        "reason": "Duplicate attempt",
    })
    # Attempt 2: unique topic
    unique_idea = MagicMock()
    unique_idea.text = json.dumps({
        "topic": "Async Task Orchestration with Temporal and Python",
        "angle": "Reliable long-running workflow state machines",
        "content_type": "software engineering",
        "target_audience": "Backend Engineers",
        "reason": "Fresh topic",
    })
    writer_resp = MagicMock()
    writer_resp.text = json.dumps({
        "hook": "Distributed transactions fail silently without persistent state machines.",
        "caption": "Distributed transactions fail silently...\n\nHere is how Temporal solves it.",
        "hashtags": ["#Python", "#Backend", "#SoftwareEngineering"],
        "call_to_action": "What engine powers your workflows?",
    })
    brief_resp = MagicMock()
    brief_resp.text = json.dumps({
        "visual_concept": "Workflow DAG nodes",
        "style": "Vector",
        "composition": "Centered",
        "color_direction": "Charcoal and cyan",
        "text_on_image": "Workflow State Machines",
        "aspect_ratio": "1:1",
    })

    client.models.generate_content.side_effect = [
        dup_idea,
        unique_idea,
        writer_resp,
        brief_resp,
    ]

    draft = run_content_pipeline(
        client=client,
        posts_dir=tmp_path,
        repo_manager=repo_manager,
        current_date="2026-09-29",
    )

    # First topic was rejected as duplicate of database record; second topic succeeded!
    assert draft.topic == "Async Task Orchestration with Temporal and Python"
    assert draft.post_id == "JVY-20260929-001"


def test_regenerate_draft_creates_new_revision_in_database(tmp_path: Path):
    """Verify that regenerate_draft creates revision 2 without overwriting revision 1."""
    repo_manager = create_in_memory_repository_manager()

    brief = ImageBrief(
        visual_concept="V",
        style="S",
        composition="C",
        color_direction="CD",
        text_on_image="T",
    )

    # Seed post and revision 1 in repo
    post_id = "JVY-20260929-001"
    post = Post(
        post_id=post_id,
        status=PostStatus.DRAFT,
        current_revision=1,
        content_type="educational",
        topic="Initial Topic v1",
        angle="Initial Angle",
        target_audience="Engineers",
        hook="Initial Hook",
        caption="Initial Caption",
        hashtags=["#AI"],
        call_to_action="Initial CTA",
        visual_concept="Initial Visual",
        image_brief=brief,
    )
    repo_manager.posts.create(post)
    repo_manager.revisions.create(
        PostRevision(
            post_id=post_id,
            revision_number=1,
            content_type="educational",
            topic="Initial Topic v1",
            angle="Initial Angle",
            target_audience="Engineers",
            hook="Initial Hook",
            caption="Initial Caption",
            hashtags=["#AI"],
            call_to_action="Initial CTA",
            visual_concept="Initial Visual",
            image_brief=brief,
        )
    )

    client = MagicMock()
    new_idea_resp = MagicMock()
    new_idea_resp.text = json.dumps({
        "topic": "Pivoted Topic: Data Governance in RAG",
        "angle": "Role-based access control inside vector embeddings",
        "content_type": "technology insight",
        "target_audience": "Security Leaders",
        "reason": "Pivoted based on founder rejection",
    })
    new_writer_resp = MagicMock()
    new_writer_resp.text = json.dumps({
        "hook": "Vector search without access control is a security breach waiting to happen.",
        "caption": "Vector search without access control is a security breach waiting to happen.\n\nImplementing ACLs at ingestion prevents unauthorized data leakage.\n\nHow does your team enforce document security in RAG?",
        "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech"],
        "call_to_action": "How does your team enforce document security in RAG?",
    })
    new_brief_resp = MagicMock()
    new_brief_resp.text = json.dumps({
        "visual_concept": "Shield and permission matrix overlay on vector database",
        "style": "Clean isometric diagram",
        "composition": "Centered security gatekeeper concept",
        "color_direction": "Charcoal and shield blue",
        "text_on_image": "Securing Enterprise Vectors",
        "aspect_ratio": "1:1",
    })

    client.models.generate_content.side_effect = [
        new_idea_resp,
        new_writer_resp,
        new_brief_resp,
    ]

    new_draft = regenerate_draft(
        rejected_draft=post_id,
        rejection_reason="Needs enterprise security focus.",
        client=client,
        posts_dir=tmp_path,
        repo_manager=repo_manager,
    )

    assert new_draft.revision == 2
    assert new_draft.status == "PENDING_APPROVAL"

    # Verify both revisions exist in database
    all_revisions = repo_manager.revisions.get_by_post_id(post_id)
    assert len(all_revisions) == 2
    assert all_revisions[0].revision_number == 1
    assert all_revisions[0].topic == "Initial Topic v1"
    assert all_revisions[1].revision_number == 2
    assert all_revisions[1].topic == "Pivoted Topic: Data Governance in RAG"
    assert all_revisions[1].rejection_reason == "Needs enterprise security focus."

    # Verify master post record updated to revision 2 and PENDING_APPROVAL
    updated_master = repo_manager.posts.get_by_post_id(post_id)
    assert updated_master.current_revision == 2
    assert updated_master.status == PostStatus.PENDING_APPROVAL
    assert updated_master.topic == "Pivoted Topic: Data Governance in RAG"
