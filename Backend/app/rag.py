"""
RAG (Retrieval-Augmented Generation) Module for Owner GPT.

Provides grounded answers with explicit citations over:
- Call transcripts
- Call summaries  
- Booking notes

Design Principles:
1. Multi-tenant isolation: All queries filter by shop_id
2. Grounded answers: LLM must cite sources, no speculation
3. Explicit citations: Every answer includes source excerpts
4. Guardrails: Refusal when evidence is insufficient

Usage:
    from app.rag import ask_with_citations
    
    response = await ask_with_citations(
        session=db,
        shop_id=shop_context.shop_id,
        question="What did customers complain about this week?",
        date_from="2026-01-08",
        date_to="2026-01-15",
    )
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .vector_search import embed_single, SourceType, EMBEDDINGS_ENABLED

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================================
# Configuration
# ============================================================================

# Default retrieval settings
DEFAULT_TOP_K = 5
MIN_SIMILARITY_THRESHOLD = 0.35  # Below this, chunks are too dissimilar
MAX_ANSWER_SENTENCES = 7

# Token budgets
MAX_CONTEXT_TOKENS = 3000  # Max tokens for retrieved context
CHARS_PER_TOKEN = 4  # Approximate


# ============================================================================
# Similarity Helpers (Consistent across all retrieval)
# ============================================================================

def cosine_distance_to_similarity(distance: float) -> float:
    """
    Convert pgvector cosine distance to similarity score.
    
    pgvector <=> operator returns cosine distance (0 = identical, 2 = opposite).
    We convert to similarity: 1 - distance (range: -1 to 1, typically 0 to 1).
    
    This is THE canonical function - use it everywhere for consistency.
    """
    return max(0.0, 1.0 - distance)


def is_above_threshold(similarity: float, threshold: float = MIN_SIMILARITY_THRESHOLD) -> bool:
    """
    Check if similarity score meets threshold.
    Use this instead of inline comparisons for consistency.
    """
    return similarity >= threshold

# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class RetrievedChunk:
    """A chunk retrieved from vector search with full metadata."""
    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    booking_id: uuid.UUID | None
    call_id: uuid.UUID | None
    customer_id: int | None
    stylist_id: int | None
    content: str
    similarity: float
    created_at: datetime
    chunk_index: int


@dataclass
class Citation:
    """A citation reference for an answer."""
    chunk_id: str
    source_type: str
    source_id: str
    booking_id: str | None
    call_id: str | None
    excerpt: str  # Truncated content for display
    similarity: float
    created_at: str


@dataclass
class RAGResponse:
    """Response from RAG query."""
    answer: str
    sources: list[Citation]
    has_sufficient_evidence: bool
    query: str
    chunks_retrieved: int
    chunks_above_threshold: int


# ============================================================================
# Pydantic Models for API
# ============================================================================


class AskRequest(BaseModel):
    """Request for /owner/ask endpoint."""
    question: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    limit: int = Field(default=DEFAULT_TOP_K, ge=1, le=20, description="Max chunks to retrieve")
    min_similarity: float = Field(default=MIN_SIMILARITY_THRESHOLD, ge=0.0, le=1.0)
    
    # Optional filters
    source_types: list[str] | None = Field(default=None, description="Filter by source types")
    date_from: str | None = Field(default=None, description="Start date (YYYY-MM-DD)")
    date_to: str | None = Field(default=None, description="End date (YYYY-MM-DD)")
    stylist_id: int | None = Field(default=None, description="Filter by stylist")
    customer_id: int | None = Field(default=None, description="Filter by customer")


class AskSource(BaseModel):
    """A source citation in the response."""
    chunk_id: str
    source_type: str
    source_id: str
    booking_id: str | None = None
    call_id: str | None = None
    excerpt: str
    similarity: float
    created_at: str


class AskResponse(BaseModel):
    """Response for /owner/ask endpoint."""
    answer: str
    sources: list[AskSource]
    has_sufficient_evidence: bool
    query: str
    chunks_retrieved: int
    chunks_above_threshold: int


# ============================================================================
# RAG Prompt Template
# ============================================================================

RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions about salon operations based ONLY on the provided context.

STRICT RULES:
1. Answer ONLY using information from the CONTEXT section below.
2. If the context doesn't contain enough information to answer, say "I don't have enough information from the available records to answer this question."
3. NEVER speculate or infer information not explicitly stated in the context.
4. ALWAYS cite your sources using [Source N] notation, where N corresponds to the source number in the context.
5. Keep answers concise: 5-7 sentences maximum.
6. Every factual claim MUST have at least one citation.
7. If asked about dates, times, or specific details not in the context, acknowledge you don't have that information.
8. Do not make up customer names, stylist names, or any other details.

CITATION FORMAT:
- Use [Source 1], [Source 2], etc. to cite specific sources
- You may cite multiple sources for the same claim: [Source 1, Source 2]
- Place citations immediately after the relevant statement

CONTEXT:
{context}

---
Remember: No citations = No answer. If you cannot cite a source, say you don't have that information."""

RAG_USER_PROMPT = """Based on the context provided above, answer the following question:

Question: {question}

Provide a clear, concise answer with citations. If the context doesn't contain relevant information, say so."""


# ============================================================================
# Enhanced Search with Filters
# ============================================================================


async def search_chunks_with_filters(
    session: AsyncSession,
    shop_id: int,
    query: str,
    *,
    limit: int = DEFAULT_TOP_K,
    min_similarity: float = MIN_SIMILARITY_THRESHOLD,
    source_types: list[SourceType] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    stylist_id: int | None = None,
    customer_id: int | None = None,
) -> list[RetrievedChunk]:
    """
    Search for similar chunks with comprehensive filters.
    
    This is an enhanced version of search_similar_chunks that includes:
    - Date range filtering
    - Returns full metadata including booking_id and call_id
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation (REQUIRED)
        query: Natural language search query
        limit: Maximum number of results
        min_similarity: Minimum similarity threshold
        source_types: Filter by source types
        date_from: Filter chunks created on or after this date
        date_to: Filter chunks created on or before this date
        stylist_id: Filter by stylist
        customer_id: Filter by customer
    
    Returns:
        List of RetrievedChunk objects with full metadata
    """
    # Embed the query
    query_embedding = await embed_single(query)
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    
    # Build dynamic WHERE clauses
    filters = ["shop_id = :shop_id"]
    params: dict[str, Any] = {
        "shop_id": shop_id,
        "embedding": embedding_str,
        "limit": limit,
    }
    
    # Source type filter
    if source_types:
        placeholders = [f":st_{i}" for i in range(len(source_types))]
        filters.append(f"source_type IN ({','.join(placeholders)})")
        for i, st in enumerate(source_types):
            params[f"st_{i}"] = st.value
    
    # Date range filters
    if date_from:
        filters.append("created_at >= :date_from")
        params["date_from"] = datetime.combine(date_from, datetime.min.time())
    
    if date_to:
        filters.append("created_at <= :date_to")
        params["date_to"] = datetime.combine(date_to, datetime.max.time())
    
    # Entity filters
    if stylist_id is not None:
        filters.append("stylist_id = :stylist_id")
        params["stylist_id"] = stylist_id
    
    if customer_id is not None:
        filters.append("customer_id = :customer_id")
        params["customer_id"] = customer_id
    
    where_clause = " AND ".join(filters)
    
    # Execute search with cosine similarity
    # 1 - (embedding <=> query) gives similarity score (1.0 = identical)
    search_query = text(f"""
        SELECT 
            id,
            source_type,
            source_id,
            booking_id,
            call_id,
            customer_id,
            stylist_id,
            content,
            chunk_index,
            created_at,
            1 - (embedding <=> :embedding) AS similarity
        FROM embedded_chunks
        WHERE {where_clause}
        ORDER BY embedding <=> :embedding
        LIMIT :limit
    """)
    
    result = await session.execute(search_query, params)
    
    chunks = []
    for row in result.fetchall():
        similarity = float(row[10])
        if similarity >= min_similarity:
            chunks.append(RetrievedChunk(
                id=uuid.UUID(str(row[0])),
                source_type=row[1],
                source_id=uuid.UUID(str(row[2])) if row[2] else None,
                booking_id=uuid.UUID(str(row[3])) if row[3] else None,
                call_id=uuid.UUID(str(row[4])) if row[4] else None,
                customer_id=row[5],
                stylist_id=row[6],
                content=row[7],
                chunk_index=row[8],
                created_at=row[9],
                similarity=similarity,
            ))
    
    return chunks


# ============================================================================
# Context Formatting
# ============================================================================


def format_context_for_rag(chunks: list[RetrievedChunk], max_tokens: int = MAX_CONTEXT_TOKENS) -> tuple[str, list[RetrievedChunk]]:
    """
    Format retrieved chunks into context string for LLM.
    
    Returns:
        Tuple of (formatted_context, chunks_used)
    """
    if not chunks:
        return "", []
    
    context_parts = []
    used_chunks = []
    total_chars = 0
    max_chars = max_tokens * CHARS_PER_TOKEN
    
    for i, chunk in enumerate(chunks, start=1):
        # Format source label
        source_label = chunk.source_type.replace("_", " ").title()
        date_str = chunk.created_at.strftime("%Y-%m-%d %H:%M") if chunk.created_at else "Unknown date"
        
        # Build metadata line
        metadata_parts = [f"Type: {source_label}", f"Date: {date_str}"]
        if chunk.call_id:
            metadata_parts.append(f"Call ID: {str(chunk.call_id)[:8]}...")
        if chunk.booking_id:
            metadata_parts.append(f"Booking ID: {str(chunk.booking_id)[:8]}...")
        if chunk.customer_id:
            metadata_parts.append(f"Customer ID: {chunk.customer_id}")
        if chunk.stylist_id:
            metadata_parts.append(f"Stylist ID: {chunk.stylist_id}")
        
        metadata_line = " | ".join(metadata_parts)
        similarity_pct = round(chunk.similarity * 100, 1)
        
        # Format the source block
        source_block = f"""[Source {i}] (Relevance: {similarity_pct}%)
{metadata_line}
---
{chunk.content}"""
        
        # Check token budget
        block_chars = len(source_block)
        if total_chars + block_chars > max_chars:
            break
        
        context_parts.append(source_block)
        used_chunks.append(chunk)
        total_chars += block_chars
    
    return "\n\n".join(context_parts), used_chunks


def create_citations(chunks: list[RetrievedChunk], max_excerpt_length: int = 200) -> list[Citation]:
    """
    Create citation objects from retrieved chunks.
    """
    citations = []
    for chunk in chunks:
        # Truncate excerpt for display
        excerpt = chunk.content
        if len(excerpt) > max_excerpt_length:
            excerpt = excerpt[:max_excerpt_length - 3].rsplit(" ", 1)[0] + "..."
        
        citations.append(Citation(
            chunk_id=str(chunk.id),
            source_type=chunk.source_type,
            source_id=str(chunk.source_id) if chunk.source_id else "",
            booking_id=str(chunk.booking_id) if chunk.booking_id else None,
            call_id=str(chunk.call_id) if chunk.call_id else None,
            excerpt=excerpt,
            similarity=round(chunk.similarity, 4),
            created_at=chunk.created_at.isoformat() if chunk.created_at else "",
        ))
    
    return citations


# ============================================================================
# RAG Answer Generation
# ============================================================================


async def generate_grounded_answer(
    question: str,
    context: str,
    chunks_used: list[RetrievedChunk],
) -> tuple[str, bool]:
    """
    Generate an answer grounded in the retrieved context.
    
    Returns:
        Tuple of (answer_text, has_valid_citations)
    
    Guardrails:
    - Validates [Source N] references exist in chunks_used
    - Rejects answers with fabricated citations
    - Refuses if LLM speculates beyond sources
    """
    if not context or not chunks_used:
        return "I don't have any relevant records to answer this question.", False
    
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    system_prompt = RAG_SYSTEM_PROMPT.format(context=context)
    user_prompt = RAG_USER_PROMPT.format(question=question)
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,  # Enough for 5-7 sentences
            temperature=0.1,  # Low temperature for factual responses
        )
        
        answer = response.choices[0].message.content or ""
        
        # Validate citations reference actual sources
        import re
        citation_pattern = re.compile(r"\[Source\s*(\d+)\]")
        cited_indices = set(int(m) for m in citation_pattern.findall(answer))
        max_valid_source = len(chunks_used)
        
        # Check for invalid citations (references to non-existent sources)
        invalid_citations = [i for i in cited_indices if i < 1 or i > max_valid_source]
        if invalid_citations:
            logger.warning(f"Answer contains invalid citation indices: {invalid_citations}")
            answer = (
                "I found relevant information but encountered an issue with source verification. "
                "Please try rephrasing your question."
            )
            return answer, False
        
        # Check if answer has valid citations
        has_citations = len(cited_indices) > 0 and not invalid_citations
        
        # Guardrail: If answer claims to have info but no citations, force refusal
        if not has_citations and not any(phrase in answer.lower() for phrase in [
            "don't have", "no information", "not enough", "cannot find",
            "no relevant", "unable to", "no records"
        ]):
            logger.warning("Answer generated without citations - applying guardrail")
            answer = (
                "I found some potentially relevant information but cannot provide "
                "a reliable answer without proper source verification. "
                "Please try rephrasing your question or being more specific."
            )
            has_citations = False
        
        return answer.strip(), has_citations
        
    except Exception as e:
        logger.exception(f"Error generating RAG answer: {e}")
        return "I encountered an error while processing your question. Please try again.", False


# ============================================================================
# Main RAG Function
# ============================================================================


async def ask_with_citations(
    session: AsyncSession,
    shop_id: int,
    question: str,
    *,
    limit: int = DEFAULT_TOP_K,
    min_similarity: float = MIN_SIMILARITY_THRESHOLD,
    source_types: list[SourceType] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    stylist_id: int | None = None,
    customer_id: int | None = None,
) -> RAGResponse:
    """
    Answer a question with grounded citations from call transcripts and booking data.
    
    This is the main RAG entry point that:
    1. Retrieves relevant chunks via vector search
    2. Applies similarity threshold filtering
    3. Formats context for LLM
    4. Generates grounded answer with citations
    5. Returns structured response with sources
    
    Returns a "feature disabled" response if embeddings are disabled.
    
    Args:
        session: Database session
        shop_id: Shop ID for multi-tenant isolation (REQUIRED)
        question: Natural language question
        limit: Max chunks to retrieve
        min_similarity: Similarity threshold (chunks below are discarded)
        source_types: Filter by source types
        date_from: Filter by start date
        date_to: Filter by end date
        stylist_id: Filter by stylist
        customer_id: Filter by customer
    
    Returns:
        RAGResponse with answer, sources, and metadata
    
    Guardrails:
        - If embeddings disabled: Returns "feature not enabled" message
        - If no chunks above threshold: Returns "No relevant data found"
        - If LLM answer has no citations: Applies refusal
        - Answer is capped at ~7 sentences
    """
    # Check if embeddings are enabled
    if not EMBEDDINGS_ENABLED:
        logger.info("RAG ask_with_citations called but embeddings are disabled")
        return RAGResponse(
            answer="Semantic search over call transcripts is not currently enabled. "
                   "This feature will be available in a future update.",
            sources=[],
            has_sufficient_evidence=False,
            query=question,
            total_chunks_retrieved=0,
            chunks_above_threshold=0,
        )
    
    # Step 1: Retrieve chunks
    all_chunks = await search_chunks_with_filters(
        session=session,
        shop_id=shop_id,
        query=question,
        limit=limit,
        min_similarity=0.0,  # Get all, filter in-memory for stats
        source_types=source_types,
        date_from=date_from,
        date_to=date_to,
        stylist_id=stylist_id,
        customer_id=customer_id,
    )
    
    # Step 2: Filter by threshold
    chunks_above_threshold = [c for c in all_chunks if c.similarity >= min_similarity]
    
    # Step 3: Handle no results
    if not chunks_above_threshold:
        return RAGResponse(
            answer="No relevant data found in call transcripts or booking records for your question.",
            sources=[],
            has_sufficient_evidence=False,
            query=question,
            chunks_retrieved=len(all_chunks),
            chunks_above_threshold=0,
        )
    
    # Step 4: Format context
    context, used_chunks = format_context_for_rag(chunks_above_threshold)
    
    # Step 5: Generate answer
    answer, has_citations = await generate_grounded_answer(question, context, used_chunks)
    
    # Step 6: Create citations
    citations = create_citations(used_chunks)
    
    return RAGResponse(
        answer=answer,
        sources=citations,
        has_sufficient_evidence=has_citations and len(used_chunks) > 0,
        query=question,
        chunks_retrieved=len(all_chunks),
        chunks_above_threshold=len(chunks_above_threshold),
    )


# ============================================================================
# SQL Reference (for documentation)
# ============================================================================

EXAMPLE_SIMILARITY_SEARCH_SQL = """
-- Similarity search with all filters
-- Uses cosine distance operator <=>
-- 1 - distance = similarity score (0 to 1)

SELECT 
    id,
    source_type,
    source_id,
    booking_id,
    call_id,
    customer_id,
    stylist_id,
    content,
    chunk_index,
    created_at,
    1 - (embedding <=> $1) AS similarity
FROM embedded_chunks
WHERE shop_id = $2                              -- MANDATORY: tenant isolation
  AND source_type IN ('call_transcript', 'call_summary')  -- optional
  AND created_at >= '2026-01-01'                -- optional: date range start
  AND created_at <= '2026-01-15'                -- optional: date range end
  AND stylist_id = 5                            -- optional
  AND customer_id = 10                          -- optional
ORDER BY embedding <=> $1                       -- order by distance (ascending = most similar first)
LIMIT 5;                                        -- top-k

-- Note: $1 is the query embedding as a vector literal: '[0.1, 0.2, ...]'
-- The embedding column uses the HNSW index for fast approximate nearest neighbor search
"""
