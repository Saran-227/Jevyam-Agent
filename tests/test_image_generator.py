"""Unit tests for image brief generator, Gemini image provider, and persistent storage."""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.exceptions import ImageGenerationError, ImageStorageError
from agent.image_generator import (
    GeminiImageProvider,
    ImageBrief,
    MockImageProvider,
    PlaceholderImageProvider,
    expand_image_prompt,
    generate_image_brief,
)
from database.storage import MockStorageService, SupabaseStorageService


def test_placeholder_image_provider():
    brief = ImageBrief(
        visual_concept="Architecture diagram",
        style="Vector blueprint",
        composition="Centered",
        color_direction="Slate and indigo",
        text_on_image="DataBridge Architecture",
    )
    provider = PlaceholderImageProvider()
    result = provider.generate_image(brief)
    assert result is None


def test_generate_image_brief_with_mock():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "visual_concept": "Modular pipeline nodes synchronizing data into vector stores",
            "style": "Minimalist dark-mode isometric diagram",
            "composition": "Diagonal flow from bottom-left to top-right",
            "color_direction": "Deep charcoal background with neon cyan highlights",
            "text_on_image": "DataBridge in Action",
            "aspect_ratio": "1:1",
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    brief = generate_image_brief(
        client=mock_client,
        topic="ETL Data Pipelines",
        angle="Solving schema drift",
        hook="Data schemas break LLM apps silently.",
        caption="Data schemas break LLM apps silently. Here is how...",
        brand_voice="Professional tech firm",
    )

    assert isinstance(brief, ImageBrief)
    assert brief.text_on_image == "DataBridge in Action"
    assert brief.aspect_ratio == "1:1"
    assert "Modular pipeline" in brief.visual_concept


def test_expand_image_prompt_contains_constraints():
    brief = ImageBrief(
        visual_concept="Distributed streaming state machine",
        style="Minimalist technical 2D vector",
        composition="4:5 vertical framing with ample negative space",
        color_direction="Slate navy background with electric cyan trace lines",
        text_on_image="Fault Tolerance",
        aspect_ratio="4:5",
    )
    expanded = expand_image_prompt(brief)

    assert "Distributed streaming state machine" in expanded
    assert "Minimalist technical 2D vector" in expanded
    assert "Fault Tolerance" in expanded
    assert "Jevyam Technologies" in expanded
    # Verify negative prompts and quality guidelines
    assert "NO distorted or unreadable text" in expanded
    assert "NO fake company logos" in expanded
    assert "NO watermarks" in expanded


def test_gemini_image_provider_success_and_cleanup(tmp_path: Path):
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagebytes"
    mock_client = MagicMock()

    # Mock candidate with inline_data part
    part_mock = MagicMock()
    part_mock.inline_data.data = fake_png
    part_mock.inline_data.mime_type = "image/png"

    cand_mock = MagicMock()
    cand_mock.content.parts = [part_mock]

    resp_mock = MagicMock()
    resp_mock.candidates = [cand_mock]
    mock_client.models.generate_content.return_value = resp_mock

    storage = MockStorageService()
    provider = GeminiImageProvider(
        client=mock_client,
        storage_service=storage,
        model="gemini-3.1-flash-image",
    )

    brief = ImageBrief(
        visual_concept="Idempotent queue consumer architecture",
        style="Crisp vector diagram",
        composition="Center balanced",
        color_direction="Navy and cyan",
        text_on_image="Reliable Automation",
        aspect_ratio="1:1",
    )

    out_file = tmp_path / "saved_test.png"
    url = provider.generate_image(
        brief=brief,
        post_id="JVY-20261013-001",
        revision=1,
        output_path=out_file,
    )

    assert url is not None
    assert "JVY-20261013-001/rev_1.png" in url
    assert out_file.exists()
    assert out_file.read_bytes() == fake_png

    # Verify storage contains uploaded bytes
    assert "JVY-20261013-001/rev_1.png" in storage.stored_files
    stored_bytes, mime = storage.stored_files["JVY-20261013-001/rev_1.png"]
    assert stored_bytes == fake_png
    assert mime == "image/png"


def test_gemini_image_provider_failure_handling():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API Model Overload 503")

    provider = GeminiImageProvider(
        client=mock_client,
        storage_service=MockStorageService(),
    )

    brief = ImageBrief(
        visual_concept="Crashed visual",
        style="Sketch",
        composition="Off-center",
        color_direction="Red",
        text_on_image="None",
    )

    with pytest.raises(ImageGenerationError) as exc_info:
        provider.generate_image(brief=brief, post_id="JVY-ERR-001", revision=1)

    assert "Gemini image generation failed" in str(exc_info.value)


def test_mock_image_provider_success_and_failure():
    mock_provider = MockImageProvider(base_url="https://cdn.jevyam.com/images")
    brief = ImageBrief(
        visual_concept="Concept",
        style="Style",
        composition="Comp",
        color_direction="Col",
        text_on_image="Text",
    )

    url = mock_provider.generate_image(brief=brief, post_id="JVY-20261013-002", revision=2)
    assert url == "https://cdn.jevyam.com/images/JVY-20261013-002/rev_2.png"
    assert len(mock_provider.generated_images) == 1

    # Test failure mode
    failing_provider = MockImageProvider(should_fail=True)
    with pytest.raises(ImageGenerationError):
        failing_provider.generate_image(brief=brief, post_id="JVY-FAIL", revision=1)


def test_supabase_storage_service_upload():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.get_public_url.return_value = "https://my-project.supabase.co/storage/v1/object/public/post-images/JVY-001/rev_1_abcd.png"
    mock_client.storage.from_.return_value = mock_bucket

    storage = SupabaseStorageService(client=mock_client, bucket_name="post-images")
    url = storage.upload_image(
        post_id="JVY-001",
        revision=1,
        image_bytes=b"sample_image_bytes",
        mime_type="image/png",
    )

    assert url == "https://my-project.supabase.co/storage/v1/object/public/post-images/JVY-001/rev_1_abcd.png"
    mock_client.storage.from_.assert_called_with("post-images")
    mock_bucket.upload.assert_called_once()


def test_supabase_storage_service_failure():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.upload.side_effect = RuntimeError("Bucket access denied 403")
    mock_client.storage.from_.return_value = mock_bucket

    storage = SupabaseStorageService(client=mock_client, bucket_name="post-images")
    with pytest.raises(ImageStorageError) as exc_info:
        storage.upload_image(
            post_id="JVY-001",
            revision=1,
            image_bytes=b"sample_image_bytes",
        )

    assert "Bucket access denied" in str(exc_info.value)
