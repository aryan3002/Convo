"""
Vector Search Module - Semantic search over call transcripts and booking notes using pgvector.

This module provides:
1. Text chunking with speaker-turn awareness
2. Batch embedding via OpenAI
3. Idempotent ingestion into pgvector
4. Semantic search with shop isolation

Design Choices:
- Embedding Model: text-embedding-3-small (1536 dims) - best cost/quality ratio
- Chunk Strategy: Speaker-turn aware, 512 tokens max, 50 token overlap
- Idempotency: Skip chunks with matching content_hash
- Multi-tenancy: All operations require shop_id

Feature Flag:
    ENABLE_EMBEDDINGS (default: False)
    When disabled, all embedding/search functions are no-ops that return empty results.
    Enable when pgvector is installed and ready (Phase 8).

Usage:
    from app.vector_search import ingest_call_transcript, search_similar_chunks
    
    # After call completes (no-op if embeddings disabled)
    await ingest_call_transcript(
        session=db,
        shop_id=shop_context.shop_id,
        call_id=call_summary.id,
        transcript="Agent: Hello...\nCustomer: Hi...",
        customer_id=customer.id,
        stylist_id=stylist.id,
    )
    
    # In owner chat (returns [] if embeddings disabled)
    results = await search_similar_chunks(
        session=db,
        shop_id=shop_context.shop_id,
        query="customer complaints about wait time",
        limit=5,
    )
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings

# Import shared types and conditional model from vector_models
from .vector_models import (
    SourceType,
    EmbeddedChunk,
    EMBEDDINGS_ENABLED,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    MAX_CHUNK_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    CHARS_PER_TOKEN,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================================
# Text Chunking
# ============================================================================

@dataclass
class Chunk:
    """A text chunk with metadata."""
    index: int
    content: str
    token_count: int
    content_hash: str


def normalize_text(text: str, for_embedding: bool = False) -> str:
    """
    Normalize text for consistent processing.
    - Collapse multiple whitespace
    - Strip leading/trailing whitespace
    - Normalize line endings
    - Optionally remove noise for embeddings (timestamps, fillers)
    """
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    if for_embedding:
        # Remove common transcript timestamps like [00:00:00] or (00:00)
        text = re.sub(r"\[\d{1,2}:\d{2}(?::\d{2})?\]", "", text)
        text = re.sub(r"\(\d{1,2}:\d{2}(?::\d{2})?\)", "", text)
        # Remove filler words that add noise to embeddings
        filler_pattern = r"\b(uh+|um+|hmm+|ah+|er+|like,?|you know,?)\b"
        text = re.sub(filler_pattern, "", text, flags=re.IGNORECASE)
    
    # Collapse multiple spaces (but preserve newlines for speaker turns)
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of normalized content."""
    normalized = normalize_text(content).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    
    Uses rough 4 chars/token ratio. For production, consider tiktoken:
        import tiktoken
        enc = tiktoken.encoding_for_model("text-embedding-3-small")
        return len(enc.encode(text))
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


def split_by_speaker_turns(transcript: str) -> list[str]:
    """
    Split transcript into speaker turns.
    
    Expects format:
        Agent: Hello, how can I help?
        Customer: I'd like to book an appointment.
        Agent: Sure, what service?
    
    Returns list of turns, each preserving the speaker prefix.
    """
    if not transcript:
        return []
    
    # Pattern matches "Speaker:" at start of line
    # Handles: Agent:, Customer:, User:, Assistant:, etc.
    turn_pattern = re.compile(r"^([A-Za-z_]+):\s*", re.MULTILINE)
    
    turns = []
    last_end = 0
    
    for match in turn_pattern.finditer(transcript):
        if match.start() > last_end:
            # There's content before this turn (shouldn't happen in clean transcripts)
            prefix_content = transcript[last_end:match.start()].strip()
            if prefix_content and turns:
                # Append to previous turn
                turns[-1] += " " + prefix_content
        
        # Find the end of this turn (start of next turn or end of string)
        next_match = turn_pattern.search(transcript, match.end())
        turn_end = next_match.start() if next_match else len(transcript)
        
        turn_content = transcript[match.start():turn_end].strip()
        if turn_content:
            turns.append(turn_content)
        
        last_end = turn_end
    
    # Handle case where transcript doesn't have speaker prefixes
    if not turns:
        # Fall back to paragraph splitting
        turns = [p.strip() for p in transcript.split("\n\n") if p.strip()]
        if not turns:
            turns = [transcript.strip()] if transcript.strip() else []
    
    return turns


def chunk_transcript(
    transcript: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Chunk a call transcript with speaker-turn awareness.
    
    Strategy:
    1. Split by speaker turns first
    2. Merge small turns together until max_tokens reached
    3. For single turns exceeding max_tokens, split by sentences
    4. Apply overlap for context continuity
    
    Returns list of Chunk objects with index, content, token count, and hash.
    """
    # Use enhanced normalization to remove timestamps/fillers for cleaner embeddings
    transcript = normalize_text(transcript, for_embedding=True)
    if not transcript:
        return []
    
    # Skip tiny transcripts that won't produce meaningful embeddings
    if len(transcript) < 50:
        logger.debug(f"Skipping tiny transcript: {len(transcript)} chars")
        return []
    
    turns = split_by_speaker_turns(transcript)
    if not turns:
        return []
    
    chunks: list[Chunk] = []
    current_content: list[str] = []
    current_tokens = 0
    
    def finalize_chunk() -> None:
        """Save current accumulated content as a chunk."""
        nonlocal current_content, current_tokens
        if current_content:
            content = "\n".join(current_content)
            chunks.append(Chunk(
                index=len(chunks),
                content=content,
                token_count=estimate_tokens(content),
                content_hash=compute_content_hash(content),
            ))
            
            # Apply overlap: keep last portion for next chunk
            if overlap_tokens > 0 and len(current_content) > 1:
                overlap_content = []
                overlap_token_count = 0
                for turn in reversed(current_content):
                    turn_tokens = estimate_tokens(turn)
                    if overlap_token_count + turn_tokens > overlap_tokens:
                        break
                    overlap_content.insert(0, turn)
                    overlap_token_count += turn_tokens
                current_content = overlap_content
                current_tokens = overlap_token_count
            else:
                current_content = []
                current_tokens = 0
    
    for turn in turns:
        turn_tokens = estimate_tokens(turn)
        
        # If single turn exceeds max, split it by sentences
        if turn_tokens > max_tokens:
            # First, finalize any pending content
            if current_content:
                finalize_chunk()
            
            # Split long turn by sentences
            sentences = re.split(r"(?<=[.!?])\s+", turn)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                sent_tokens = estimate_tokens(sentence)
                
                if current_tokens + sent_tokens > max_tokens and current_content:
                    finalize_chunk()
                
                current_content.append(sentence)
                current_tokens += sent_tokens
        else:
            # Normal case: accumulate turns
            if current_tokens + turn_tokens > max_tokens and current_content:
                finalize_chunk()
            
            current_content.append(turn)
            current_tokens += turn_tokens
    
    # Finalize remaining content
    if current_content:
        content = "\n".join(current_content)
        chunks.append(Chunk(
            index=len(chunks),
            content=content,
            token_count=estimate_tokens(content),
            content_hash=compute_content_hash(content),
        ))
    
    # Filter out chunks that are too small to be useful (< 20 tokens)
    MIN_CHUNK_TOKENS = 20
    chunks = [c for c in chunks if c.token_count >= MIN_CHUNK_TOKENS]
    
    # Re-index after filtering
    for i, chunk in enumerate(chunks):
        chunk.index = i
    
    return chunks


def chunk_text_simple(
    text: str,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Simple chunking for non-transcript text (summaries, notes).
    
    Splits by paragraphs, then sentences if needed.
    """
    text = normalize_text(text)
    if not text:
        return []
    
    # For short text, return as single chunk
    if estimate_tokens(text) <= max_tokens:
        return [Chunk(
            index=0,
            content=text,
            token_count=estimate_tokens(text),
            content_hash=compute_content_hash(text),
        )]
    
    # Split by paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text]
    
    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        
        if current_tokens + para_tokens > max_tokens and current_parts:
            # Finalize current chunk
            content = "\n\n".join(current_parts)
            chunks.append(Chunk(
                index=len(chunks),
                content=content,
                token_count=estimate_tokens(content),
                content_hash=compute_content_hash(content),
            ))
            # Overlap: keep last paragraph
            if overlap_tokens > 0 and current_parts:
                last_para = current_parts[-1]
                if estimate_tokens(last_para) <= overlap_tokens:
                    current_parts = [last_para]
                    current_tokens = estimate_tokens(last_para)
                else:
                    current_parts = []
                    current_tokens = 0
            else:
                current_parts = []
                current_tokens = 0
        
        current_parts.append(para)
        current_tokens += para_tokens
    
    # Finalize remaining
    if current_parts:
        content = "\n\n".join(current_parts)
        chunks.append(Chunk(
            index=len(chunks),
            content=content,
            token_count=estimate_tokens(content),
            content_hash=compute_content_hash(content),
        ))
    
    return chunks


# ============================================================================
# Embedding
# ============================================================================

async def embed_texts(
    texts: list[str],
    batch_size: int = 100,
) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenAI API.
    
    Batches requests to stay within API limits.
    Returns list of embedding vectors in same order as input.
    
    Raises:
        ValueError: If embeddings disabled or no API key configured
        OpenAI API errors propagate up
    """
    if not EMBEDDINGS_ENABLED:
        logger.debug("Embeddings disabled, skipping embed_texts")
        raise ValueError("Embeddings are disabled (ENABLE_EMBEDDINGS=False)")
    
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")
    
    if not texts:
        return []
    
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        
        # Sort by index to maintain order (API may return out of order)
        sorted_embeddings = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([e.embedding for e in sorted_embeddings])
    
    return all_embeddings


async def embed_single(text: str) -> list[float]:
    """
    Embed a single text. Convenience wrapper around embed_texts.
    
    Raises ValueError if embeddings are disabled.
    """
    if not EMBEDDINGS_ENABLED:
        raise ValueError("Embeddings are disabled (ENABLE_EMBEDDINGS=False)")
    embeddings = await embed_texts([text])
    return embeddings[0]


# ============================================================================
# Ingestion
# ============================================================================

async def ingest_chunks(
    session: AsyncSession,
    shop_id: int,
    source_type: SourceType,
    source_id: uuid.UUID,
    chunks: list[Chunk],
    *,
    booking_id: uuid.UUID | None = None,
    call_id: uuid.UUID | None = None,
    customer_id: int | None = None,
    stylist_id: int | None = None,
) -> int:
    """
    Ingest text chunks into pgvector table.
    
    Idempotent: Skips chunks that already exist (by shop_id, source_type, source_id, chunk_index).
    Returns 0 (no-op) if embeddings are disabled.
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation
        source_type: Type of source content
        source_id: ID of the source record
        chunks: List of Chunk objects to ingest
        booking_id: Optional related booking
        call_id: Optional related call summary
        customer_id: Optional related customer
        stylist_id: Optional related stylist
    
    Returns:
        Number of chunks inserted (excluding skipped duplicates), 0 if disabled
    """
    if not EMBEDDINGS_ENABLED:
        logger.debug("Embeddings disabled, skipping ingest_chunks for %s/%s", source_type.value, source_id)
        return 0
    
    if not chunks:
        return 0
    
    # Check which chunks already exist
    existing_query = text("""
        SELECT chunk_index, content_hash 
        FROM embedded_chunks 
        WHERE shop_id = :shop_id 
          AND source_type = :source_type 
          AND source_id = :source_id
    """)
    
    result = await session.execute(
        existing_query,
        {
            "shop_id": shop_id,
            "source_type": source_type.value,
            "source_id": str(source_id),
        }
    )
    existing = {row[0]: row[1] for row in result.fetchall()}
    
    # Filter to only new or changed chunks
    chunks_to_embed: list[tuple[int, Chunk]] = []
    for chunk in chunks:
        existing_hash = existing.get(chunk.index)
        if existing_hash is None:
            # New chunk
            chunks_to_embed.append((chunk.index, chunk))
        elif existing_hash != chunk.content_hash:
            # Content changed - delete old and re-insert
            await session.execute(
                text("""
                    DELETE FROM embedded_chunks 
                    WHERE shop_id = :shop_id 
                      AND source_type = :source_type 
                      AND source_id = :source_id 
                      AND chunk_index = :chunk_index
                """),
                {
                    "shop_id": shop_id,
                    "source_type": source_type.value,
                    "source_id": str(source_id),
                    "chunk_index": chunk.index,
                }
            )
            chunks_to_embed.append((chunk.index, chunk))
        # else: unchanged, skip
    
    if not chunks_to_embed:
        logger.info(f"All {len(chunks)} chunks already exist for {source_type.value}/{source_id}")
        return 0
    
    # Generate embeddings for new chunks
    texts_to_embed = [chunk.content for _, chunk in chunks_to_embed]
    embeddings = await embed_texts(texts_to_embed)
    
    # Insert new chunks
    inserted = 0
    for (original_index, chunk), embedding in zip(chunks_to_embed, embeddings):
        # Format embedding as pgvector string
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        
        insert_query = text("""
            INSERT INTO embedded_chunks (
                id, shop_id, source_type, source_id, booking_id, call_id,
                customer_id, stylist_id, chunk_index, content, content_hash,
                token_count, embedding, created_at
            ) VALUES (
                gen_random_uuid(), :shop_id, :source_type, :source_id, :booking_id, :call_id,
                :customer_id, :stylist_id, :chunk_index, :content, :content_hash,
                :token_count, :embedding, NOW()
            )
            ON CONFLICT (shop_id, source_type, source_id, chunk_index) DO NOTHING
        """)
        
        await session.execute(
            insert_query,
            {
                "shop_id": shop_id,
                "source_type": source_type.value,
                "source_id": str(source_id),
                "booking_id": str(booking_id) if booking_id else None,
                "call_id": str(call_id) if call_id else None,
                "customer_id": customer_id,
                "stylist_id": stylist_id,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "token_count": chunk.token_count,
                "embedding": embedding_str,
            }
        )
        inserted += 1
    
    await session.commit()
    logger.info(f"Ingested {inserted} chunks for {source_type.value}/{source_id}")
    return inserted


async def ingest_call_transcript(
    session: AsyncSession,
    shop_id: int,
    call_id: uuid.UUID,
    transcript: str,
    *,
    booking_id: uuid.UUID | None = None,
    customer_id: int | None = None,
    stylist_id: int | None = None,
) -> int:
    """
    Ingest a call transcript into the vector store.
    
    Chunks the transcript with speaker-turn awareness and embeds.
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation
        call_id: Call summary ID (used as source_id)
        transcript: Full transcript text (with speaker prefixes)
        booking_id: Optional related booking
        customer_id: Optional related customer
        stylist_id: Optional related stylist
    
    Returns:
        Number of chunks ingested
    """
    chunks = chunk_transcript(transcript)
    return await ingest_chunks(
        session=session,
        shop_id=shop_id,
        source_type=SourceType.CALL_TRANSCRIPT,
        source_id=call_id,
        chunks=chunks,
        booking_id=booking_id,
        call_id=call_id,
        customer_id=customer_id,
        stylist_id=stylist_id,
    )


async def ingest_call_summary(
    session: AsyncSession,
    shop_id: int,
    call_id: uuid.UUID,
    summary_text: str,
    *,
    booking_id: uuid.UUID | None = None,
    customer_id: int | None = None,
    stylist_id: int | None = None,
) -> int:
    """
    Ingest a call summary (key notes) into the vector store.
    """
    chunks = chunk_text_simple(summary_text)
    return await ingest_chunks(
        session=session,
        shop_id=shop_id,
        source_type=SourceType.CALL_SUMMARY,
        source_id=call_id,
        chunks=chunks,
        booking_id=booking_id,
        call_id=call_id,
        customer_id=customer_id,
        stylist_id=stylist_id,
    )


async def ingest_booking_note(
    session: AsyncSession,
    shop_id: int,
    booking_id: uuid.UUID,
    note_text: str,
    *,
    customer_id: int | None = None,
    stylist_id: int | None = None,
) -> int:
    """
    Ingest a booking note into the vector store.
    """
    chunks = chunk_text_simple(note_text)
    return await ingest_chunks(
        session=session,
        shop_id=shop_id,
        source_type=SourceType.BOOKING_NOTE,
        source_id=booking_id,
        chunks=chunks,
        booking_id=booking_id,
        customer_id=customer_id,
        stylist_id=stylist_id,
    )


# ============================================================================
# Search
# ============================================================================

@dataclass
class SearchResult:
    """A search result with relevance score."""
    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    chunk_index: int
    content: str
    customer_id: int | None
    stylist_id: int | None
    created_at: datetime
    similarity: float  # 0.0 to 1.0, higher is more similar


async def search_similar_chunks(
    session: AsyncSession,
    shop_id: int,
    query: str,
    *,
    limit: int = 10,
    source_types: list[SourceType] | None = None,
    customer_id: int | None = None,
    stylist_id: int | None = None,
    min_similarity: float = 0.0,
) -> list[SearchResult]:
    """
    Search for chunks similar to the query text.
    
    Returns empty list if embeddings are disabled.
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation (REQUIRED)
        query: Natural language search query
        limit: Maximum number of results
        source_types: Filter by source types (None = all)
        customer_id: Filter by customer
        stylist_id: Filter by stylist
        min_similarity: Minimum similarity score (0.0 to 1.0)
    
    Returns:
        List of SearchResult objects ordered by similarity (highest first), empty if disabled
    """
    if not EMBEDDINGS_ENABLED:
        logger.debug("Embeddings disabled, returning empty search results")
        return []
    
    # Embed the query
    query_embedding = await embed_single(query)
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    
    # Build the search query
    # Using cosine distance operator <=> for similarity
    # 1 - distance = similarity (cosine distance is 0 for identical, 2 for opposite)
    
    source_type_filter = ""
    if source_types:
        types_list = ",".join(f"'{st.value}'" for st in source_types)
        source_type_filter = f"AND source_type IN ({types_list})"
    
    customer_filter = ""
    if customer_id is not None:
        customer_filter = f"AND customer_id = {customer_id}"
    
    stylist_filter = ""
    if stylist_id is not None:
        stylist_filter = f"AND stylist_id = {stylist_id}"
    
    search_query = text(f"""
        SELECT 
            id,
            source_type,
            source_id,
            chunk_index,
            content,
            customer_id,
            stylist_id,
            created_at,
            1 - (embedding <=> :embedding) AS similarity
        FROM embedded_chunks
        WHERE shop_id = :shop_id
            {source_type_filter}
            {customer_filter}
            {stylist_filter}
        ORDER BY embedding <=> :embedding
        LIMIT :limit
    """)
    
    result = await session.execute(
        search_query,
        {
            "shop_id": shop_id,
            "embedding": embedding_str,
            "limit": limit,
        }
    )
    
    results = []
    for row in result.fetchall():
        similarity = float(row[8])
        if similarity >= min_similarity:
            results.append(SearchResult(
                id=uuid.UUID(str(row[0])),
                source_type=row[1],
                source_id=uuid.UUID(str(row[2])),
                chunk_index=row[3],
                content=row[4],
                customer_id=row[5],
                stylist_id=row[6],
                created_at=row[7],
                similarity=similarity,
            ))
    
    return results


async def get_context_for_query(
    session: AsyncSession,
    shop_id: int,
    query: str,
    *,
    max_tokens: int = 2000,
    limit: int = 10,
) -> str:
    """
    Get relevant context chunks formatted for LLM consumption.
    
    Retrieves similar chunks and formats them as context,
    respecting a token budget.
    
    Returns empty string if embeddings are disabled.
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation
        query: Natural language query
        max_tokens: Maximum tokens in returned context
        limit: Maximum chunks to retrieve
    
    Returns:
        Formatted context string for injection into LLM prompt, empty if disabled
    """
    if not EMBEDDINGS_ENABLED:
        logger.debug("Embeddings disabled, returning empty context")
        return ""
    
    results = await search_similar_chunks(
        session=session,
        shop_id=shop_id,
        query=query,
        limit=limit,
        min_similarity=0.3,  # Filter out low-quality matches
    )
    
    if not results:
        return ""
    
    context_parts = []
    total_tokens = 0
    
    for result in results:
        chunk_tokens = estimate_tokens(result.content)
        if total_tokens + chunk_tokens > max_tokens:
            break
        
        # Format with source info
        source_label = result.source_type.replace("_", " ").title()
        context_parts.append(f"[{source_label}]\n{result.content}")
        total_tokens += chunk_tokens
    
    return "\n\n---\n\n".join(context_parts)
