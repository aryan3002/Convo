"""
Vector Models Module - Conditional pgvector model loading.

This module conditionally defines the EmbeddedChunk model based on the 
ENABLE_EMBEDDINGS feature flag. When embeddings are disabled (default),
this module provides no-op stubs that prevent pgvector from being imported.

Why this pattern:
- pgvector SQLAlchemy integration requires CREATE EXTENSION vector in Postgres
- If pgvector is not installed, importing the Vector type will fail at table creation
- This allows the app to run and migrate without pgvector until Phase 8

Usage:
    from app.vector_models import EmbeddedChunk, EMBEDDINGS_ENABLED
    
    if EMBEDDINGS_ENABLED:
        # Safe to use EmbeddedChunk
        pass
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from .core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Feature flag - controls whether pgvector models are loaded
EMBEDDINGS_ENABLED = settings.enable_embeddings


class SourceType(str, Enum):
    """Types of content that can be embedded."""
    CALL_TRANSCRIPT = "call_transcript"
    CALL_SUMMARY = "call_summary"
    BOOKING_NOTE = "booking_note"


# Configuration constants (needed by vector_search even when disabled)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
MAX_CHUNK_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4


# Conditional model loading
EmbeddedChunk = None  # Default to None when disabled

if EMBEDDINGS_ENABLED:
    try:
        from pgvector.sqlalchemy import Vector
        from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Index, CheckConstraint
        from sqlalchemy.dialects.postgresql import UUID
        from sqlalchemy.orm import Mapped, mapped_column
        
        from .core.db import Base
        
        class EmbeddedChunk(Base):
            """
            Stores embedded text chunks for semantic search.
            
            All queries MUST filter by shop_id for multi-tenant isolation.
            Only defined when ENABLE_EMBEDDINGS=True.
            """
            __tablename__ = "embedded_chunks"

            id: Mapped[uuid.UUID] = mapped_column(
                UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
            )
            shop_id: Mapped[int] = mapped_column(
                Integer, ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True
            )
            source_type: Mapped[str] = mapped_column(String(32), nullable=False)
            source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
            
            # Optional foreign keys for filtering
            booking_id: Mapped[uuid.UUID | None] = mapped_column(
                UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
            )
            call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
            customer_id: Mapped[int | None] = mapped_column(
                Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
            )
            stylist_id: Mapped[int | None] = mapped_column(
                Integer, ForeignKey("stylists.id", ondelete="SET NULL"), nullable=True
            )
            
            # Chunk content
            chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
            content: Mapped[str] = mapped_column(Text, nullable=False)
            content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
            token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
            
            # Vector embedding (1536 dims for text-embedding-3-small)
            embedding = Column(Vector(EMBEDDING_DIMENSION), nullable=False)
            
            created_at: Mapped[datetime] = mapped_column(
                DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
            )

            __table_args__ = (
                # Prevent duplicate chunk ingestion
                Index("uq_chunk_identity", "shop_id", "source_type", "source_id", "chunk_index", unique=True),
                # Filtered indexes
                Index("idx_chunks_shop_created", "shop_id", "created_at"),
                Index("idx_chunks_shop_source_type", "shop_id", "source_type"),
                Index("idx_chunks_content_hash", "shop_id", "content_hash"),
                # Source type validation
                CheckConstraint(
                    "source_type IN ('call_transcript', 'call_summary', 'booking_note')",
                    name="ck_source_type_valid"
                ),
            )
        
        logger.info("pgvector EmbeddedChunk model loaded successfully")
        
    except ImportError as e:
        logger.warning(
            "ENABLE_EMBEDDINGS=True but pgvector not available: %s. "
            "Install pgvector extension in Postgres and 'pip install pgvector'.",
            e
        )
        EmbeddedChunk = None
        EMBEDDINGS_ENABLED = False  # Override flag if pgvector unavailable

else:
    logger.info(
        "Embeddings disabled (ENABLE_EMBEDDINGS=False). "
        "Vector search features will be no-ops. Enable in Phase 8."
    )
