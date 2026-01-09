"""
ChromaDB vector store for semantic email search.

CRITICAL: Uses cosine distance (not default L2) for text embeddings.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default storage location - supports EMAIL_INDEX_DATA_DIR env var for Railway volumes
def get_default_chroma_path() -> Path:
    """Get default ChromaDB path, using env var if set for Railway deployment."""
    import os
    data_dir = os.environ.get("EMAIL_INDEX_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "chroma"
    return Path.home() / ".workspace-mcp" / "chroma"


DEFAULT_CHROMA_PATH = get_default_chroma_path()

# Collection configuration
COLLECTION_NAME = "emails"
BATCH_SIZE = 200  # Optimal batch size per ChromaDB docs


class VectorStore:
    """ChromaDB vector store for email embeddings."""

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        embedding_generator=None,
    ):
        """
        Initialize ChromaDB vector store.

        Args:
            persist_directory: Path to ChromaDB persistence directory.
            embedding_generator: EmbeddingGenerator instance for generating embeddings.
        """
        self.persist_directory = persist_directory or DEFAULT_CHROMA_PATH
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.embedding_generator = embedding_generator

        self._client = None
        self._collection = None

    @property
    def client(self):
        """Lazy load ChromaDB client."""
        if self._client is None:
            import chromadb
            # Use absolute path for PersistentClient
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory.absolute())
            )
            logger.info(f"ChromaDB initialized at {self.persist_directory}")
        return self._client

    @property
    def collection(self):
        """Get or create the emails collection with cosine distance."""
        if self._collection is None:
            # CRITICAL: Must use cosine distance for text embeddings!
            # Default L2 produces poor results for text similarity
            self._collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},  # CRITICAL - not default L2!
            )
            logger.info(f"Collection '{COLLECTION_NAME}' ready with {self._collection.count()} documents")
        return self._collection

    def add_emails(
        self,
        emails: list[dict],
        embeddings: Optional[list[list[float]]] = None,
    ) -> int:
        """
        Add emails to vector store.

        Args:
            emails: List of email dicts with 'id', 'message_id', 'subject', 'sender', 'body_text', 'user_email'
            embeddings: Pre-computed embeddings. If None, generates using embedding_generator.

        Returns:
            Number of emails added.
        """
        if not emails:
            return 0

        # Generate embeddings if not provided
        if embeddings is None:
            if self.embedding_generator is None:
                raise ValueError("Must provide embeddings or embedding_generator")
            embeddings = self.embedding_generator.generate_email_batch_embeddings(emails)

        # Prepare data for ChromaDB
        ids = [str(email['id']) for email in emails]
        metadatas = [
            {
                'message_id': email['message_id'],
                'user_email': email['user_email'],
                'subject': email.get('subject', '')[:500],  # Truncate for metadata
                'sender': email.get('sender', '')[:200],
                'date_sent': email.get('date_sent', ''),
            }
            for email in emails
        ]
        # Documents for ChromaDB (used if we need to re-embed)
        documents = [
            self.embedding_generator.format_email_text(
                subject=email.get('subject'),
                sender=email.get('sender'),
                body=email.get('body_text'),
            ) if self.embedding_generator else ''
            for email in emails
        ]

        # Add in batches
        added = 0
        for i in range(0, len(ids), BATCH_SIZE):
            batch_ids = ids[i:i + BATCH_SIZE]
            batch_embeddings = embeddings[i:i + BATCH_SIZE]
            batch_metadatas = metadatas[i:i + BATCH_SIZE]
            batch_documents = documents[i:i + BATCH_SIZE]

            self.collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents,
            )
            added += len(batch_ids)

        logger.info(f"Added {added} emails to vector store")
        return added

    def search(
        self,
        query: str,
        user_email: str,
        n_results: int = 20,
        query_embedding: Optional[list[float]] = None,
    ) -> list[dict]:
        """
        Search for similar emails.

        Args:
            query: Search query text
            user_email: Filter results to specific user
            n_results: Number of results to return
            query_embedding: Pre-computed query embedding. If None, generates using embedding_generator.

        Returns:
            List of results with 'id', 'message_id', 'score', 'subject', 'sender', 'date_sent'
        """
        # Generate query embedding if not provided
        if query_embedding is None:
            if self.embedding_generator is None:
                raise ValueError("Must provide query_embedding or embedding_generator")
            query_embedding = self.embedding_generator.generate_embedding(query)

        # Query with user_email filter
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={"user_email": user_email},
            include=["metadatas", "distances"],
        )

        # Format results
        formatted = []
        if results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 0

                # Convert distance to similarity score (cosine: 0=identical, 2=opposite)
                # Similarity = 1 - distance for normalized cosine
                similarity = 1 - distance

                formatted.append({
                    'id': int(doc_id),
                    'message_id': metadata.get('message_id', ''),
                    'subject': metadata.get('subject', ''),
                    'sender': metadata.get('sender', ''),
                    'date_sent': metadata.get('date_sent', ''),
                    'score': similarity,  # Higher is better
                })

        return formatted

    def delete_by_ids(self, ids: list[int]) -> int:
        """
        Delete emails by their database IDs.

        Args:
            ids: List of database row IDs to delete

        Returns:
            Number of emails deleted
        """
        if not ids:
            return 0

        str_ids = [str(i) for i in ids]
        self.collection.delete(ids=str_ids)
        logger.info(f"Deleted {len(ids)} emails from vector store")
        return len(ids)

    def delete_by_message_ids(self, message_ids: list[str], user_email: str) -> int:
        """
        Delete emails by Gmail message IDs.

        Args:
            message_ids: List of Gmail message IDs
            user_email: User email to scope the deletion

        Returns:
            Number of emails deleted
        """
        if not message_ids:
            return 0

        # Find matching documents
        deleted = 0
        for message_id in message_ids:
            results = self.collection.get(
                where={"$and": [
                    {"message_id": message_id},
                    {"user_email": user_email}
                ]},
                include=[],
            )
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                deleted += len(results['ids'])

        logger.info(f"Deleted {deleted} emails by message_id from vector store")
        return deleted

    def count(self, user_email: Optional[str] = None) -> int:
        """
        Count emails in vector store.

        Args:
            user_email: Optional filter by user

        Returns:
            Number of emails
        """
        if user_email:
            # ChromaDB doesn't have a direct count with filter
            # Use get with minimal data
            results = self.collection.get(
                where={"user_email": user_email},
                include=[],
            )
            return len(results['ids']) if results['ids'] else 0
        return self.collection.count()

    def clear(self):
        """Delete all emails from the collection."""
        # Delete and recreate collection
        self.client.delete_collection(COLLECTION_NAME)
        self._collection = None
        # Force recreation
        _ = self.collection
        logger.info("Vector store cleared")
