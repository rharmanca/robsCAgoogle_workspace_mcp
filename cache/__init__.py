# Semantic caching module for google-workspace-mcp
# Uses Qdrant for semantic similarity and Redis for exact-match caching

from .semantic_cache import SemanticCache, CacheConfig, get_cache
from .cache_decorator import cached_response, invalidate_cache_for

__all__ = [
    "SemanticCache",
    "CacheConfig",
    "get_cache",
    "cached_response",
    "invalidate_cache_for",
]
