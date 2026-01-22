"""
Tests for ENABLE_EMBEDDINGS feature flag.

Verifies that the backend can start and operate without pgvector when
ENABLE_EMBEDDINGS=False (the default).

Run: pytest Backend/tests/test_embeddings_disabled.py -v
Or: cd Backend && ENABLE_EMBEDDINGS=false pytest tests/test_embeddings_disabled.py -v
"""

import os
import sys
from pathlib import Path

# Add parent to path for standalone running
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# Ensure embeddings are disabled for these tests
os.environ["ENABLE_EMBEDDINGS"] = "false"


def test_embeddings_disabled_by_default():
    """Verify ENABLE_EMBEDDINGS defaults to False."""
    from app.core.config import get_settings
    
    settings = get_settings()
    # Default should be False (disabled)
    # Note: This test may fail if env var is set to true elsewhere
    assert settings.enable_embeddings is False, (
        "ENABLE_EMBEDDINGS should default to False. "
        "Ensure no env var is overriding this."
    )


def test_vector_models_does_not_define_embedded_chunk_when_disabled():
    """Verify EmbeddedChunk is None when embeddings are disabled."""
    from app.vector_models import EmbeddedChunk, EMBEDDINGS_ENABLED
    
    assert EMBEDDINGS_ENABLED is False, "Expected EMBEDDINGS_ENABLED=False for this test"
    assert EmbeddedChunk is None, (
        "EmbeddedChunk should be None when embeddings are disabled"
    )


def test_embedded_chunks_not_in_metadata_when_disabled():
    """Verify embedded_chunks table is not registered in SQLAlchemy metadata."""
    from app.core.db import Base
    
    table_names = list(Base.metadata.tables.keys())
    assert "embedded_chunks" not in table_names, (
        f"embedded_chunks should NOT be in Base.metadata when disabled. "
        f"Found tables: {table_names}"
    )


def test_source_type_enum_importable_when_disabled():
    """SourceType enum should be importable even when embeddings are disabled."""
    from app.vector_search import SourceType
    
    assert SourceType.CALL_TRANSCRIPT == "call_transcript"
    assert SourceType.CALL_SUMMARY == "call_summary"
    assert SourceType.BOOKING_NOTE == "booking_note"


@pytest.mark.asyncio
async def test_search_similar_chunks_returns_empty_when_disabled():
    """search_similar_chunks should return empty list when disabled."""
    from app.vector_search import search_similar_chunks, EMBEDDINGS_ENABLED
    
    assert EMBEDDINGS_ENABLED is False
    
    # Mock session (not actually used since we return early)
    class MockSession:
        pass
    
    results = await search_similar_chunks(
        session=MockSession(),  # type: ignore
        shop_id=1,
        query="test query",
    )
    
    assert results == [], "Expected empty list when embeddings disabled"


@pytest.mark.asyncio
async def test_get_context_for_query_returns_empty_when_disabled():
    """get_context_for_query should return empty string when disabled."""
    from app.vector_search import get_context_for_query, EMBEDDINGS_ENABLED
    
    assert EMBEDDINGS_ENABLED is False
    
    class MockSession:
        pass
    
    context = await get_context_for_query(
        session=MockSession(),  # type: ignore
        shop_id=1,
        query="test query",
    )
    
    assert context == "", "Expected empty string when embeddings disabled"


@pytest.mark.asyncio
async def test_ingest_call_transcript_noop_when_disabled():
    """ingest_call_transcript should be a no-op when disabled."""
    import uuid
    from app.vector_search import ingest_call_transcript, EMBEDDINGS_ENABLED
    
    assert EMBEDDINGS_ENABLED is False
    
    class MockSession:
        pass
    
    count = await ingest_call_transcript(
        session=MockSession(),  # type: ignore
        shop_id=1,
        call_id=uuid.uuid4(),
        transcript="Agent: Hello\nCustomer: Hi",
    )
    
    assert count == 0, "Expected 0 chunks ingested when embeddings disabled"


@pytest.mark.asyncio  
async def test_embed_single_raises_when_disabled():
    """embed_single should raise ValueError when embeddings are disabled."""
    from app.vector_search import embed_single, EMBEDDINGS_ENABLED
    
    assert EMBEDDINGS_ENABLED is False
    
    with pytest.raises(ValueError, match="Embeddings are disabled"):
        await embed_single("test text")


def test_chunking_functions_work_when_disabled():
    """Text chunking functions should work even when embeddings are disabled."""
    from app.vector_search import (
        chunk_transcript,
        chunk_text_simple,
        normalize_text,
        compute_content_hash,
    )
    
    # These are pure functions that don't need pgvector
    text = "Agent: Hello, how can I help?\nCustomer: I want to book an appointment."
    
    normalized = normalize_text(text)
    assert "Agent:" in normalized
    
    hash_val = compute_content_hash(text)
    assert len(hash_val) == 64  # SHA256 hex
    
    chunks = chunk_transcript(text)
    assert isinstance(chunks, list)
    
    simple_chunks = chunk_text_simple("Short text for testing.")
    assert isinstance(simple_chunks, list)


def test_app_can_be_imported_without_pgvector():
    """Verify the FastAPI app can be imported without pgvector installed."""
    # This is the critical test - if this fails, the app won't start
    try:
        from app.main import app
        assert app is not None
        assert app.title == "Convo Booking Backend"
    except ImportError as e:
        if "pgvector" in str(e):
            pytest.fail(
                f"App import failed due to pgvector: {e}. "
                "ENABLE_EMBEDDINGS feature flag should prevent this."
            )
        raise


def test_owner_chat_importable_when_disabled():
    """owner_chat module should be importable when embeddings are disabled."""
    from app.owner_chat import OwnerChatRequest, OwnerChatResponse
    
    assert OwnerChatRequest is not None
    assert OwnerChatResponse is not None


def test_call_summary_importable_when_disabled():
    """call_summary module should be importable when embeddings are disabled."""
    from app.call_summary import generate_call_summary
    
    assert generate_call_summary is not None


def test_rag_importable_when_disabled():
    """rag module should be importable when embeddings are disabled."""
    from app.rag import ask_with_citations, RAGResponse
    
    assert ask_with_citations is not None
    assert RAGResponse is not None
