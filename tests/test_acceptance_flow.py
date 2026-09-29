"""Acceptance test verifying the exact 7-step founder approval workflow specified in Phase 3."""

import json
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from api.dependencies import get_approval_service
from api.main import app
from api.services.approval_service import ApprovalService
from database.models import ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager


def test_full_acceptance_workflow_steps_1_to_7():
    """Execute the mandatory 7-step acceptance workflow."""
    repo_manager = create_in_memory_repository_manager()

    mock_gemini = MagicMock()
    # Mock regeneration response
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Pivoted Topic: Data Governance in RAG",
            "angle": "Enterprise RBAC within vector indices",
            "content_type": "technology insight",
            "target_audience": "CISOs and Lead Engineers",
            "reason": "Feedback requested deeper enterprise security.",
        })),
        MagicMock(text=json.dumps({
            "hook": "Vector search without access control is a security breach waiting to happen.",
            "caption": "Vector search without access control is a security breach waiting to happen.\n\nImplementing tenant isolation prevents cross-tenant data leakage in enterprise RAG.\n\nHow do you handle document permissions?",
            "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech", "#CloudArchitecture"],
            "call_to_action": "How do you handle document permissions?",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Cryptographic shield encasing vector clusters",
            "style": "Minimalist isometric blueprint",
            "composition": "Centered shield with isolated layers",
            "color_direction": "Slate and cobalt",
            "text_on_image": "Securing Vector Stores",
            "aspect_ratio": "1:1",
        })),
    ]

    service = ApprovalService(repo_manager=repo_manager, gemini_client=mock_gemini)
    app.dependency_overrides[get_approval_service] = lambda: service
    client = TestClient(app)

    try:
        # ----------------------------------------------------
        # STEP 1: Have an existing draft (JVY-20260929-001, revision = 1, status = DRAFT)
        # ----------------------------------------------------
        post_id = "JVY-20260929-001"
        brief = ImageBrief(
            visual_concept="Initial visual",
            style="Vector",
            composition="Center",
            color_direction="Slate",
            text_on_image="Initial Concept",
        )
        initial_post = Post(
            post_id=post_id,
            status=PostStatus.DRAFT,
            current_revision=1,
            content_type="technology insight",
            topic="Evaluating Zero-Trust Vectors",
            angle="Embedding-time access control",
            target_audience="CTOs",
            hook="Vector search without access control is a vulnerability.",
            caption="Vector search without access control is a vulnerability.",
            hashtags=["#AI", "#Security"],
            call_to_action="How do you secure vectors?",
            visual_concept="Initial visual",
            image_brief=brief,
        )
        repo_manager.posts.create(initial_post)
        repo_manager.revisions.create(
            PostRevision(
                post_id=post_id,
                revision_number=1,
                content_type=initial_post.content_type,
                topic=initial_post.topic,
                angle=initial_post.angle,
                target_audience=initial_post.target_audience,
                hook=initial_post.hook,
                caption=initial_post.caption,
                hashtags=initial_post.hashtags,
                call_to_action=initial_post.call_to_action,
                visual_concept=initial_post.visual_concept,
                image_brief=brief,
            )
        )

        p = repo_manager.posts.get_by_post_id(post_id)
        assert p.status == PostStatus.DRAFT
        assert p.current_revision == 1

        # ----------------------------------------------------
        # STEP 2: Create an approval request.
        # Expected: status = PENDING_APPROVAL, approval token created.
        # ----------------------------------------------------
        create_resp = service.create_approval_request(post_id=post_id, revision_number=1)
        token_1 = create_resp.approval_token
        assert token_1.startswith("appr_")

        p = repo_manager.posts.get_by_post_id(post_id)
        assert p.status == PostStatus.PENDING_APPROVAL

        # ----------------------------------------------------
        # STEP 3: Open: GET /approve/{token}
        # Expected: Founder-facing approval page appears.
        # ----------------------------------------------------
        page_resp = client.get(f"/approve/{token_1}")
        assert page_resp.status_code == 200
        assert "LinkedIn Post Approval" in page_resp.text
        assert "Evaluating Zero-Trust Vectors" in page_resp.text
        assert "YES — PUBLISH" in page_resp.text
        assert "NO — REGENERATE" in page_resp.text

        # ----------------------------------------------------
        # STEP 4: Click: YES — PUBLISH
        # Expected: post status = APPROVED, approval status = APPROVED, token cannot be reused.
        # ----------------------------------------------------
        yes_resp = client.post(f"/approve/{token_1}/yes")
        assert yes_resp.status_code == 200
        assert yes_resp.json()["status"] == "approved"

        p = repo_manager.posts.get_by_post_id(post_id)
        assert p.status == PostStatus.APPROVED

        appr_record = repo_manager.approvals.get_by_token(token_1)
        assert appr_record.status == ApprovalStatus.APPROVED

        # Verify token cannot be reused
        double_yes = client.post(f"/approve/{token_1}/yes")
        assert double_yes.status_code == 410

        # ----------------------------------------------------
        # STEP 5: Reset/create another pending approval for demonstration.
        # Click: NO — REGENERATE
        # Expected:
        # revision 1 remains in database.
        # revision 2 is created with new content.
        # current_revision = 2.
        # post status = PENDING_APPROVAL.
        # old approval token is invalid.
        # new approval token exists.
        # new approval URL is returned.
        # ----------------------------------------------------
        # Create a second approval request for revision 1 (simulating founder asking to regenerate)
        appr_for_reject = repo_manager.approvals.create_approval_request(post_id=post_id, revision_number=1)
        token_for_reject = appr_for_reject.approval_token
        # Reset post status to PENDING_APPROVAL
        p.status = PostStatus.PENDING_APPROVAL
        repo_manager.posts.update(p)

        no_resp = client.post(
            f"/approve/{token_for_reject}/no",
            json={"reason": "Make it more technical and focused on enterprise security."},
        )
        assert no_resp.status_code == 200
        no_data = no_resp.json()
        assert no_data["status"] == "regenerated"
        assert no_data["revision"] == 2
        new_approval_url = no_data["approval_url"]
        new_token = new_approval_url.split("/approve/")[-1]

        # Verify revision 1 remains in database
        revs = repo_manager.revisions.get_by_post_id(post_id)
        assert len(revs) == 2
        assert revs[0].revision_number == 1
        assert revs[0].topic == "Evaluating Zero-Trust Vectors"

        # Verify revision 2 is created
        assert revs[1].revision_number == 2
        assert revs[1].topic == "Pivoted Topic: Data Governance in RAG"
        assert revs[1].rejection_reason == "Make it more technical and focused on enterprise security."

        # Verify post status and current_revision
        p = repo_manager.posts.get_by_post_id(post_id)
        assert p.current_revision == 2
        assert p.status == PostStatus.PENDING_APPROVAL

        # Verify old token is invalid
        old_record = repo_manager.approvals.get_by_token(token_for_reject)
        assert old_record.status == ApprovalStatus.REJECTED

        # ----------------------------------------------------
        # STEP 6: Open the new URL.
        # Expected: revision 2 is displayed.
        # ----------------------------------------------------
        new_page_resp = client.get(f"/approve/{new_token}")
        assert new_page_resp.status_code == 200
        assert "Revision #2" in new_page_resp.text
        assert "Pivoted Topic: Data Governance in RAG" in new_page_resp.text

        # ----------------------------------------------------
        # STEP 7: Click YES.
        # Expected: revision 2 becomes approved.
        # ----------------------------------------------------
        yes_rev2_resp = client.post(f"/approve/{new_token}/yes")
        assert yes_rev2_resp.status_code == 200
        assert yes_rev2_resp.json()["status"] == "approved"
        assert yes_rev2_resp.json()["revision"] == 2

        p_final = repo_manager.posts.get_by_post_id(post_id)
        assert p_final.status == PostStatus.APPROVED
        assert p_final.current_revision == 2

    finally:
        app.dependency_overrides.clear()
