"""
External OAuth Provider for Google Workspace MCP

Extends FastMCP's GoogleProvider to support external OAuth flows where
access tokens (ya29.*) are issued by external systems and need validation.

This provider acts as a Resource Server only - it validates tokens issued by
Google's Authorization Server but does not issue tokens itself.
"""

import logging
import time
from typing import Optional

from starlette.routing import Route
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth import AccessToken
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# Google's OAuth 2.0 Authorization Server
GOOGLE_ISSUER_URL = "https://accounts.google.com"


class ExternalOAuthProvider(GoogleProvider):
    """
    Extended GoogleProvider that supports validating external Google OAuth access tokens.

    This provider handles ya29.* access tokens by calling Google's userinfo API,
    while maintaining compatibility with standard JWT ID tokens.

    Unlike the standard GoogleProvider, this acts as a Resource Server only:
    - Does NOT create /authorize, /token, /register endpoints
    - Only advertises Google's authorization server in metadata
    - Only validates tokens, does not issue them
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        resource_server_url: Optional[str] = None,
        **kwargs,
    ):
        """Initialize and store client credentials for token validation."""
        self._resource_server_url = resource_server_url
        super().__init__(client_id=client_id, client_secret=client_secret, **kwargs)
        # Store credentials as they're not exposed by parent class
        self._client_id = client_id
        self._client_secret = client_secret
        # Store as string - Pydantic validates it when passed to models
        self.resource_server_url = self._resource_server_url

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        Verify a token - supports both JWT ID tokens and ya29.* access tokens.

        For ya29.* access tokens (issued externally), validates by calling
        Google's userinfo API. For JWT tokens, delegates to parent class.

        Args:
            token: Token string to verify (JWT or ya29.* access token)

        Returns:
            AccessToken object if valid, None otherwise
        """
        # For ya29.* access tokens, validate using Google's userinfo API
        if token.startswith("ya29."):
            logger.debug("Validating external Google OAuth access token")

            try:
                from auth.google_auth import get_user_info

                # Create minimal Credentials object for userinfo API call
                credentials = Credentials(
                    token=token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )

                # Validate token by calling userinfo API
                user_info = get_user_info(credentials)

                if user_info and user_info.get("email"):
                    # Token is valid - create AccessToken object
                    logger.info(
                        f"Validated external access token for: {user_info['email']}"
                    )

                    scope_list = list(getattr(self, "required_scopes", []) or [])
                    from auth.oauth_types import WorkspaceAccessToken

                    access_token = WorkspaceAccessToken(
                        token=token,
                        scopes=scope_list,
                        expires_at=int(time.time())
                        + 3600,  # Default to 1-hour validity
                        claims={
                            "email": user_info["email"],
                            "sub": user_info.get("id"),
                        },
                        client_id=self._client_id,
                        email=user_info["email"],
                        sub=user_info.get("id"),
                    )
                    return access_token
                else:
                    logger.error("Could not get user info from access token")
                    return None

            except Exception as e:
                logger.error(f"Error validating external access token: {e}")
                return None

        # For JWT tokens, use parent class implementation
        return await super().verify_token(token)

    def get_routes(self, **kwargs) -> list[Route]:
        """
        Get OAuth routes for external provider mode.

        Returns only protected resource metadata routes that point to Google
        as the authorization server. Does not create authorization server routes
        (/authorize, /token, etc.) since tokens are issued by Google directly.

        Args:
            **kwargs: Additional arguments passed by FastMCP (e.g., mcp_path)

        Returns:
            List of routes - only protected resource metadata
        """
        from mcp.server.auth.routes import create_protected_resource_routes

        if not self.resource_server_url:
            logger.warning(
                "ExternalOAuthProvider: resource_server_url not set, no routes created"
            )
            return []

        # Create protected resource routes that point to Google as the authorization server
        # Pass strings directly - Pydantic validates them during model construction
        protected_routes = create_protected_resource_routes(
            resource_url=self.resource_server_url,
            authorization_servers=[GOOGLE_ISSUER_URL],
            scopes_supported=self.required_scopes,
            resource_name="Google Workspace MCP",
            resource_documentation=None,
        )

        logger.info(
            f"ExternalOAuthProvider: Created protected resource routes pointing to {GOOGLE_ISSUER_URL}"
        )
        return protected_routes
