"""
RAG Enhancements Module - Quality, Performance, and Observability improvements.

This module provides:
1. Query rewriting - Optimize owner questions for better retrieval
2. Hybrid retrieval - Combine vector + full-text search
3. Source reranking - Reorder chunks by relevance
4. Chunk deduplication - Remove near-duplicates
5. Caching - Short TTL cache for identical queries
6. Metrics - Track retrieval quality and latency

All improvements are optional and configurable via RAGConfig.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .rag import RetrievedChunk, RAGResponse, Citation
from .vector_search import embed_single, SourceType

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================================
# Configuration
# ============================================================================


@dataclass
class RAGConfig:
    """Configuration for RAG enhancements. All features are optional."""
    
    # Query rewriting
    enable_query_rewrite: bool = True
    rewrite_model: str = "gpt-4o-mini"
    
    # Hybrid search
    enable_hybrid_search: bool = True
    vector_weight: float = 0.7  # Weight for vector similarity
    text_weight: float = 0.3   # Weight for full-text search
    
    # Reranking
    enable_reranking: bool = True
    rerank_top_n: int = 10  # Retrieve more, rerank to top-k
    
    # Deduplication
    enable_deduplication: bool = True
    similarity_dedup_threshold: float = 0.92  # Chunks more similar than this are duplicates
    
    # Caching
    enable_cache: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes
    max_cache_size: int = 100
    
    # Hard limits
    max_chunks_retrieved: int = 20
    max_context_tokens: int = 3000
    max_llm_tokens: int = 500
    
    # Metrics
    enable_metrics: bool = True


# Global config instance - can be overridden
_config = RAGConfig()


def get_rag_config() -> RAGConfig:
    return _config


def set_rag_config(config: RAGConfig) -> None:
    global _config
    _config = config


# ============================================================================
# Metrics Collection
# ============================================================================


@dataclass
class RAGMetrics:
    """Metrics for a single RAG request."""
    request_id: str
    timestamp: datetime
    shop_id: int
    
    # Query info
    original_query: str
    rewritten_query: str | None = None
    
    # Retrieval stats
    chunks_retrieved: int = 0
    chunks_above_threshold: int = 0
    chunks_after_dedup: int = 0
    chunks_sent_to_llm: int = 0
    
    # Quality indicators
    has_sufficient_evidence: bool = False
    top_similarity_score: float = 0.0
    avg_similarity_score: float = 0.0
    
    # Latency breakdown (milliseconds)
    query_rewrite_ms: float = 0.0
    embedding_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    llm_ms: float = 0.0
    total_ms: float = 0.0
    
    # Cache
    cache_hit: bool = False


# In-memory metrics store (bounded)
_metrics_store: list[RAGMetrics] = []
MAX_METRICS_STORE = 1000


def record_metrics(metrics: RAGMetrics) -> None:
    """Record metrics for observability."""
    global _metrics_store
    _metrics_store.append(metrics)
    if len(_metrics_store) > MAX_METRICS_STORE:
        _metrics_store = _metrics_store[-MAX_METRICS_STORE:]
    
    # Log summary
    logger.info(
        f"RAG metrics: query='{metrics.original_query[:50]}...' "
        f"chunks={metrics.chunks_above_threshold}/{metrics.chunks_retrieved} "
        f"evidence={metrics.has_sufficient_evidence} "
        f"total_ms={metrics.total_ms:.0f} "
        f"(rewrite={metrics.query_rewrite_ms:.0f}, embed={metrics.embedding_ms:.0f}, "
        f"retrieve={metrics.retrieval_ms:.0f}, llm={metrics.llm_ms:.0f})"
    )


def get_metrics_summary(shop_id: int | None = None, hours: int = 24) -> dict[str, Any]:
    """Get aggregated metrics summary."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    relevant = [m for m in _metrics_store if m.timestamp >= cutoff]
    if shop_id:
        relevant = [m for m in relevant if m.shop_id == shop_id]
    
    if not relevant:
        return {"total_requests": 0, "period_hours": hours}
    
    total = len(relevant)
    with_evidence = sum(1 for m in relevant if m.has_sufficient_evidence)
    cache_hits = sum(1 for m in relevant if m.cache_hit)
    
    avg_retrieval = sum(m.chunks_above_threshold for m in relevant) / total
    avg_latency = sum(m.total_ms for m in relevant) / total
    avg_llm_latency = sum(m.llm_ms for m in relevant) / total
    avg_retrieval_latency = sum(m.retrieval_ms for m in relevant) / total
    
    # Top queries (ANONYMIZED - strip PII before aggregating)
    def anonymize_query(q: str) -> str:
        """Remove potential PII from query for safe aggregation."""
        import re
        # Remove email patterns
        q = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]', q)
        # Remove phone patterns (various formats)
        q = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', q)
        q = re.sub(r'\(\d{3}\)\s?\d{3}[-.]?\d{4}', '[PHONE]', q)
        # Remove potential names after common patterns
        q = re.sub(r'\b(customer|stylist|client)\s+[A-Z][a-z]+\b', r'\1 [NAME]', q, flags=re.IGNORECASE)
        return q[:50].lower()
    
    query_counts: dict[str, int] = {}
    for m in relevant:
        key = anonymize_query(m.original_query)
        query_counts[key] = query_counts.get(key, 0) + 1
    top_queries = sorted(query_counts.items(), key=lambda x: -x[1])[:10]
    
    return {
        "total_requests": total,
        "period_hours": hours,
        "evidence_rate": round(with_evidence / total * 100, 1),
        "cache_hit_rate": round(cache_hits / total * 100, 1),
        "avg_chunks_retrieved": round(avg_retrieval, 1),
        "avg_total_latency_ms": round(avg_latency, 0),
        "avg_retrieval_latency_ms": round(avg_retrieval_latency, 0),
        "avg_llm_latency_ms": round(avg_llm_latency, 0),
        "top_query_patterns": [{"query": q[:30] + "...", "count": c} for q, c in top_queries[:5]],
    }


# ============================================================================
# Simple In-Memory Cache
# ============================================================================


@dataclass
class CacheEntry:
    """Cache entry for RAG responses."""
    response: RAGResponse
    created_at: datetime
    
    def is_expired(self, ttl_seconds: int) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(seconds=ttl_seconds)


_cache: dict[str, CacheEntry] = {}


def _cache_key(shop_id: int, question: str, filters: dict, config: RAGConfig) -> str:
    """
    Generate cache key from request parameters.
    
    Includes:
    - shop_id: Tenant isolation (CRITICAL)
    - question: Normalized
    - filters: All filter params
    - model version: Invalidates cache when model changes
    """
    # Include rewrite model in key so cache invalidates when model changes
    model_version = config.rewrite_model if config.enable_query_rewrite else "none"
    key_str = f"{shop_id}:{question.lower().strip()}:{sorted(filters.items())}:{model_version}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def cache_get(shop_id: int, question: str, filters: dict, config: RAGConfig) -> RAGResponse | None:
    """Get cached response if valid. Returns None on miss or expired."""
    if not config.enable_cache:
        return None
    
    key = _cache_key(shop_id, question, filters, config)
    entry = _cache.get(key)
    
    if entry and not entry.is_expired(config.cache_ttl_seconds):
        return entry.response
    
    # Clean expired
    if entry:
        del _cache[key]
    
    return None


def cache_set(shop_id: int, question: str, filters: dict, response: RAGResponse, config: RAGConfig) -> None:
    """Cache a response with size bounds."""
    if not config.enable_cache:
        return
    
    key = _cache_key(shop_id, question, filters, config)
    
    # Enforce max size (LRU-like: remove oldest)
    if len(_cache) >= config.max_cache_size:
        oldest_key = min(_cache.keys(), key=lambda k: _cache[k].created_at)
        del _cache[oldest_key]
    
    _cache[key] = CacheEntry(response=response, created_at=datetime.utcnow())


def cache_clear() -> None:
    """Clear all cache entries."""
    global _cache
    _cache = {}


# ============================================================================
# Query Rewriting
# ============================================================================

QUERY_REWRITE_PROMPT = """You are a search query optimizer for a salon business database.

Your task: Rewrite the owner's natural language question into an optimized search query that will find relevant call transcripts and booking notes.

Rules:
1. Extract key entities: customer names, services, stylists, dates
2. Include synonyms for common terms (e.g., "haircut" → "haircut cut trim")
3. Remove filler words (what, did, can you tell me)
4. Keep it concise (under 50 words)
5. Preserve temporal context (today, this week, yesterday)
6. Output ONLY the rewritten query, no explanation

Examples:
- "What did customers say about wait times?" → "customer wait time waiting long delay complaint feedback"
- "Any issues with the new stylist Alex?" → "Alex new stylist problem issue complaint feedback customer"
- "Summarize today's calls" → "today calls booking appointment service customer"
- "Did anyone ask about balayage?" → "balayage hair color highlight customer request booking"

Owner question: {question}

Optimized query:"""


async def rewrite_query(question: str, config: RAGConfig) -> tuple[str, float]:
    """
    Rewrite owner question into search-optimized query.
    
    Safety guards:
    - Max 200 chars to prevent prompt injection
    - Sanitized to prevent SQL injection in full-text search
    - No cross-tenant context (stateless rewrite)
    
    Returns:
        Tuple of (rewritten_query, latency_ms)
    """
    if not config.enable_query_rewrite:
        return question, 0.0
    
    # Guard: Limit input length to prevent abuse
    MAX_QUESTION_LEN = 500
    if len(question) > MAX_QUESTION_LEN:
        question = question[:MAX_QUESTION_LEN]
    
    start = time.time()
    
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=config.rewrite_model,
            messages=[
                {"role": "user", "content": QUERY_REWRITE_PROMPT.format(question=question)}
            ],
            max_tokens=100,
            temperature=0.0,
        )
        
        rewritten = response.choices[0].message.content.strip()
        
        # Safety: Limit rewritten query length
        MAX_REWRITE_LEN = 200
        if len(rewritten) > MAX_REWRITE_LEN:
            rewritten = rewritten[:MAX_REWRITE_LEN]
        
        # Safety: Sanitize for SQL full-text search (remove special chars that could break tsquery)
        # Only allow alphanumeric, spaces, and basic punctuation
        import re
        rewritten = re.sub(r"[^\w\s\-']", " ", rewritten)
        rewritten = re.sub(r"\s+", " ", rewritten).strip()
        
        # Fallback if sanitization produces empty string
        if not rewritten:
            rewritten = question[:MAX_REWRITE_LEN]
        
        latency = (time.time() - start) * 1000
        
        logger.debug(f"Query rewrite: '{question}' → '{rewritten}'")
        return rewritten, latency
        
    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")
        return question, (time.time() - start) * 1000


# ============================================================================
# Hybrid Search (Vector + Full-Text)
# ============================================================================


async def hybrid_search(
    session: AsyncSession,
    shop_id: int,
    query: str,
    query_embedding: list[float],
    *,
    limit: int = 10,
    config: RAGConfig,
    source_types: list[SourceType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    stylist_id: int | None = None,
    customer_id: int | None = None,
) -> list[RetrievedChunk]:
    """
    Hybrid search combining vector similarity and full-text search.
    
    Score = vector_weight * vector_similarity + text_weight * text_rank
    """
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    
    # Build filters
    filters = ["shop_id = :shop_id"]
    params: dict[str, Any] = {
        "shop_id": shop_id,
        "embedding": embedding_str,
        "limit": limit,
        "query": query,  # For full-text search
        "vector_weight": config.vector_weight,
        "text_weight": config.text_weight,
    }
    
    if source_types:
        placeholders = [f":st_{i}" for i in range(len(source_types))]
        filters.append(f"source_type IN ({','.join(placeholders)})")
        for i, st in enumerate(source_types):
            params[f"st_{i}"] = st.value
    
    if date_from:
        filters.append("created_at >= :date_from")
        params["date_from"] = date_from
    
    if date_to:
        filters.append("created_at <= :date_to")
        params["date_to"] = date_to
    
    if stylist_id is not None:
        filters.append("stylist_id = :stylist_id")
        params["stylist_id"] = stylist_id
    
    if customer_id is not None:
        filters.append("customer_id = :customer_id")
        params["customer_id"] = customer_id
    
    where_clause = " AND ".join(filters)
    
    if config.enable_hybrid_search:
        # Hybrid: combine vector and full-text scores
        # Note: Using ts_rank with plainto_tsquery for full-text
        search_sql = text(f"""
            WITH vector_scores AS (
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
                    1 - (embedding <=> :embedding) AS vector_sim
                FROM embedded_chunks
                WHERE {where_clause}
            ),
            text_scores AS (
                SELECT 
                    id,
                    ts_rank_cd(
                        to_tsvector('english', content),
                        plainto_tsquery('english', :query)
                    ) AS text_rank
                FROM embedded_chunks
                WHERE {where_clause}
                  AND to_tsvector('english', content) @@ plainto_tsquery('english', :query)
            )
            SELECT 
                v.id,
                v.source_type,
                v.source_id,
                v.booking_id,
                v.call_id,
                v.customer_id,
                v.stylist_id,
                v.content,
                v.chunk_index,
                v.created_at,
                COALESCE(
                    :vector_weight * v.vector_sim + :text_weight * COALESCE(t.text_rank, 0),
                    v.vector_sim
                ) AS combined_score
            FROM vector_scores v
            LEFT JOIN text_scores t ON v.id = t.id
            ORDER BY combined_score DESC
            LIMIT :limit
        """)
    else:
        # Pure vector search
        search_sql = text(f"""
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
                1 - (embedding <=> :embedding) AS combined_score
            FROM embedded_chunks
            WHERE {where_clause}
            ORDER BY embedding <=> :embedding
            LIMIT :limit
        """)
    
    result = await session.execute(search_sql, params)
    
    chunks = []
    for row in result.fetchall():
        chunks.append(RetrievedChunk(
            id=row[0],
            source_type=row[1],
            source_id=row[2],
            booking_id=row[3],
            call_id=row[4],
            customer_id=row[5],
            stylist_id=row[6],
            content=row[7],
            chunk_index=row[8],
            created_at=row[9],
            similarity=float(row[10]),
        ))
    
    return chunks


# ============================================================================
# Chunk Deduplication
# ============================================================================


def deduplicate_chunks(chunks: list[RetrievedChunk], threshold: float = 0.92, min_keep: int = 2) -> list[RetrievedChunk]:
    """
    Remove near-duplicate chunks based on content similarity.
    
    Uses simple Jaccard similarity on word sets for speed.
    Keeps the chunk with higher similarity score.
    
    Safety guards:
    - Always keeps at least min_keep chunks
    - Bounds O(n^2) by only comparing first 50 chunks
    """
    if len(chunks) <= 1:
        return chunks
    
    # Bound to prevent O(n^2) explosion on large result sets
    MAX_COMPARE = 50
    chunks_to_compare = chunks[:MAX_COMPARE]
    remainder = chunks[MAX_COMPARE:]
    
    def word_set(text: str) -> set[str]:
        return set(text.lower().split())
    
    def jaccard(s1: set[str], s2: set[str]) -> float:
        if not s1 or not s2:
            return 0.0
        intersection = len(s1 & s2)
        union = len(s1 | s2)
        return intersection / union if union > 0 else 0.0
    
    # Compute word sets once
    word_sets = [word_set(c.content) for c in chunks_to_compare]
    
    # Track which chunks to keep
    keep = [True] * len(chunks_to_compare)
    
    for i in range(len(chunks_to_compare)):
        if not keep[i]:
            continue
        for j in range(i + 1, len(chunks_to_compare)):
            if not keep[j]:
                continue
            sim = jaccard(word_sets[i], word_sets[j])
            if sim >= threshold:
                # Keep the one with higher similarity score
                if chunks_to_compare[i].similarity >= chunks_to_compare[j].similarity:
                    keep[j] = False
                else:
                    keep[i] = False
                    break
    
    # Collect kept chunks + remainder
    result = [c for c, k in zip(chunks_to_compare, keep) if k] + remainder
    
    # Safety: Always keep at least min_keep chunks
    if len(result) < min_keep and len(chunks) >= min_keep:
        return chunks[:min_keep]
    
    return result


# ============================================================================
# Reranking
# ============================================================================


def rerank_chunks(chunks: list[RetrievedChunk], question: str) -> list[RetrievedChunk]:
    """
    Simple keyword-based reranking boost.
    
    Boosts chunks that contain exact keywords from the question.
    No external reranker model needed.
    """
    if not chunks:
        return chunks
    
    # Extract keywords from question (simple approach)
    stop_words = {'what', 'did', 'do', 'does', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
                  'how', 'why', 'when', 'where', 'who', 'any', 'some', 'can', 'could',
                  'tell', 'me', 'about', 'my', 'our', 'their', 'this', 'that', 'and', 'or'}
    
    keywords = set(
        word.lower().strip('?.,!') 
        for word in question.split() 
        if word.lower() not in stop_words and len(word) > 2
    )
    
    if not keywords:
        return chunks
    
    def keyword_boost(chunk: RetrievedChunk) -> float:
        content_lower = chunk.content.lower()
        matches = sum(1 for kw in keywords if kw in content_lower)
        # Small boost per keyword match (max 20% boost)
        return min(0.2, matches * 0.05)
    
    # Apply boost and re-sort
    boosted = [
        (chunk, chunk.similarity + keyword_boost(chunk))
        for chunk in chunks
    ]
    boosted.sort(key=lambda x: -x[1])
    
    # Update similarity scores
    result = []
    for chunk, new_score in boosted:
        chunk.similarity = min(1.0, new_score)  # Cap at 1.0
        result.append(chunk)
    
    return result


# ============================================================================
# Enhanced RAG with All Improvements
# ============================================================================


async def enhanced_ask_with_citations(
    session: AsyncSession,
    shop_id: int,
    question: str,
    *,
    limit: int = 5,
    min_similarity: float = 0.35,
    source_types: list[SourceType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    stylist_id: int | None = None,
    customer_id: int | None = None,
    config: RAGConfig | None = None,
) -> tuple[RAGResponse, RAGMetrics]:
    """
    Enhanced RAG with query rewriting, hybrid search, reranking, and caching.
    
    Returns:
        Tuple of (RAGResponse, RAGMetrics)
    """
    import uuid as uuid_mod
    from .rag import format_context_for_rag, generate_grounded_answer, create_citations
    
    config = config or get_rag_config()
    request_id = str(uuid_mod.uuid4())[:8]
    start_time = time.time()
    
    # Initialize metrics
    metrics = RAGMetrics(
        request_id=request_id,
        timestamp=datetime.utcnow(),
        shop_id=shop_id,
        original_query=question,
    )
    
    # Build filter dict for cache key
    filters = {
        "limit": limit,
        "min_similarity": min_similarity,
        "source_types": [s.value for s in source_types] if source_types else None,
        "date_from": str(date_from) if date_from else None,
        "date_to": str(date_to) if date_to else None,
        "stylist_id": stylist_id,
        "customer_id": customer_id,
    }
    
    # Check cache
    cached = cache_get(shop_id, question, filters, config)
    if cached:
        metrics.cache_hit = True
        metrics.total_ms = (time.time() - start_time) * 1000
        metrics.has_sufficient_evidence = cached.has_sufficient_evidence
        if config.enable_metrics:
            record_metrics(metrics)
        return cached, metrics
    
    # Step 1: Query rewriting
    search_query, rewrite_ms = await rewrite_query(question, config)
    metrics.rewritten_query = search_query if search_query != question else None
    metrics.query_rewrite_ms = rewrite_ms
    
    # Step 2: Embed the search query
    embed_start = time.time()
    query_embedding = await embed_single(search_query)
    metrics.embedding_ms = (time.time() - embed_start) * 1000
    
    # Step 3: Hybrid retrieval
    retrieve_start = time.time()
    retrieval_limit = config.rerank_top_n if config.enable_reranking else limit
    retrieval_limit = min(retrieval_limit, config.max_chunks_retrieved)
    
    all_chunks = await hybrid_search(
        session=session,
        shop_id=shop_id,
        query=search_query,
        query_embedding=query_embedding,
        limit=retrieval_limit,
        config=config,
        source_types=source_types,
        date_from=date_from,
        date_to=date_to,
        stylist_id=stylist_id,
        customer_id=customer_id,
    )
    metrics.retrieval_ms = (time.time() - retrieve_start) * 1000
    metrics.chunks_retrieved = len(all_chunks)
    
    # Step 4: Filter by threshold
    chunks_above_threshold = [c for c in all_chunks if c.similarity >= min_similarity]
    metrics.chunks_above_threshold = len(chunks_above_threshold)
    
    # Step 5: Deduplication
    if config.enable_deduplication:
        chunks_deduped = deduplicate_chunks(chunks_above_threshold, config.similarity_dedup_threshold)
    else:
        chunks_deduped = chunks_above_threshold
    metrics.chunks_after_dedup = len(chunks_deduped)
    
    # Step 6: Reranking
    rerank_start = time.time()
    if config.enable_reranking:
        chunks_reranked = rerank_chunks(chunks_deduped, question)[:limit]
    else:
        chunks_reranked = chunks_deduped[:limit]
    metrics.reranking_ms = (time.time() - rerank_start) * 1000
    metrics.chunks_sent_to_llm = len(chunks_reranked)
    
    # Compute similarity stats
    if chunks_reranked:
        metrics.top_similarity_score = chunks_reranked[0].similarity
        metrics.avg_similarity_score = sum(c.similarity for c in chunks_reranked) / len(chunks_reranked)
    
    # Step 7: Handle no results
    if not chunks_reranked:
        response = RAGResponse(
            answer="No relevant data found in call transcripts or booking records for your question.",
            sources=[],
            has_sufficient_evidence=False,
            query=question,
            chunks_retrieved=metrics.chunks_retrieved,
            chunks_above_threshold=metrics.chunks_above_threshold,
        )
        metrics.has_sufficient_evidence = False
        metrics.total_ms = (time.time() - start_time) * 1000
        cache_set(shop_id, question, filters, response, config)
        if config.enable_metrics:
            record_metrics(metrics)
        return response, metrics
    
    # Step 8: Format context and generate answer
    llm_start = time.time()
    context, used_chunks = format_context_for_rag(chunks_reranked, config.max_context_tokens)
    answer, has_citations = await generate_grounded_answer(question, context, used_chunks)
    metrics.llm_ms = (time.time() - llm_start) * 1000
    
    # Step 9: Create response
    citations = create_citations(used_chunks)
    
    response = RAGResponse(
        answer=answer,
        sources=citations,
        has_sufficient_evidence=has_citations and len(used_chunks) > 0,
        query=question,
        chunks_retrieved=metrics.chunks_retrieved,
        chunks_above_threshold=metrics.chunks_above_threshold,
    )
    
    metrics.has_sufficient_evidence = response.has_sufficient_evidence
    metrics.total_ms = (time.time() - start_time) * 1000
    
    # Cache result
    cache_set(shop_id, question, filters, response, config)
    
    # Record metrics
    if config.enable_metrics:
        record_metrics(metrics)
    
    return response, metrics
