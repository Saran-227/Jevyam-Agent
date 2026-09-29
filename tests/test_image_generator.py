"""Unit tests for image brief generator and pluggable provider."""

import json
from unittest.mock import MagicMock

from agent.image_generator import (
    ImageBrief,
    PlaceholderImageProvider,
    generate_image_brief,
)


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
