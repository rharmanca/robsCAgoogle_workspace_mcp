"""
Gmail indexing subsystem for local email search.

Components:
- db_manager: SQLite + FTS5 database for metadata and full-text search
- vector_store: ChromaDB for semantic vector search
- embeddings: sentence-transformers for generating embeddings
- sync_manager: Gmail API sync logic
- hybrid_search: RRF algorithm for combining search results
"""

from .db_manager import DatabaseManager
from .vector_store import VectorStore
from .embeddings import EmbeddingGenerator
from .sync_manager import SyncManager
from .hybrid_search import hybrid_search, reciprocal_rank_fusion

__all__ = [
    'DatabaseManager',
    'VectorStore',
    'EmbeddingGenerator',
    'SyncManager',
    'hybrid_search',
    'reciprocal_rank_fusion',
]
