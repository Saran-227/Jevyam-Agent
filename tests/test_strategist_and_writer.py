"""Unit tests for strategist and writer modules with mocked Gemini client."""

import json
from unittest.mock import MagicMock

from agent.knowledge import CompanyKnowledge
from agent.strategist import ContentIdea, format_previous_posts_summary, select_content_idea
from agent.writer import LinkedInPostContent, generate_linkedin_post


def get_mock_company_knowledge() -> CompanyKnowledge:
    return CompanyKnowledge(
        profile="Jevyam Technologies builds AI and custom software systems.",
        products="Jevyam Workflow Copilot and Jevyam DataBridge.",
        services="Generative AI, Process Automation, Full-Stack Engineering.",
        brand_voice="Professional, grounded, no buzzwords, no fake stats.",
    )


def test_format_previous_posts_summary():
    posts = [
        {"post_id": "JVY-20260901-001", "topic": "RAG Pipelines", "angle": "Chunking", "hook": "Chunking matters"},
        {"post_id": "JVY-20260902-001", "topic": "Agent Workflows", "angle": "Human-in-the-loop", "hook": "Stop fully autonomous chaos"},
    ]
    summary = format_previous_posts_summary(posts)
    assert "JVY-20260901-001" in summary
    assert "RAG Pipelines" in summary
    assert "Agent Workflows" in summary


def test_select_content_idea_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "topic": "Why Context Windows Don't Replace Clean ETL",
            "angle": "Relying purely on larger LLM context windows leads to latency spikes and hallucination risks",
            "content_type": "technology insight",
            "target_audience": "CTOs and Lead Engineers",
            "reason": "Addresses a common architectural misconception with practical data engineering solutions.",
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    knowledge = get_mock_company_knowledge()
    idea = select_content_idea(
        client=mock_client,
        company_knowledge=knowledge,
        previous_posts=[],
        current_date="2026-09-29",
    )

    assert isinstance(idea, ContentIdea)
    assert idea.topic == "Why Context Windows Don't Replace Clean ETL"
    assert idea.content_type == "technology insight"
    assert idea.target_audience == "CTOs and Lead Engineers"


def test_generate_linkedin_post_mocked():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "hook": "A 1-million token context window won't fix dirty data.",
            "caption": "A 1-million token context window won't fix dirty data.\n\nMany engineering teams assume larger context windows eliminate the need for data transformation.\n\nIn reality, dumping raw PDFs into context increases token costs and latency while degrading retrieval accuracy.\n\nAt Jevyam Technologies, we prioritize structured preprocessing with solutions like Jevyam DataBridge.\n\nHow is your team handling unstructured data preprocessing?",
            "hashtags": ["#SoftwareEngineering", "#AI", "#DataEngineering", "#MachineLearning", "#CloudArchitecture"],
            "call_to_action": "How is your team handling unstructured data preprocessing?",
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    knowledge = get_mock_company_knowledge()
    idea = ContentIdea(
        topic="Why Context Windows Don't Replace Clean ETL",
        angle="Latency and noise",
        content_type="technology insight",
        target_audience="CTOs",
        reason="Timely",
    )

    post = generate_linkedin_post(
        client=mock_client,
        company_knowledge=knowledge,
        idea=idea,
        previous_posts=[],
    )

    assert isinstance(post, LinkedInPostContent)
    assert post.hook == "A 1-million token context window won't fix dirty data."
    assert len(post.hashtags) == 5
    assert all(tag.startswith("#") for tag in post.hashtags)
