# Vector Search Setup Guide

This document explains how to set up and use pgvector semantic search for call transcripts and booking notes.

## Overview

The vector search system enables Owner GPT to answer questions about past call transcripts, call summaries, and booking notes using semantic similarity search powered by pgvector and OpenAI embeddings.

## Prerequisites

1. **Neon Postgres** with pgvector extension enabled
2. **OpenAI API key** for generating embeddings
3. Python dependencies: `pgvector`, `tiktoken` (already added to requirements.txt)

## Setup Steps

### 1. Run the Migration

Execute the SQL migration against your Neon database:

```bash
psql $DATABASE_URL < Backend/migrations/001_add_pgvector_chunks.sql
```

Or run via your preferred database tool (TablePlus, pgAdmin, Neon console, etc.).

The migration:
- Enables the `vector` extension
- Creates the `embedded_chunks` table
- Creates optimized indexes including HNSW for vector similarity
- Adds a helper function `search_chunks()` for direct SQL queries

### 2. Install Dependencies

```bash
pip install -r Backend/requirements.txt
```

New dependencies added:
- `pgvector==0.3.6` - PostgreSQL vector extension for SQLAlchemy
- `tiktoken==0.8.0` - Token counting (optional, for precise chunking)

### 3. Verify OpenAI API Key

Ensure `OPENAI_API_KEY` is set in your `.env` file:

```env
OPENAI_API_KEY=sk-...
```

## How It Works

### Automatic Ingestion

When a voice call completes and `generate_call_summary()` runs:
1. The call transcript is chunked (speaker-turn aware, ~512 tokens per chunk)
2. Each chunk is embedded using `text-embedding-3-small`
3. Chunks are stored in `embedded_chunks` table with the call metadata
4. Key notes are also embedded separately

This happens automatically - no manual intervention needed for new calls.

### Manual Ingestion (Backfill)

To backfill existing call summaries:

```bash
# Via API
curl -X POST http://localhost:8000/owner/ingest-call \
  -H "Content-Type: application/json" \
  -d '{"call_id": "uuid-of-call-summary"}'
```

Or programmatically:
```python
from app.vector_search import ingest_call_transcript

await ingest_call_transcript(
    session=db,
    shop_id=1,
    call_id=call_summary.id,
    transcript=call_summary.transcript,
    customer_id=customer.id,
    stylist_id=stylist.id,
)
```

### Semantic Search

#### Via API

```bash
curl -X POST http://localhost:8000/owner/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "customer complaints about wait time",
    "limit": 5,
    "min_similarity": 0.3
  }'
```

#### Via Owner GPT

Owner GPT automatically searches call transcripts when queries mention:
- calls, transcripts, conversations
- customer feedback, complaints
- what customers said/mentioned/asked

Example queries that trigger search:
- "What have customers said about our new hair treatment?"
- "Any complaints about wait times in the last week?"
- "What services has Sarah asked about in calls?"

## Architecture

### Embedding Model

- **Model**: `text-embedding-3-small`
- **Dimensions**: 1536
- **Cost**: ~$0.02 per 1M tokens

For higher quality (at higher cost), switch to `text-embedding-3-large` (3072 dims) by updating:
1. `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` in `vector_search.py`
2. The `vector(1536)` column in the migration

### Chunking Strategy

**For Transcripts:**
1. Split by speaker turns (`Agent:`, `Customer:`)
2. Merge small turns until ~512 tokens
3. Apply 50-token overlap for context continuity
4. Preserve speaker attribution

**For Summaries/Notes:**
1. Split by paragraphs
2. Enforce max 512 tokens per chunk
3. Apply overlap

### Vector Index

We use **HNSW** (Hierarchical Navigable Small World) instead of IVFFlat because:
- No training required (IVFFlat needs `lists` parameter tuning)
- Better recall on small-to-medium datasets
- Faster query times
- Slightly higher memory usage (acceptable for moderate scale)

### Multi-Tenancy

**Critical**: All operations filter by `shop_id` first.
- The `embedded_chunks` table enforces this via indexes
- The `search_chunks()` SQL function requires `shop_id` parameter
- Python functions all require `shop_id` argument

## API Endpoints

### POST /owner/search

Search call transcripts and notes semantically.

**Request:**
```json
{
  "query": "string (required)",
  "limit": 10,
  "source_types": ["call_transcript", "call_summary", "booking_note"],
  "customer_id": null,
  "stylist_id": null,
  "min_similarity": 0.3
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "uuid",
      "source_type": "call_transcript",
      "source_id": "uuid",
      "chunk_index": 0,
      "content": "Agent: How can I help you today?\nCustomer: I'd like to book a haircut.",
      "customer_id": 123,
      "stylist_id": 1,
      "created_at": "2025-01-15T10:30:00Z",
      "similarity": 0.87
    }
  ],
  "query": "booking a haircut",
  "total": 1
}
```

### POST /owner/ingest-call

Manually ingest a call summary into the vector store.

**Request:**
```json
{
  "call_id": "uuid-of-call-summary"
}
```

**Response:**
```json
{
  "success": true,
  "chunks_ingested": 5,
  "message": "Successfully ingested 5 chunks from call ..."
}
```

## Database Schema

```sql
CREATE TABLE embedded_chunks (
    id UUID PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    source_type TEXT NOT NULL,  -- 'call_transcript', 'call_summary', 'booking_note'
    source_id UUID NOT NULL,
    booking_id UUID,
    call_id UUID,
    customer_id INTEGER,
    stylist_id INTEGER,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_count INTEGER,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(shop_id, source_type, source_id, chunk_index)
);
```

## Tradeoffs & Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single `embedded_chunks` table | Simpler schema, unified search, easier maintenance |
| text-embedding-3-small | Best cost/quality ratio for search use cases |
| HNSW over IVFFlat | Better recall without training, faster for moderate scale |
| 512 token chunks | Balances context size vs. search granularity |
| Content hash for idempotency | Prevents duplicate ingestion, allows re-ingestion on change |
| Automatic ingestion on call complete | Zero manual intervention for new data |

## Troubleshooting

### "pgvector extension not found"
Run `CREATE EXTENSION IF NOT EXISTS vector;` as superuser or enable in Neon console.

### "OPENAI_API_KEY not configured"
Ensure the key is in your `.env` file and the app is restarted.

### Low similarity scores
- Check if embeddings were generated (query `embedded_chunks` table)
- Try more specific queries
- Lower `min_similarity` threshold

### Ingestion not happening
- Check logs for "Failed to ingest" warnings
- Verify transcript length >= 50 characters
- Check OpenAI API rate limits
