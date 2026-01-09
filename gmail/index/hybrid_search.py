"""
Hybrid search combining FTS5 keyword search and semantic vector search.

Uses Reciprocal Rank Fusion (RRF) from SIGIR '09 paper (Cormack et al.).
Formula: RRF(d) = SUM over rankers of: 1 / (k + rank(d))
k=60 is the empirically validated default from original research.
"""

import logging
from collections import defaultdict
from typing import Optional

from .db_manager import DatabaseManager
from .vector_store import VectorStore
from .embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

# RRF parameter from SIGIR '09 paper
RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """
    Combine results from multiple rankers using Reciprocal Rank Fusion.

    RRF only uses rank positions, not scores. This makes it robust to
    different scoring scales between rankers.

    Args:
        ranked_lists: List of ranked document ID lists (best first)
        k: RRF constant (default 60 from SIGIR '09 paper)

    Returns:
        List of (doc_id, rrf_score) tuples sorted by score descending
    """
    rrf_scores: dict[str, float] = defaultdict(float)

    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            rrf_scores[doc_id] += 1.0 / (k + rank)

    # Sort by score descending
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(
    query: str,
    user_email: str,
    db_manager: DatabaseManager,
    vector_store: VectorStore,
    embedding_generator: EmbeddingGenerator,
    limit: int = 20,
    fts_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[dict]:
    """
    Perform hybrid search combining FTS5 and semantic results.

    Args:
        query: Search query
        user_email: User email to filter results
        db_manager: Database manager for FTS5 search
        vector_store: Vector store for semantic search
        embedding_generator: For generating query embedding
        limit: Maximum results to return
        fts_weight: Weight for FTS results (1.0 = normal, 0 = disabled)
        semantic_weight: Weight for semantic results (1.0 = normal, 0 = disabled)

    Returns:
        List of search results with combined scores
    """
    # Fetch more candidates than limit for better fusion
    candidate_limit = min(limit * 3, 100)

    # Run both searches
    fts_results = []
    semantic_results = []

    if fts_weight > 0:
        try:
            fts_results = db_manager.search_fts(
                query=query,
                user_email=user_email,
                limit=candidate_limit,
            )
            logger.debug(f"FTS returned {len(fts_results)} results")
        except Exception as e:
            logger.warning(f"FTS search failed: {e}")

    if semantic_weight > 0:
        try:
            # Generate query embedding
            query_embedding = embedding_generator.generate_embedding(query)

            semantic_results = vector_store.search(
                query=query,
                user_email=user_email,
                n_results=candidate_limit,
                query_embedding=query_embedding,
            )
            logger.debug(f"Semantic search returned {len(semantic_results)} results")
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")

    # If one search type failed or disabled, return the other
    if not fts_results and not semantic_results:
        return []

    if not fts_results:
        return semantic_results[:limit]

    if not semantic_results:
        return _format_fts_results(fts_results[:limit])

    # Build ranked lists using message_id as key
    fts_ranked = [r['message_id'] for r in fts_results]
    semantic_ranked = [r['message_id'] for r in semantic_results]

    # Apply weights by repeating in ranked list (simple weighting)
    ranked_lists = []
    if fts_weight > 0:
        ranked_lists.append(fts_ranked)
    if semantic_weight > 0:
        ranked_lists.append(semantic_ranked)

    # Fuse results
    fused = reciprocal_rank_fusion(ranked_lists)

    # Build result lookup from both sources
    result_lookup: dict[str, dict] = {}

    for r in fts_results:
        msg_id = r['message_id']
        if msg_id not in result_lookup:
            result_lookup[msg_id] = {
                'id': r['id'],
                'message_id': msg_id,
                'thread_id': r.get('thread_id'),
                'subject': r.get('subject'),
                'sender': r.get('sender'),
                'date_sent': r.get('date_sent'),
                'fts_score': r.get('score'),
                'fts_snippet': r.get('snippet'),
            }
        else:
            result_lookup[msg_id]['fts_score'] = r.get('score')
            result_lookup[msg_id]['fts_snippet'] = r.get('snippet')

    for r in semantic_results:
        msg_id = r['message_id']
        if msg_id not in result_lookup:
            result_lookup[msg_id] = {
                'id': r['id'],
                'message_id': msg_id,
                'subject': r.get('subject'),
                'sender': r.get('sender'),
                'date_sent': r.get('date_sent'),
                'semantic_score': r.get('score'),
            }
        else:
            result_lookup[msg_id]['semantic_score'] = r.get('score')

    # Build final results in RRF order
    results = []
    for msg_id, rrf_score in fused[:limit]:
        if msg_id in result_lookup:
            result = result_lookup[msg_id].copy()
            result['rrf_score'] = rrf_score
            results.append(result)

    return results


def _format_fts_results(fts_results: list[dict]) -> list[dict]:
    """Format FTS results to match hybrid output format."""
    return [
        {
            'id': r['id'],
            'message_id': r['message_id'],
            'thread_id': r.get('thread_id'),
            'subject': r.get('subject'),
            'sender': r.get('sender'),
            'date_sent': r.get('date_sent'),
            'fts_score': r.get('score'),
            'fts_snippet': r.get('snippet'),
            'rrf_score': None,
        }
        for r in fts_results
    ]
