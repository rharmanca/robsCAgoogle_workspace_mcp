"""
Embedding generator supporting both local and API-based embeddings.

Supports:
- Local: sentence-transformers (all-MiniLM-L6-v2)
- API: OpenAI-compatible endpoints (synthetic.new, OpenAI, etc.)

Uses lazy loading to avoid startup delay.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Local model configuration
DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
LOCAL_EMBEDDING_DIMENSION = 384

# API configuration
# synthetic.new requires hf:organization/model-name format
DEFAULT_API_MODEL = "hf:nomic-ai/nomic-embed-text-v1.5"
API_EMBEDDING_DIMENSION = 768  # nomic-embed-text-v1.5 dimension

# synthetic.new API base URL
SYNTHETIC_API_BASE = "https://api.synthetic.new/openai/v1"


class EmbeddingGenerator:
    """Generate embeddings for email content using local models or API."""

    def __init__(
        self,
        use_api: bool = False,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        api_model: str = DEFAULT_API_MODEL,
        local_model: str = DEFAULT_LOCAL_MODEL,
    ):
        """
        Initialize embedding generator.

        Args:
            use_api: If True, use API-based embeddings. If False, use local model.
            api_key: API key for embedding service. Defaults to SYNTHETIC_API_KEY env var.
            api_base_url: Base URL for API. Defaults to synthetic.new.
            api_model: Model name for API embeddings.
            local_model: Name of sentence-transformers model for local embeddings.
        """
        self.use_api = use_api
        self.api_key = api_key or os.environ.get("SYNTHETIC_API_KEY")
        self.api_base_url = api_base_url or SYNTHETIC_API_BASE
        self.api_model = api_model
        self.local_model_name = local_model
        self._local_model = None  # Lazy loaded

    @property
    def local_model(self):
        """Lazy load the local model on first use."""
        if self._local_model is None:
            logger.info(f"Loading local embedding model: {self.local_model_name}")
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer(self.local_model_name)
            logger.info("Local embedding model loaded successfully")
        return self._local_model

    @property
    def dimension(self) -> int:
        """Return embedding dimension for the configured model."""
        if self.use_api:
            return API_EMBEDDING_DIMENSION
        return LOCAL_EMBEDDING_DIMENSION

    def format_email_text(
        self,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        body: Optional[str] = None,
        max_body_length: int = 2000,
    ) -> str:
        """
        Format email content for embedding.

        Args:
            subject: Email subject
            sender: Sender address
            body: Email body text
            max_body_length: Truncate body to this length

        Returns:
            Formatted text for embedding
        """
        parts = []

        if subject:
            parts.append(f"Subject: {subject}")

        if sender:
            parts.append(f"From: {sender}")

        if body:
            truncated_body = body[:max_body_length] if len(body) > max_body_length else body
            parts.append(f"\n{truncated_body}")

        return "\n".join(parts)

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding as list of floats
        """
        if self.use_api:
            return self._generate_api_embedding(text)
        return self._generate_local_embedding(text)

    def _generate_local_embedding(self, text: str) -> list[float]:
        """Generate embedding using local sentence-transformers model."""
        embedding = self.local_model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def _generate_api_embedding(self, text: str) -> list[float]:
        """Generate embedding using API."""
        embeddings = self._call_embeddings_api([text])
        return embeddings[0] if embeddings else []

    def _call_embeddings_api(self, texts: list[str]) -> list[list[float]]:
        """
        Call OpenAI-compatible embeddings API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not self.api_key:
            raise ValueError(
                "API key required for API embeddings. "
                "Set SYNTHETIC_API_KEY environment variable or pass api_key parameter."
            )

        url = f"{self.api_base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.api_model,
            "input": texts,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                # Extract embeddings from OpenAI-format response
                embeddings = []
                for item in sorted(data.get("data", []), key=lambda x: x.get("index", 0)):
                    embeddings.append(item.get("embedding", []))

                return embeddings

        except httpx.HTTPStatusError as e:
            logger.error(f"Embeddings API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to call embeddings API: {e}")
            raise

    def generate_email_embedding(
        self,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        body: Optional[str] = None,
    ) -> list[float]:
        """
        Generate embedding for an email.

        Args:
            subject: Email subject
            sender: Sender address
            body: Email body text

        Returns:
            Embedding as list of floats
        """
        text = self.format_email_text(subject, sender, body)
        return self.generate_embedding(text)

    def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not texts:
            return []

        if self.use_api:
            # API supports batching natively
            return self._call_embeddings_api(texts)

        # Local model batching
        embeddings = self.local_model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]

    def generate_email_batch_embeddings(
        self,
        emails: list[dict],
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple emails.

        Args:
            emails: List of email dicts with 'subject', 'sender', 'body_text' keys

        Returns:
            List of embeddings
        """
        texts = [
            self.format_email_text(
                subject=email.get('subject'),
                sender=email.get('sender'),
                body=email.get('body_text'),
            )
            for email in emails
        ]
        return self.generate_batch_embeddings(texts)
