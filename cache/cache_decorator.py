"""
Decorator for adding semantic caching to google-workspace-mcp tools.

Usage:
    @cached_response(skip_on_write=True)
    @require_google_service("calendar", "calendar_read")
    async def get_events(service, user_google_email: str, ...):
        ...
"""

import logging
from functools import wraps
from typing import Any, Callable, Optional, Set

from .semantic_cache import get_cache

logger = logging.getLogger(__name__)

# Tools that perform write operations (should invalidate cache, not read from it)
WRITE_TOOLS: Set[str] = {
    # Calendar
    "create_event",
    "modify_event",
    "delete_event",
    # Tasks
    "create_task",
    "update_task",
    "delete_task",
    "move_task",
    "clear_completed_tasks",
    # Gmail
    "send_gmail_message",
    "draft_gmail_message",
    "modify_gmail_message_labels",
    "batch_modify_gmail_message_labels",
    # Drive
    "create_drive_file",
    "update_drive_file",
    # Docs
    "create_doc",
    "modify_doc_text",
    "find_and_replace_doc",
    "insert_doc_elements",
    "insert_doc_image",
    "update_doc_headers_footers",
    "batch_update_doc",
    # Sheets
    "modify_sheet_values",
    "create_spreadsheet",
    "create_sheet",
    # Slides
    "create_presentation",
    "batch_update_presentation",
    # Forms
    "create_form",
    "set_publish_settings",
    # Chat
    "send_message",
}

# Tools that should never be cached
NEVER_CACHE: Set[str] = {
    "start_google_auth",
    "get_gmail_attachment",  # Binary data
}


def cached_response(
    skip_on_write: bool = True,
    custom_ttl: Optional[int] = None,
):
    """
    Decorator that adds semantic caching to MCP tool functions.

    Args:
        skip_on_write: If True, write operations invalidate cache instead of reading
        custom_ttl: Override the default TTL for this tool

    Example:
        @cached_response()
        @require_google_service("calendar", "calendar_read")
        async def get_events(service, user_google_email: str, time_min: str = None, ...):
            # This response will be cached
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tool_name = func.__name__
            cache = get_cache()

            # Never cache certain tools
            if tool_name in NEVER_CACHE:
                return await func(*args, **kwargs)

            # Extract user_google_email from kwargs or args
            user_email = kwargs.get("user_google_email")
            if not user_email and len(args) > 1:
                # Assuming user_google_email is second arg after service
                user_email = (
                    args[1] if isinstance(args[1], str) and "@" in args[1] else None
                )

            if not user_email:
                # Can't cache without user context
                return await func(*args, **kwargs)

            # Build params dict for cache key (excluding service and user_email)
            cache_params = {
                k: v
                for k, v in kwargs.items()
                if k != "user_google_email" and v is not None
            }

            # Handle write operations
            if skip_on_write and tool_name in WRITE_TOOLS:
                result = await func(*args, **kwargs)
                # Invalidate related cache entries
                await cache.invalidate(tool_name=tool_name, user_email=user_email)
                return result

            # Try to get from cache
            try:
                cached_result, cache_type = await cache.get(
                    tool_name=tool_name,
                    params=cache_params,
                    user_email=user_email,
                )

                if cached_result is not None:
                    # Add cache metadata to response
                    if isinstance(cached_result, dict):
                        cached_result["_cache"] = {
                            "hit": True,
                            "type": cache_type,
                        }
                    return cached_result
            except Exception as e:
                logger.warning(f"Cache get failed for {tool_name}: {e}")

            # Cache miss - call the actual function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await cache.set(
                    tool_name=tool_name,
                    params=cache_params,
                    user_email=user_email,
                    response=result,
                    ttl=custom_ttl,
                )
            except Exception as e:
                logger.warning(f"Cache set failed for {tool_name}: {e}")

            return result

        return wrapper

    return decorator


def invalidate_cache_for(tool_name: str, user_email: str):
    """
    Manually invalidate cache entries.

    Call this after operations that modify data but aren't decorated.
    """
    import asyncio

    cache = get_cache()
    asyncio.create_task(cache.invalidate(tool_name=tool_name, user_email=user_email))
