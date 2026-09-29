"""Unit tests for duplicate and repetition detection."""

from agent.repetition import (
    calculate_similarity,
    calculate_token_overlap,
    check_repetition,
    normalize_text,
)


def test_normalize_text():
    raw = "  Why AI Workflows Fail in 2026! (And How to Fix Them...)  "
    normalized = normalize_text(raw)
    assert normalized == "why ai workflows fail in 2026 and how to fix them"


def test_calculate_similarity_identical():
    sim = calculate_similarity("RAG Architecture in 2026", "rag architecture in 2026")
    assert sim == 1.0


def test_calculate_similarity_different():
    sim = calculate_similarity("Why Microservices Fail", "How to Train LLMs on Private Data")
    assert sim < 0.40


def test_token_overlap():
    t1 = "Why AI workflows fail in production"
    t2 = "Why workflows fail in production and scale"
    overlap = calculate_token_overlap(t1, t2)
    assert overlap > 0.5


def test_check_repetition_identical_topic():
    prev = [
        {
            "post_id": "JVY-20260901-001",
            "topic": "Evaluating RAG Architecture for Enterprise",
            "hook": "90% of RAG implementations struggle with data drift.",
        }
    ]
    is_rep, reason = check_repetition(
        candidate_topic="Evaluating RAG Architecture for Enterprise",
        previous_posts=prev,
    )
    assert is_rep is True
    assert "Identical topic" in reason


def test_check_repetition_similar_topic():
    prev = [
        {
            "post_id": "JVY-20260901-001",
            "topic": "Evaluating Enterprise RAG Architecture and Vectors",
            "hook": "Data drift kills enterprise search.",
        }
    ]
    is_rep, reason = check_repetition(
        candidate_topic="Evaluating Enterprise RAG Architectures and Vectors",
        previous_posts=prev,
        topic_threshold=0.70,
    )
    assert is_rep is True
    assert "Topic is too similar" in reason or "shares" in reason


def test_check_repetition_identical_hook():
    prev = [
        {
            "post_id": "JVY-20260901-001",
            "topic": "Something completely different",
            "hook": "Most teams build AI features backwards.",
        }
    ]
    is_rep, reason = check_repetition(
        candidate_topic="A Brand New AI Topic",
        candidate_hook="Most teams build AI features backwards.",
        previous_posts=prev,
    )
    assert is_rep is True
    assert "hook" in reason.lower()


def test_check_repetition_clean_unique_post():
    prev = [
        {
            "post_id": "JVY-20260901-001",
            "topic": "Deploying Kubernetes on Edge Hardware",
            "hook": "Edge computing brings latency down to 2ms.",
        }
    ]
    is_rep, reason = check_repetition(
        candidate_topic="Intelligent ETL Pipelines with Jevyam DataBridge",
        candidate_hook="Unstructured PDFs remain the hidden bottleneck for LLM applications.",
        previous_posts=prev,
    )
    assert is_rep is False
    assert reason is None
