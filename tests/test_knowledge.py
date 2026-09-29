"""Unit tests for company knowledge loader."""

from pathlib import Path
import pytest

from agent.exceptions import MissingKnowledgeFileError
from agent.knowledge import CompanyKnowledge, load_company_knowledge


def test_load_existing_company_knowledge():
    """Verify loading from the default data/company directory."""
    knowledge = load_company_knowledge()
    assert isinstance(knowledge, CompanyKnowledge)
    assert "Jevyam Technologies" in knowledge.profile
    assert "Jevyam Workflow Copilot" in knowledge.products
    assert "Generative AI" in knowledge.services
    assert "Brand Voice" in knowledge.brand_voice or "Editorial Philosophy" in knowledge.brand_voice

    # Check combined full_context
    assert "=== COMPANY PROFILE ===" in knowledge.full_context
    assert "=== PRODUCTS & SOLUTIONS ===" in knowledge.full_context
    assert "=== SERVICES & CAPABILITIES ===" in knowledge.full_context


def test_missing_knowledge_file_error(tmp_path: Path):
    """Verify that a missing required markdown file raises MissingKnowledgeFileError."""
    # Create directory with only 2 of 4 files
    (tmp_path / "company_profile.md").write_text("Profile", encoding="utf-8")
    (tmp_path / "products.md").write_text("Products", encoding="utf-8")

    with pytest.raises(MissingKnowledgeFileError) as exc_info:
        load_company_knowledge(tmp_path)

    assert "services.md" in str(exc_info.value) or "brand_voice.md" in str(exc_info.value)


def test_nonexistent_directory_error(tmp_path: Path):
    """Verify error when directory doesn't exist."""
    fake_dir = tmp_path / "does_not_exist"
    with pytest.raises(MissingKnowledgeFileError):
        load_company_knowledge(fake_dir)
