"""
Gmail Indexing MCP Tools

Tools for local email indexing with FTS5 keyword search and semantic vector search.
Combines both using Reciprocal Rank Fusion (RRF) for hybrid search.
"""

import logging
import os
from typing import Optional

import anyio

from auth.service_decorator import require_google_service
from core.utils import handle_http_errors
from core.server import server

from .index.db_manager import DatabaseManager
from .index.vector_store import VectorStore
from .index.embeddings import EmbeddingGenerator
from .index.sync_manager import SyncManager
from .index.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)

# Lazy-initialized global instances
_db_manager: Optional[DatabaseManager] = None
_vector_store: Optional[VectorStore] = None
_embedding_generator: Optional[EmbeddingGenerator] = None
_sync_manager: Optional[SyncManager] = None


def _get_db_manager() -> DatabaseManager:
    """Get or create database manager singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def _get_embedding_generator() -> EmbeddingGenerator:
    """Get or create embedding generator singleton."""
    global _embedding_generator
    if _embedding_generator is None:
        # Check if API key is available for synthetic.new
        use_api = bool(os.environ.get("SYNTHETIC_API_KEY"))
        _embedding_generator = EmbeddingGenerator(use_api=use_api)
        if use_api:
            logger.info("Using synthetic.new API for embeddings")
        else:
            logger.info("Using local sentence-transformers for embeddings")
    return _embedding_generator


def _get_vector_store() -> VectorStore:
    """Get or create vector store singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(embedding_generator=_get_embedding_generator())
    return _vector_store


def _get_sync_manager() -> SyncManager:
    """Get or create sync manager singleton."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = SyncManager(
            db_manager=_get_db_manager(),
            vector_store=_get_vector_store(),
            embedding_generator=_get_embedding_generator(),
        )
    return _sync_manager


@server.tool()
@handle_http_errors("index_gmail_inbox", is_read_only=True, service_type="gmail")
@require_google_service("gmail", "gmail_read")
async def index_gmail_inbox(
    service,
    user_google_email: str,
    max_messages: int = 5000,
    query: str = "",
) -> str:
    """
    Index emails from Gmail inbox for local full-text and semantic search.

    Creates a local SQLite database with FTS5 for keyword search and
    ChromaDB vector store for semantic search. First run may take several
    minutes depending on inbox size.

    Args:
        user_google_email (str): The user's Google email address. Required.
        max_messages (int): Maximum number of emails to index. Defaults to 5000.
        query (str): Optional Gmail search query to filter which emails to index.
                     Example: "after:2024/01/01" to only index recent emails.

    Returns:
        str: Indexing statistics including count and duration.
    """
    logger.info(f"[index_gmail_inbox] Starting index for {user_google_email}, max={max_messages}")

    sync_manager = _get_sync_manager()

    # Run sync in thread pool (blocking operation)
    result = await anyio.to_thread.run_sync(
        lambda: sync_manager.full_sync(
            service=service,
            user_email=user_google_email,
            max_messages=max_messages,
            query=query,
        )
    )

    return (
        f"Indexing complete for {user_google_email}:\n"
        f"- Indexed: {result['indexed']} emails\n"
        f"- Total found: {result['total']}\n"
        f"- Duration: {result['duration_seconds']} seconds\n"
        f"- History ID: {result.get('history_id', 'N/A')}"
    )


@server.tool()
@handle_http_errors("sync_gmail_index", is_read_only=True, service_type="gmail")
@require_google_service("gmail", "gmail_read")
async def sync_gmail_index(
    service,
    user_google_email: str,
) -> str:
    """
    Incrementally sync new emails to the local index.

    Uses Gmail History API to efficiently fetch only new/changed emails
    since the last sync. Much faster than full indexing.

    Args:
        user_google_email (str): The user's Google email address. Required.

    Returns:
        str: Sync statistics including added/deleted counts.
    """
    logger.info(f"[sync_gmail_index] Starting incremental sync for {user_google_email}")

    sync_manager = _get_sync_manager()

    result = await anyio.to_thread.run_sync(
        lambda: sync_manager.incremental_sync(
            service=service,
            user_email=user_google_email,
        )
    )

    if 'indexed' in result:
        # Full sync was triggered
        return (
            f"Full sync performed (no prior sync state):\n"
            f"- Indexed: {result['indexed']} emails\n"
            f"- Duration: {result['duration_seconds']} seconds"
        )

    return (
        f"Incremental sync complete for {user_google_email}:\n"
        f"- Added: {result.get('added', 0)} emails\n"
        f"- Deleted: {result.get('deleted', 0)} emails\n"
        f"- Duration: {result['duration_seconds']} seconds"
    )


@server.tool()
async def search_gmail_fts(
    user_google_email: str,
    query: str,
    limit: int = 20,
) -> str:
    """
    Fast keyword search using FTS5 full-text search on locally indexed emails.

    Uses BM25 ranking with column weights (sender > subject > body).
    Does not require Gmail API authentication - searches local index only.
    Must run index_gmail_inbox first to populate the index.

    Args:
        user_google_email (str): The user's Google email address. Required.
        query (str): Search query. Supports basic keyword matching.
        limit (int): Maximum number of results. Defaults to 20.

    Returns:
        str: Matching emails with subject, sender, date, and relevant snippets.
    """
    logger.info(f"[search_gmail_fts] Query: '{query}' for {user_google_email}")

    db = _get_db_manager()

    results = await anyio.to_thread.run_sync(
        lambda: db.search_fts(
            query=query,
            user_email=user_google_email,
            limit=limit,
        )
    )

    if not results:
        return f"No results found for '{query}'. Make sure emails are indexed first with index_gmail_inbox."

    output = [f"Found {len(results)} results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        output.append(
            f"{i}. **{r.get('subject', '(no subject)')}**\n"
            f"   From: {r.get('sender', 'Unknown')}\n"
            f"   Date: {r.get('date_sent', 'Unknown')}\n"
            f"   Snippet: {r.get('snippet', '')}\n"
            f"   Message ID: {r['message_id']}\n"
        )

    return "\n".join(output)


@server.tool()
async def search_gmail_semantic(
    user_google_email: str,
    query: str,
    limit: int = 20,
) -> str:
    """
    Semantic similarity search on locally indexed emails using vector embeddings.

    Finds emails that are conceptually similar to your query, even if they
    don't contain the exact keywords. Great for natural language queries like
    "emails about budget planning" or "discussions with vendors about pricing".

    Does not require Gmail API authentication - searches local index only.
    Must run index_gmail_inbox first to populate the index.

    Args:
        user_google_email (str): The user's Google email address. Required.
        query (str): Natural language search query.
        limit (int): Maximum number of results. Defaults to 20.

    Returns:
        str: Semantically similar emails with similarity scores.
    """
    logger.info(f"[search_gmail_semantic] Query: '{query}' for {user_google_email}")

    vector_store = _get_vector_store()

    results = await anyio.to_thread.run_sync(
        lambda: vector_store.search(
            query=query,
            user_email=user_google_email,
            n_results=limit,
        )
    )

    if not results:
        return f"No results found for '{query}'. Make sure emails are indexed first with index_gmail_inbox."

    output = [f"Found {len(results)} semantically similar results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        score_pct = r.get('score', 0) * 100
        output.append(
            f"{i}. **{r.get('subject', '(no subject)')}** (similarity: {score_pct:.1f}%)\n"
            f"   From: {r.get('sender', 'Unknown')}\n"
            f"   Date: {r.get('date_sent', 'Unknown')}\n"
            f"   Message ID: {r['message_id']}\n"
        )

    return "\n".join(output)


@server.tool()
async def search_gmail_hybrid(
    user_google_email: str,
    query: str,
    limit: int = 20,
) -> str:
    """
    Hybrid search combining keyword (FTS5) and semantic (vector) search.

    Uses Reciprocal Rank Fusion (RRF) to combine results from both search
    methods, providing the best of both worlds: exact keyword matches and
    conceptually similar content.

    This is the recommended search method for most use cases.
    Does not require Gmail API authentication - searches local index only.
    Must run index_gmail_inbox first to populate the index.

    Args:
        user_google_email (str): The user's Google email address. Required.
        query (str): Search query (works with both keywords and natural language).
        limit (int): Maximum number of results. Defaults to 20.

    Returns:
        str: Combined search results with RRF scores.
    """
    logger.info(f"[search_gmail_hybrid] Query: '{query}' for {user_google_email}")

    db = _get_db_manager()
    vector_store = _get_vector_store()
    embeddings = _get_embedding_generator()

    results = await anyio.to_thread.run_sync(
        lambda: hybrid_search(
            query=query,
            user_email=user_google_email,
            db_manager=db,
            vector_store=vector_store,
            embedding_generator=embeddings,
            limit=limit,
        )
    )

    if not results:
        return f"No results found for '{query}'. Make sure emails are indexed first with index_gmail_inbox."

    output = [f"Found {len(results)} results for '{query}' (hybrid search):\n"]
    for i, r in enumerate(results, 1):
        rrf_score = r.get('rrf_score')
        score_str = f" (RRF: {rrf_score:.4f})" if rrf_score else ""

        # Show which search methods matched
        sources = []
        if r.get('fts_score') is not None:
            sources.append("keyword")
        if r.get('semantic_score') is not None:
            sources.append("semantic")
        source_str = f" [{'+'.join(sources)}]" if sources else ""

        output.append(
            f"{i}. **{r.get('subject', '(no subject)')}**{score_str}{source_str}\n"
            f"   From: {r.get('sender', 'Unknown')}\n"
            f"   Date: {r.get('date_sent', 'Unknown')}\n"
            f"   Message ID: {r['message_id']}\n"
        )

        # Include snippet if available from FTS
        if r.get('fts_snippet'):
            output.append(f"   Snippet: {r['fts_snippet']}\n")

    return "\n".join(output)


@server.tool()
async def get_gmail_index_stats(
    user_google_email: str,
) -> str:
    """
    Get statistics about the local email index.

    Shows number of indexed emails, last sync time, database size, and
    whether incremental sync is available.

    Args:
        user_google_email (str): The user's Google email address. Required.

    Returns:
        str: Index statistics and status information.
    """
    logger.info(f"[get_gmail_index_stats] Getting stats for {user_google_email}")

    db = _get_db_manager()
    vector_store = _get_vector_store()

    # Get database stats
    db_stats = await anyio.to_thread.run_sync(
        lambda: db.get_stats(user_google_email)
    )

    # Get vector store count
    vector_count = await anyio.to_thread.run_sync(
        lambda: vector_store.count(user_google_email)
    )

    # Get overall stats
    overall_stats = await anyio.to_thread.run_sync(
        lambda: db.get_stats()
    )

    output = [
        f"Email Index Statistics for {user_google_email}:\n",
        f"- Indexed emails (SQLite): {db_stats['total_emails']}",
        f"- Indexed emails (Vector): {vector_count}",
        f"- Last sync: {db_stats.get('last_sync', 'Never')}",
        f"- History ID: {db_stats.get('history_id', 'N/A')}",
        f"\nOverall Index:",
        f"- Total emails: {overall_stats['total_emails']}",
        f"- Total users: {overall_stats['total_users']}",
        f"- Database path: {overall_stats['db_path']}",
        f"- Database size: {overall_stats['db_size_mb']:.2f} MB",
    ]

    # Check embedding mode
    embeddings = _get_embedding_generator()
    mode = "API (synthetic.new)" if embeddings.use_api else "Local (sentence-transformers)"
    output.append(f"\nEmbedding mode: {mode}")

    return "\n".join(output)
