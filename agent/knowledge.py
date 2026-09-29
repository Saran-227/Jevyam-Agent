"""Company knowledge loader for Jevyam Technologies.

Loads authoritative company knowledge and brand guidelines from Markdown source files.
"""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from agent.exceptions import MissingKnowledgeFileError


class CompanyKnowledge(BaseModel):
    """Structured representation of Jevyam company knowledge."""

    profile: str = Field(description="Core company profile, mission, and values")
    products: str = Field(description="Official products and internal solutions")
    services: str = Field(description="Engineering capabilities and offerings")
    brand_voice: str = Field(description="Brand voice, tone, and editorial rules")

    @property
    def full_context(self) -> str:
        """Combined authoritative company context for prompts."""
        return (
            f"=== COMPANY PROFILE ===\n{self.profile}\n\n"
            f"=== PRODUCTS & SOLUTIONS ===\n{self.products}\n\n"
            f"=== SERVICES & CAPABILITIES ===\n{self.services}"
        )


DEFAULT_COMPANY_DIR = Path(__file__).resolve().parent.parent / "data" / "company"

REQUIRED_FILES = {
    "profile": "company_profile.md",
    "products": "products.md",
    "services": "services.md",
    "brand_voice": "brand_voice.md",
}


def load_company_knowledge(company_dir: Optional[Path] = None) -> CompanyKnowledge:
    """Load all required company knowledge files into a CompanyKnowledge instance.

    Args:
        company_dir: Optional custom path to company knowledge directory.
                     Defaults to data/company relative to project root.

    Returns:
        CompanyKnowledge containing contents of each markdown source.

    Raises:
        MissingKnowledgeFileError: If any of the required markdown files is missing.
    """
    directory = company_dir or DEFAULT_COMPANY_DIR
    if not directory.exists() or not directory.is_dir():
        raise MissingKnowledgeFileError(
            f"Company knowledge directory does not exist: {directory.resolve()}"
        )

    loaded_contents: dict[str, str] = {}

    for key, filename in REQUIRED_FILES.items():
        file_path = directory / filename
        if not file_path.exists() or not file_path.is_file():
            raise MissingKnowledgeFileError(
                f"Required knowledge file '{filename}' was not found at: {file_path.resolve()}"
            )
        try:
            loaded_contents[key] = file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            raise MissingKnowledgeFileError(
                f"Failed to read knowledge file '{filename}': {e}"
            ) from e

    return CompanyKnowledge(**loaded_contents)
