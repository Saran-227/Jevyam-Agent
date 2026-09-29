"""Tests for the Phase 6 daily automation and orchestration layer."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from agent.exceptions import (
    ConfigurationError,
    DailyOrchestrationError,
)
from agent.image_generator import ImageBrief
from agent.orchestrator import DailyOrchestrator, DailyRunResult
from agent.strategist import ContentIdea
from agent.writer import LinkedInPostContent
from api.services.approval_service import ApprovalService
from api.services.whatsapp_service import WhatsAppService
from config.settings import settings
from database.models import Post, PostStatus
from database.repositories import RepositoryManager
from database.repositories.approvals import InMemoryApprovalRepository
from database.repositories.companies import InMemoryCompanyRepository
from database.repositories.posts import InMemoryPostRepository
from database.repositories.publications import InMemoryPublicationRepository
from database.repositories.revisions import InMemoryRevisionRepository
from integrations.whatsapp.mock import MockWhatsAppProvider


def create_test_repo_manager() -> RepositoryManager:
    """Create an isolated in-memory repository manager for testing."""
    return RepositoryManager(
        companies=InMemoryCompanyRepository(),
        posts=InMemoryPostRepository(),
        revisions=InMemoryRevisionRepository(),
        approvals=InMemoryApprovalRepository(),
        publications=InMemoryPublicationRepository(),
    )


DISTINCT_TOPICS = [
    ("Why Vector Search Needs Hybrid Keyword Inverted Indexes", "Information retrieval trade-offs in modern RAG systems"),
    ("Deterministic State Machines for AI Agent Safety", "Bounding agentic executions with finite state machines"),
    ("Zero-Downtime Database Schema Migrations at Scale", "Blue-green database deployments and backward compatible views"),
    ("Decoupled Message Queuing with Dead-Letter Handling", "Reliable queue worker architectures in fintech"),
    ("Serverless Cold Start Optimization for Latency Sensitive APIs", "Provisioned concurrency vs edge routing"),
    ("Event-Driven Architecture and Distributed Tracing", "OpenTelemetry spans across asynchronous worker clusters"),
    ("Content Addressable Storage for Large AI Datasets", "Deduplicating training corpora with cryptographic hashing"),
]


def create_mock_gemini() -> MagicMock:
    """Mock Gemini client responding with valid and unique structured outputs."""
    client = MagicMock()
    counter = {"count": 0}

    def mock_generate_content(*args, **kwargs):
        config = kwargs.get("config")
        schema = getattr(config, "response_schema", None)
        resp = MagicMock()

        if schema == ContentIdea:
            idx = counter["count"] % len(DISTINCT_TOPICS)
            counter["count"] += 1
            topic, angle = DISTINCT_TOPICS[idx]
            resp.text = json.dumps({
                "topic": topic,
                "angle": angle,
                "content_type": "software engineering",
                "target_audience": "CTOs and Lead Engineers",
                "reason": "Clear architectural insights on cloud reliability.",
            })
        elif schema == LinkedInPostContent:
            resp.text = json.dumps({
                "hook": "Cron jobs fail silently. Event queues don't.",
                "caption": "Cron jobs fail silently. When scaling automation, idempotency is paramount.",
                "hashtags": ["#SoftwareEngineering", "#Architecture", "#DevOps"],
                "call_to_action": "How does your team guarantee idempotency?",
            })
        elif schema == ImageBrief:
            resp.text = json.dumps({
                "visual_concept": "Clean architectural diagram of idempotent event processing",
                "style": "Dark mode modern blueprint",
                "composition": "Horizontal message queue pipeline",
                "color_direction": "Slate blue background with cyan and emerald accents",
                "text_on_image": "Idempotent Architectures",
                "aspect_ratio": "1:1",
            })
        else:
            resp.text = "{}"

        return resp

    client.models.generate_content.side_effect = mock_generate_content
    return client


def test_orchestrator_initialization():
    """Verify orchestrator initializes with provided dependencies."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        use_in_memory_db=True,
    )
    assert orchestrator.repos is repos
    assert orchestrator.gemini_client is mock_gemini
    assert orchestrator.approval_service is not None


def test_validate_configuration_mock_mode_success():
    """Verify mock mode validation passes when mock client is provided."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        use_in_memory_db=True,
    )
    # Should not raise
    orchestrator.validate_configuration(mode="mock")


def test_validate_configuration_mock_mode_missing_gemini():
    """Verify mock mode raises error when no GEMINI_API_KEY and no mock client."""
    repos = create_test_repo_manager()
    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=None,
        use_in_memory_db=True,
    )
    with patch.object(settings, "GEMINI_API_KEY", ""):
        with pytest.raises(ConfigurationError) as exc_info:
            orchestrator.validate_configuration(mode="mock")
        assert "GEMINI_API_KEY" in str(exc_info.value)


def test_validate_configuration_live_mode_refusal():
    """Verify LIVE mode raises ConfigurationError if credentials are missing or placeholders."""
    repos = create_test_repo_manager()
    orchestrator = DailyOrchestrator(repo_manager=repos, use_in_memory_db=True)

    with patch.object(settings, "WHATSAPP_ACCESS_TOKEN", None), \
         patch.object(settings, "LINKEDIN_ACCESS_TOKEN", None):
        with pytest.raises(ConfigurationError) as exc_info:
            orchestrator.validate_configuration(mode="live")
        err_msg = str(exc_info.value)
        assert "LIVE mode cannot proceed" in err_msg
        assert "WHATSAPP_ACCESS_TOKEN" in err_msg
        assert "LINKEDIN_ACCESS_TOKEN" in err_msg


def test_validate_configuration_live_mode_placeholders_rejected():
    """Verify LIVE mode rejects placeholder credentials."""
    repos = create_test_repo_manager()
    orchestrator = DailyOrchestrator(repo_manager=repos, use_in_memory_db=True)

    with patch.object(settings, "GEMINI_API_KEY", "your_gemini_key"), \
         patch.object(settings, "SUPABASE_URL", "your_supabase_url"), \
         patch.object(settings, "SUPABASE_KEY", "your_supabase_key"), \
         patch.object(settings, "WHATSAPP_ACCESS_TOKEN", "your_wa_token"), \
         patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", "your_phone_id"), \
         patch.object(settings, "WHATSAPP_FOUNDER_PHONE", "+919876543210"), \
         patch.object(settings, "LINKEDIN_ACCESS_TOKEN", "your_li_token"), \
         patch.object(settings, "LINKEDIN_ORGANIZATION_ID", "12345678"):
        with pytest.raises(ConfigurationError) as exc_info:
            orchestrator.validate_configuration(mode="live")
        assert "LIVE mode cannot proceed" in str(exc_info.value)


def test_daily_run_mock_end_to_end_success(tmp_path):
    """Verify end-to-end execution in mock mode creates post, revision, approval, and mock WhatsApp notification."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    mock_wa_provider = MockWhatsAppProvider()
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_gemini)
    wa_svc = WhatsAppService(approval_service=approval_svc, provider=mock_wa_provider)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_svc,
        whatsapp_service=wa_svc,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    result = orchestrator.run(
        mode="mock",
        date_str="2026-10-01",
    )

    assert result.success is True
    assert result.is_skipped is False
    assert result.mode == "mock"
    assert result.post_id == "JVY-20261001-001"
    assert result.revision_number == 1
    assert result.status == PostStatus.PENDING_APPROVAL.value
    assert result.approval_token is not None
    assert result.approval_url.startswith("http://")
    assert result.whatsapp_message_id.startswith("mock_wamid_")

    # Verify persisted post in repository
    saved_post = repos.posts.get_by_post_id("JVY-20261001-001")
    assert saved_post is not None
    assert saved_post.status == PostStatus.PENDING_APPROVAL

    # Verify WhatsApp notification was recorded
    assert len(mock_wa_provider.sent_messages) == 1
    assert mock_wa_provider.sent_messages[0]["type"] == "approval_interactive"
    assert mock_wa_provider.sent_messages[0]["payload"]["post_id"] == "JVY-20261001-001"


def test_daily_idempotency_prevents_duplicate_runs(tmp_path):
    """Verify idempotency skips duplicate creation when run twice on the same day."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    mock_wa_provider = MockWhatsAppProvider()
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_gemini)
    wa_svc = WhatsAppService(approval_service=approval_svc, provider=mock_wa_provider)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_svc,
        whatsapp_service=wa_svc,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    # First run: should create post JVY-20261002-001
    res1 = orchestrator.run(mode="mock", date_str="2026-10-02")
    assert res1.success is True
    assert res1.is_skipped is False
    assert res1.post_id == "JVY-20261002-001"

    # Second run without force: should skip and report existing post
    res2 = orchestrator.run(mode="mock", date_str="2026-10-02", force=False)
    assert res2.success is True
    assert res2.is_skipped is True
    assert res2.post_id == "JVY-20261002-001"
    assert "already exists" in res2.message

    # WhatsApp message count should still be 1 (no duplicate sent)
    assert len(mock_wa_provider.sent_messages) == 1


def test_daily_idempotency_force_override(tmp_path):
    """Verify force=True bypasses idempotency guard and generates sequence 002."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    mock_wa_provider = MockWhatsAppProvider()
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_gemini)
    wa_svc = WhatsAppService(approval_service=approval_svc, provider=mock_wa_provider)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_svc,
        whatsapp_service=wa_svc,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    # First run
    res1 = orchestrator.run(mode="mock", date_str="2026-10-03")
    assert res1.post_id == "JVY-20261003-001"

    # Second run with force=True: should generate sequence 002
    res2 = orchestrator.run(mode="mock", date_str="2026-10-03", force=True)
    assert res2.success is True
    assert res2.is_skipped is False
    assert res2.post_id == "JVY-20261003-002"
    assert len(mock_wa_provider.sent_messages) == 2


def test_safe_logging_never_exposes_tokens(tmp_path, caplog):
    """Verify tokens and secrets are not leaked in log output."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    import logging
    with caplog.at_level(logging.INFO):
        res = orchestrator.run(mode="mock", date_str="2026-10-04")

    token = res.approval_token
    assert token is not None
    # Entire unmasked token should not appear in raw log text
    assert token not in caplog.text


def test_failure_propagation_on_pipeline_error(tmp_path):
    """Verify DailyOrchestrationError is raised when content pipeline fails."""
    repos = create_test_repo_manager()
    broken_gemini = MagicMock()
    broken_gemini.models.generate_content.side_effect = RuntimeError("Fatal Gemini API failure")

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=broken_gemini,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    with pytest.raises(DailyOrchestrationError) as exc_info:
        orchestrator.run(mode="mock", date_str="2026-10-05")
    assert "Content generation pipeline failed" in str(exc_info.value)


def test_failure_propagation_on_whatsapp_error(tmp_path):
    """Verify DailyOrchestrationError is raised when WhatsApp provider dispatch fails."""
    repos = create_test_repo_manager()
    mock_gemini = create_mock_gemini()
    failing_wa_provider = MockWhatsAppProvider(should_fail=True, failure_error="Simulated network failure")
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_gemini)
    wa_svc = WhatsAppService(approval_service=approval_svc, provider=failing_wa_provider)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_svc,
        whatsapp_service=wa_svc,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    with pytest.raises(DailyOrchestrationError) as exc_info:
        orchestrator.run(mode="mock", date_str="2026-10-06")
    assert "WhatsApp provider returned error" in str(exc_info.value)


def test_cli_help_flag():
    """Verify python scripts/daily_run.py --help returns 0."""
    res = subprocess.run(
        [sys.executable, "scripts/daily_run.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Jevyam AI Marketing Agent" in res.stdout
    assert "--dry-run" in res.stdout
    assert "--live" in res.stdout


def test_cli_dry_run_execution(tmp_path):
    """Verify python scripts/daily_run.py --dry-run --mock-gemini --in-memory returns 0."""
    res = subprocess.run(
        [
            sys.executable,
            "scripts/daily_run.py",
            "--dry-run",
            "--mock-gemini",
            "--in-memory",
            "--posts-dir",
            str(tmp_path),
            "--date",
            "2026-10-07",
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "[SUCCESS]" in res.stdout
