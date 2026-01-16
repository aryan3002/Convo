# RAG (Retrieval-Augmented Generation) Implementation

This document describes the RAG implementation for Owner GPT, enabling grounded answers with explicit citations over call transcripts and booking history.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User Question  │────▶│  /owner/search   │────▶│   Raw Chunks    │
│                 │     │  (no LLM)        │     │   + Metadata    │
└─────────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User Question  │────▶│   /owner/ask     │────▶│  Grounded       │
│  + Filters      │     │   (RAG)          │     │  Answer + Cites │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                 ┌─────────────────────────────┐
                 │  1. Embed question          │
                 │  2. Retrieve top-k chunks   │
                 │  3. Filter by threshold     │
                 │  4. Format context          │
                 │  5. LLM generates answer    │
                 │  6. Validate citations      │
                 └─────────────────────────────┘
```

## Files Created/Modified

### Created
- **`Backend/app/rag.py`** - Core RAG module with:
  - `search_chunks_with_filters()` - Enhanced similarity search
  - `ask_with_citations()` - Main RAG entry point
  - `generate_grounded_answer()` - LLM answer generation
  - `format_context_for_rag()` - Context formatting
  - `Citation` and `RAGResponse` data classes
  - `RAG_SYSTEM_PROMPT` - Grounding prompt template

### Modified
- **`Backend/app/main.py`** - Added endpoints:
  - Enhanced `POST /owner/search` with date filters and full metadata
  - New `POST /owner/ask` for RAG Q&A with citations

---

## API Endpoints

### POST /owner/search

**Purpose:** Raw similarity search over embedded chunks. No LLM calls.

**Request:**
```json
{
    "query": "customer complaints about pricing",
    "limit": 10,
    "min_similarity": 0.35,
    "source_types": ["call_transcript", "call_summary"],
    "date_from": "2026-01-01",
    "date_to": "2026-01-15",
    "stylist_id": 5,
    "customer_id": null
}
```

**Response:**
```json
{
    "results": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "source_type": "call_transcript",
            "source_id": "123e4567-e89b-12d3-a456-426614174000",
            "booking_id": null,
            "call_id": "123e4567-e89b-12d3-a456-426614174000",
            "chunk_index": 0,
            "content": "Customer: I was surprised by the final price...",
            "customer_id": 42,
            "stylist_id": 5,
            "created_at": "2026-01-10T14:30:00Z",
            "similarity": 0.7823
        }
    ],
    "query": "customer complaints about pricing",
    "total": 3
}
```

**Filters:**
| Filter | Type | Description |
|--------|------|-------------|
| `query` | string | Natural language search query (required) |
| `limit` | int | Max results (1-50, default: 10) |
| `min_similarity` | float | Minimum relevance (0.0-1.0, default: 0.3) |
| `source_types` | list | `call_transcript`, `call_summary`, `booking_note` |
| `date_from` | string | Start date YYYY-MM-DD |
| `date_to` | string | End date YYYY-MM-DD |
| `stylist_id` | int | Filter by stylist |
| `customer_id` | int | Filter by customer |

---

### POST /owner/ask

**Purpose:** RAG-powered Q&A with grounded answers and explicit citations.

**Request:**
```json
{
    "question": "What did customers say about wait times this week?",
    "limit": 5,
    "min_similarity": 0.35,
    "date_from": "2026-01-08",
    "date_to": "2026-01-15"
}
```

**Response:**
```json
{
    "answer": "Based on the call transcripts, two customers mentioned wait times this week. One customer expressed frustration about waiting 15 minutes past their appointment time [Source 1]. Another customer praised the salon for being ready on time despite their early arrival [Source 2].",
    "sources": [
        {
            "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
            "source_type": "call_transcript",
            "source_id": "123e4567-e89b-12d3-a456-426614174000",
            "booking_id": null,
            "call_id": "123e4567-e89b-12d3-a456-426614174000",
            "excerpt": "Customer: I had to wait almost 15 minutes...",
            "similarity": 0.7234,
            "created_at": "2026-01-10T14:30:00Z"
        },
        {
            "chunk_id": "661e8400-e29b-41d4-a716-446655440001",
            "source_type": "call_transcript",
            "source_id": "234e4567-e89b-12d3-a456-426614174001",
            "booking_id": null,
            "call_id": "234e4567-e89b-12d3-a456-426614174001",
            "excerpt": "Customer: I arrived early and they took me right away...",
            "similarity": 0.6891,
            "created_at": "2026-01-12T10:15:00Z"
        }
    ],
    "has_sufficient_evidence": true,
    "query": "What did customers say about wait times this week?",
    "chunks_retrieved": 8,
    "chunks_above_threshold": 5
}
```

**Response Fields:**
| Field | Description |
|-------|-------------|
| `answer` | LLM-generated answer with [Source N] citations |
| `sources` | Array of cited sources with excerpts and metadata |
| `has_sufficient_evidence` | True if answer has valid citations |
| `chunks_retrieved` | Total chunks found before threshold filter |
| `chunks_above_threshold` | Chunks meeting similarity threshold |

---

## Example SQL for Similarity Search

```sql
-- Similarity search with all filters
-- Uses cosine distance operator <=> from pgvector
-- 1 - distance = similarity score (0 to 1, higher = more similar)

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
ORDER BY embedding <=> $1                       -- order by distance (ascending)
LIMIT 5;                                        -- top-k

-- Note: $1 is the query embedding as a vector literal: '[0.1, 0.2, ...]'
-- The embedding column uses the HNSW index for fast approximate nearest neighbor
```

---

## RAG Prompt Template

The system uses a strict grounding prompt to ensure factual, cited answers:

```
You are a helpful assistant that answers questions about salon operations 
based ONLY on the provided context.

STRICT RULES:
1. Answer ONLY using information from the CONTEXT section below.
2. If the context doesn't contain enough information to answer, say 
   "I don't have enough information from the available records to answer this question."
3. NEVER speculate or infer information not explicitly stated in the context.
4. ALWAYS cite your sources using [Source N] notation.
5. Keep answers concise: 5-7 sentences maximum.
6. Every factual claim MUST have at least one citation.
7. If asked about dates, times, or specific details not in the context, 
   acknowledge you don't have that information.
8. Do not make up customer names, stylist names, or any other details.

CITATION FORMAT:
- Use [Source 1], [Source 2], etc. to cite specific sources
- You may cite multiple sources for the same claim: [Source 1, Source 2]
- Place citations immediately after the relevant statement

CONTEXT:
[Source 1] (Relevance: 78.2%)
Type: Call Transcript | Date: 2026-01-10 14:30 | Call ID: 123e4567...
---
Customer: I was surprised by the final price. The service was great though.
Agent: I apologize for any confusion about the pricing...

[Source 2] (Relevance: 65.4%)
...

---
Remember: No citations = No answer. If you cannot cite a source, say you don't have that information.
```

---

## Guardrails and Failure Modes

### 1. No Relevant Chunks Found
**Trigger:** Zero chunks above `min_similarity` threshold

**Response:**
```json
{
    "answer": "No relevant data found in call transcripts or booking records for your question.",
    "sources": [],
    "has_sufficient_evidence": false,
    "chunks_retrieved": 5,
    "chunks_above_threshold": 0
}
```

### 2. LLM Answer Without Citations
**Trigger:** LLM generates answer but doesn't include `[Source N]` markers and doesn't indicate lack of information

**Response:**
```json
{
    "answer": "I found some potentially relevant information but cannot provide a reliable answer without proper source verification. Please try rephrasing your question or being more specific.",
    "sources": [...],
    "has_sufficient_evidence": false,
    ...
}
```

### 3. Insufficient Evidence
**Trigger:** LLM explicitly states it cannot answer from context

**Response:** LLM's refusal message is returned with `has_sufficient_evidence: false`

### 4. API Error
**Trigger:** OpenAI API failure or database error

**Response:** HTTP 500 with error message

---

## Configuration Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `DEFAULT_TOP_K` | 5 | Default chunks to retrieve |
| `MIN_SIMILARITY_THRESHOLD` | 0.35 | Default minimum similarity |
| `MAX_CONTEXT_TOKENS` | 3000 | Max tokens for context |
| `MAX_ANSWER_SENTENCES` | 7 | Target answer length |
| `EMBEDDING_MODEL` | text-embedding-3-small | OpenAI model |
| `LLM_MODEL` | gpt-4o-mini | Answer generation model |
| `TEMPERATURE` | 0.1 | Low temperature for factual answers |

---

## Multi-Tenant Isolation

**All queries filter by `shop_id`:**
- `shop_id` is mandatory on every vector search query
- Obtained from `get_default_shop(session)` in endpoints
- Prevents data leakage between tenants

```sql
-- Every query includes:
WHERE shop_id = :shop_id  -- Never omitted
```

---

## Testing Examples

### Test 1: Basic RAG Query
```bash
curl -X POST http://localhost:8000/owner/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What services did customers book this week?",
    "limit": 5
  }'
```

### Test 2: Filtered Search
```bash
curl -X POST http://localhost:8000/owner/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "haircut booking",
    "date_from": "2026-01-10",
    "date_to": "2026-01-15",
    "source_types": ["call_transcript"],
    "min_similarity": 0.4
  }'
```

### Test 3: Customer-Specific Query
```bash
curl -X POST http://localhost:8000/owner/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What did this customer request in their calls?",
    "customer_id": 42,
    "limit": 10
  }'
```

### Test 4: No Results (Guardrail Test)
```bash
curl -X POST http://localhost:8000/owner/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the weather like?",
    "min_similarity": 0.9
  }'
# Should return: "No relevant data found..."
```

---

## Performance Considerations

1. **HNSW Index**: Uses approximate nearest neighbor for fast search
2. **Token Budget**: Context is capped at 3000 tokens to control costs
3. **Embedding Caching**: Query embeddings are computed once per request
4. **Batch Processing**: Multiple chunks are fetched in a single query
5. **Similarity Filtering**: Early filtering reduces LLM context size

---

## Future Enhancements

1. **Hybrid Search**: Combine vector + keyword search for better recall
2. **Re-ranking**: Use cross-encoder for re-ranking top results
3. **Answer Caching**: Cache common question-answer pairs
4. **Streaming**: Stream LLM responses for better UX
5. **Feedback Loop**: Learn from user corrections
