"""
Semantic caching layer for Google Workspace MCP responses.

Uses Qdrant for semantic similarity search and Redis for exact-match caching.
Significantly reduces token usage by caching API responses.
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Lazy imports to avoid startup failures if dependencies missing
_redis = None
_qdrant_client = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis

        _redis = redis
    return _redis


def _get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import (
            Distance,
            VectorParams,
            PointStruct,
            Filter,
            FieldCondition,
            MatchValue,
        )

        _qdrant_client = {
            "QdrantClient": QdrantClient,
            "Distance": Distance,
            "VectorParams": VectorParams,
            "PointStruct": PointStruct,
            "Filter": Filter,
            "FieldCondition": FieldCondition,
            "MatchValue": MatchValue,
        }
    return _qdrant_client


@dataclass
class CacheConfig:
    """Configuration for the semantic cache."""

    # Qdrant settings
    qdrant_host: str = field(
        default_factory=lambda: os.getenv("QDRANT_HOST", "qdrant.railway.internal")
    )
    qdrant_port: int = field(
        default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333"))
    )
    qdrant_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("QDRANT_API_KEY")
    )
    collection_name: str = "mcp_response_cache"

    # Redis settings
    redis_host: str = field(
        default_factory=lambda: os.getenv("REDIS_HOST", "redis.railway.internal")
    )
    redis_port: int = field(
        default_factory=lambda: int(os.getenv("REDIS_PORT", "6379"))
    )
    redis_password: Optional[str] = field(
        default_factory=lambda: os.getenv("REDIS_PASSWORD")
    )

    # Cache behavior
    similarity_threshold: float = 0.85  # Minimum similarity for cache hit
    vector_dimension: int = 384  # Dimension for sentence-transformers/all-MiniLM-L6-v2

    # Enable/disable caching
    enabled: bool = field(
        default_factory=lambda: os.getenv("CACHE_ENABLED", "true").lower() == "true"
    )

    # TTL settings (in seconds)
    ttl_calendar_future: int = 300  # 5 minutes for future events
    ttl_calendar_past: int = 3600  # 1 hour for past events
    ttl_drive_listing: int = 600  # 10 minutes for file listings
    ttl_drive_content: int = 3600  # 1 hour for file content
    ttl_tasks: int = 180  # 3 minutes for tasks
    ttl_email_search: int = 120  # 2 minutes for email searches
    ttl_email_content: int = 1800  # 30 minutes for email content
    ttl_default: int = 300  # 5 minutes default

    # Enable/disable caching per service
    cache_calendar: bool = True
    cache_drive: bool = True
    cache_tasks: bool = True
    cache_gmail: bool = True
    cache_docs: bool = True
    cache_sheets: bool = True


class SemanticCache:
    """
    Semantic caching layer that combines exact-match (Redis) and
    semantic similarity (Qdrant) caching.
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._qdrant = None
        self._redis = None
        self._embedder = None
        self._initialized = False
        self._init_failed = False

    async def initialize(self):
        """Initialize connections to Qdrant and Redis."""
        if self._initialized or self._init_failed:
            return

        if not self.config.enabled:
            logger.info("Semantic cache is disabled via CACHE_ENABLED=false")
            self._init_failed = True
            return

        try:
            # Initialize Qdrant
            qdrant = _get_qdrant()
            self._qdrant = qdrant["QdrantClient"](
                host=self.config.qdrant_host,
                port=self.config.qdrant_port,
                api_key=self.config.qdrant_api_key,
            )

            # Create collection if it doesn't exist
            collections = self._qdrant.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.config.collection_name not in collection_names:
                self._qdrant.create_collection(
                    collection_name=self.config.collection_name,
                    vectors_config=qdrant["VectorParams"](
                        size=self.config.vector_dimension,
                        distance=qdrant["Distance"].COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {self.config.collection_name}")

            # Initialize Redis
            redis_mod = _get_redis()
            self._redis = redis_mod.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                decode_responses=True,
            )
            self._redis.ping()

            # Initialize embedder (lazy load to save memory)
            self._load_embedder()

            self._initialized = True
            logger.info("SemanticCache initialized successfully")

        except Exception as e:
            logger.warning(
                f"Failed to initialize SemanticCache (caching disabled): {e}"
            )
            self._init_failed = True

    def _load_embedder(self):
        """Load the sentence transformer model for embeddings."""
        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded embedding model: all-MiniLM-L6-v2")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed, semantic caching disabled"
            )
            self._embedder = None

    def _generate_cache_key(
        self, tool_name: str, params: Dict[str, Any], user_email: str
    ) -> str:
        """Generate a deterministic cache key for exact-match lookups."""
        # Sort params for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True, default=str)
        key_string = f"{tool_name}:{user_email}:{sorted_params}"
        return f"mcp_cache:{hashlib.sha256(key_string.encode()).hexdigest()[:16]}"

    def _generate_query_text(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Generate a natural language query for semantic similarity."""
        # Convert tool call to natural language for embedding
        param_str = ", ".join(f"{k}={v}" for k, v in params.items() if v is not None)
        return f"{tool_name} with {param_str}" if param_str else tool_name

    def _get_ttl(self, tool_name: str, params: Dict[str, Any]) -> int:
        """Determine TTL based on the tool and parameters."""
        tool_lower = tool_name.lower()

        if "calendar" in tool_lower or "event" in tool_lower:
            # Check if querying future or past events
            time_min = params.get("time_min", "")
            if time_min:
                try:
                    if (
                        datetime.fromisoformat(time_min.replace("Z", "+00:00"))
                        > datetime.now()
                    ):
                        return self.config.ttl_calendar_future
                except:
                    pass
            return self.config.ttl_calendar_past

        elif "drive" in tool_lower:
            if "content" in tool_lower:
                return self.config.ttl_drive_content
            return self.config.ttl_drive_listing

        elif "task" in tool_lower:
            return self.config.ttl_tasks

        elif "gmail" in tool_lower or "email" in tool_lower:
            if "search" in tool_lower:
                return self.config.ttl_email_search
            return self.config.ttl_email_content

        return self.config.ttl_default

    async def get(
        self, tool_name: str, params: Dict[str, Any], user_email: str
    ) -> Tuple[Optional[Any], str]:
        """
        Try to get a cached response.

        Returns:
            Tuple of (cached_response, cache_type) where cache_type is:
            - "exact": Redis exact match
            - "semantic": Qdrant semantic match
            - "miss": No cache hit
        """
        if not self._initialized:
            await self.initialize()

        if self._init_failed:
            return None, "miss"

        # 1. Try exact match in Redis first (fastest)
        cache_key = self._generate_cache_key(tool_name, params, user_email)

        try:
            cached = self._redis.get(cache_key)
            if cached:
                logger.info(f"[CACHE HIT] Exact match for {tool_name}")
                return json.loads(cached), "exact"
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")

        # 2. Try semantic similarity in Qdrant
        if self._embedder and self._qdrant:
            try:
                qdrant = _get_qdrant()
                query_text = self._generate_query_text(tool_name, params)
                query_vector = self._embedder.encode(query_text).tolist()

                results = self._qdrant.search(
                    collection_name=self.config.collection_name,
                    query_vector=query_vector,
                    query_filter=qdrant["Filter"](
                        must=[
                            qdrant["FieldCondition"](
                                key="user_email",
                                match=qdrant["MatchValue"](value=user_email),
                            ),
                            qdrant["FieldCondition"](
                                key="tool_name",
                                match=qdrant["MatchValue"](value=tool_name),
                            ),
                        ]
                    ),
                    limit=1,
                    score_threshold=self.config.similarity_threshold,
                )

                if results:
                    best_match = results[0]
                    # Check if not expired
                    expires_at = best_match.payload.get("expires_at", 0)
                    if expires_at > datetime.utcnow().timestamp():
                        logger.info(
                            f"[CACHE HIT] Semantic match for {tool_name} "
                            f"(similarity: {best_match.score:.3f})"
                        )
                        return json.loads(best_match.payload["response"]), "semantic"
                    else:
                        # Expired, delete it
                        self._qdrant.delete(
                            collection_name=self.config.collection_name,
                            points_selector=[best_match.id],
                        )
            except Exception as e:
                logger.warning(f"Qdrant search failed: {e}")

        logger.debug(f"[CACHE MISS] {tool_name}")
        return None, "miss"

    async def set(
        self,
        tool_name: str,
        params: Dict[str, Any],
        user_email: str,
        response: Any,
        ttl: Optional[int] = None,
    ):
        """Store a response in both Redis (exact) and Qdrant (semantic) caches."""
        if not self._initialized:
            await self.initialize()

        if self._init_failed:
            return

        ttl = ttl or self._get_ttl(tool_name, params)
        response_json = json.dumps(response, default=str)

        # 1. Store in Redis for exact matches
        cache_key = self._generate_cache_key(tool_name, params, user_email)
        try:
            self._redis.setex(cache_key, ttl, response_json)
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")

        # 2. Store in Qdrant for semantic matches
        if self._embedder and self._qdrant:
            try:
                qdrant = _get_qdrant()
                query_text = self._generate_query_text(tool_name, params)
                vector = self._embedder.encode(query_text).tolist()

                point_id = hashlib.md5(
                    f"{tool_name}:{user_email}:{json.dumps(params, sort_keys=True)}".encode()
                ).hexdigest()

                self._qdrant.upsert(
                    collection_name=self.config.collection_name,
                    points=[
                        qdrant["PointStruct"](
                            id=point_id,
                            vector=vector,
                            payload={
                                "tool_name": tool_name,
                                "user_email": user_email,
                                "params": json.dumps(params, default=str),
                                "response": response_json,
                                "created_at": datetime.utcnow().timestamp(),
                                "expires_at": (
                                    datetime.utcnow() + timedelta(seconds=ttl)
                                ).timestamp(),
                            },
                        )
                    ],
                )
            except Exception as e:
                logger.warning(f"Qdrant upsert failed: {e}")

        logger.debug(f"[CACHE SET] {tool_name} (TTL: {ttl}s)")

    async def invalidate(
        self,
        tool_name: Optional[str] = None,
        user_email: Optional[str] = None,
    ):
        """Invalidate cache entries. Call after write operations."""
        if not self._initialized or self._init_failed:
            return

        # For now, invalidate by tool pattern in Redis
        # This is called after create/update/delete operations
        if tool_name and user_email:
            # Invalidate related read operations
            invalidation_map = {
                "create_event": ["get_events", "list_calendars"],
                "modify_event": ["get_events"],
                "delete_event": ["get_events"],
                "create_task": ["list_tasks", "get_task"],
                "update_task": ["list_tasks", "get_task"],
                "delete_task": ["list_tasks"],
                "send_gmail_message": ["search_gmail_messages"],
                "create_drive_file": ["search_drive_files", "list_drive_items"],
                "update_drive_file": ["search_drive_files", "get_drive_file_content"],
            }

            related_tools = invalidation_map.get(tool_name, [])
            for related_tool in related_tools:
                # Delete from Qdrant
                try:
                    qdrant = _get_qdrant()
                    self._qdrant.delete(
                        collection_name=self.config.collection_name,
                        points_selector=qdrant["Filter"](
                            must=[
                                qdrant["FieldCondition"](
                                    key="user_email",
                                    match=qdrant["MatchValue"](value=user_email),
                                ),
                                qdrant["FieldCondition"](
                                    key="tool_name",
                                    match=qdrant["MatchValue"](value=related_tool),
                                ),
                            ]
                        ),
                    )
                except Exception as e:
                    logger.warning(f"Qdrant invalidation failed: {e}")

            logger.info(f"[CACHE INVALIDATE] {tool_name} -> {related_tools}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "initialized": self._initialized,
            "init_failed": self._init_failed,
            "qdrant_connected": self._qdrant is not None,
            "redis_connected": self._redis is not None,
            "embedder_loaded": self._embedder is not None,
        }

        if self._redis:
            try:
                info = self._redis.info("stats")
                stats["redis_hits"] = info.get("keyspace_hits", 0)
                stats["redis_misses"] = info.get("keyspace_misses", 0)
            except:
                pass

        if self._qdrant:
            try:
                collection_info = self._qdrant.get_collection(
                    self.config.collection_name
                )
                stats["qdrant_points"] = collection_info.points_count
            except:
                pass

        return stats


# Global cache instance
_cache_instance: Optional[SemanticCache] = None


def get_cache() -> SemanticCache:
    """Get or create the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance
