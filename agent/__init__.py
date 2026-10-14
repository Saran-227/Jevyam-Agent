"""Jevyam AI Content Marketing Agent package."""

from agent.exceptions import (
    CompanyKnowledgeError,
    ContentGenerationError,
    DuplicateContentError,
    GeminiAPIError,
    GeminiAuthError,
    GeminiNetworkError,
    GeminiRateLimitError,
    GeminiUnavailableError,
    ImageGenerationError,
    ImageRequiredError,
    ImageStorageError,
    InvalidGeminiResponseError,
    JevyamAgentError,
    MissingGeminiApiKeyError,
    MissingKnowledgeFileError,
)

__all__ = [
    "CompanyKnowledge",
    "load_company_knowledge",
    "ContentIdea",
    "select_content_idea",
    "LinkedInPostContent",
    "generate_linkedin_post",
    "ImageBrief",
    "generate_image_brief",
    "BaseImageProvider",
    "BrandedPillowImageProvider",
    "BrandedImageProvider",
    "render_branded_image",
    "GeminiImageProvider",
    "MockImageProvider",
    "resolve_image_provider",
    "is_valid_image_url",
    "LinkedInDraft",
    "run_content_pipeline",
    "regenerate_draft",
    "load_previous_drafts",
    "save_draft",
    "generate_post_id",
    "check_repetition",
    "JevyamAgentError",
    "MissingGeminiApiKeyError",
    "CompanyKnowledgeError",
    "MissingKnowledgeFileError",
    "GeminiAPIError",
    "GeminiAuthError",
    "GeminiNetworkError",
    "GeminiRateLimitError",
    "GeminiUnavailableError",
    "InvalidGeminiResponseError",
    "DuplicateContentError",
    "ContentGenerationError",
    "ImageGenerationError",
    "ImageStorageError",
    "ImageRequiredError",
]


def __getattr__(name: str):
    if name in (
        "BaseImageProvider",
        "BrandedPillowImageProvider",
        "BrandedImageProvider",
        "GeminiImageProvider",
        "ImageBrief",
        "MockImageProvider",
        "resolve_image_provider",
        "is_valid_image_url",
        "generate_image_brief",
    ):
        from agent import image_generator

        return getattr(image_generator, name)
    if name in ("render_branded_image",):
        from agent import branded_renderer

        return getattr(branded_renderer, name)
    if name in ("CompanyKnowledge", "load_company_knowledge"):
        from agent import knowledge

        return getattr(knowledge, name)
    if name in (
        "LinkedInDraft",
        "generate_post_id",
        "load_previous_drafts",
        "regenerate_draft",
        "run_content_pipeline",
        "save_draft",
    ):
        from agent import pipeline

        return getattr(pipeline, name)
    if name in ("check_repetition",):
        from agent import repetition

        return getattr(repetition, name)
    if name in ("ContentIdea", "select_content_idea"):
        from agent import strategist

        return getattr(strategist, name)
    if name in ("LinkedInPostContent", "generate_linkedin_post"):
        from agent import writer

        return getattr(writer, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
