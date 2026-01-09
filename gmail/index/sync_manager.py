"""
Gmail sync manager for indexing emails.

Handles batch fetching via Gmail API and coordinates SQLite + ChromaDB updates.
Uses Gmail History API for incremental sync.
"""

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .db_manager import DatabaseManager
from .vector_store import VectorStore
from .embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

# Gmail API limits
BATCH_SIZE = 50  # Google recommends 50 per batch
BATCH_DELAY_MS = 150  # Delay between batches to avoid rate limits
MAX_MESSAGES_PER_SYNC = 10000  # Safety limit


class SyncManager:
    """Manages Gmail to local index synchronization."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        vector_store: VectorStore,
        embedding_generator: EmbeddingGenerator,
    ):
        """
        Initialize sync manager.

        Args:
            db_manager: Database manager for SQLite/FTS5
            vector_store: Vector store for ChromaDB
            embedding_generator: For generating embeddings
        """
        self.db = db_manager
        self.vector_store = vector_store
        self.embeddings = embedding_generator

    def full_sync(
        self,
        service,
        user_email: str,
        max_messages: int = 5000,
        query: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Perform full sync of emails to local index.

        Args:
            service: Gmail API service object
            user_email: User's email address
            max_messages: Maximum emails to index
            query: Optional Gmail search query to filter emails
            progress_callback: Optional callback(indexed, total) for progress

        Returns:
            Dict with sync statistics
        """
        start_time = time.time()
        max_messages = min(max_messages, MAX_MESSAGES_PER_SYNC)

        logger.info(f"Starting full sync for {user_email}, max {max_messages} messages")

        # Get message IDs
        message_ids = self._list_message_ids(service, max_messages, query)
        total_messages = len(message_ids)
        logger.info(f"Found {total_messages} messages to index")

        if not message_ids:
            return {
                'status': 'success',
                'indexed': 0,
                'total': 0,
                'duration_seconds': time.time() - start_time,
            }

        # Fetch and index in batches
        indexed = 0
        latest_history_id = None

        for i in range(0, len(message_ids), BATCH_SIZE):
            batch_ids = message_ids[i:i + BATCH_SIZE]

            # Fetch message details
            messages = self._batch_get_messages(service, batch_ids)

            if messages:
                # Process and index
                emails_data = []
                for msg in messages.values():
                    email_data = self._parse_message(msg, user_email)
                    if email_data:
                        emails_data.append(email_data)
                        # Track latest historyId
                        if msg.get('historyId'):
                            if latest_history_id is None or int(msg['historyId']) > int(latest_history_id):
                                latest_history_id = msg['historyId']

                if emails_data:
                    # Index to SQLite
                    self.db.upsert_emails_batch(emails_data)

                    # Generate embeddings and add to vector store
                    embeddings = self.embeddings.generate_email_batch_embeddings(emails_data)

                    # Add IDs from database for vector store
                    for email_data in emails_data:
                        db_email = self.db.get_email_by_message_id(email_data['message_id'])
                        if db_email:
                            email_data['id'] = db_email['id']

                    self.vector_store.add_emails(emails_data, embeddings)

                    indexed += len(emails_data)

            # Progress callback
            if progress_callback:
                progress_callback(indexed, total_messages)

            # Delay between batches to avoid rate limits
            if i + BATCH_SIZE < len(message_ids):
                time.sleep(BATCH_DELAY_MS / 1000)

        # Update sync state
        if latest_history_id:
            self.db.update_sync_state(user_email, latest_history_id, indexed)

        duration = time.time() - start_time
        logger.info(f"Full sync complete: {indexed} emails in {duration:.1f}s")

        return {
            'status': 'success',
            'indexed': indexed,
            'total': total_messages,
            'duration_seconds': round(duration, 1),
            'history_id': latest_history_id,
        }

    def incremental_sync(
        self,
        service,
        user_email: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Perform incremental sync using Gmail History API.

        Args:
            service: Gmail API service object
            user_email: User's email address
            progress_callback: Optional callback for progress

        Returns:
            Dict with sync statistics
        """
        start_time = time.time()

        # Get last sync state
        sync_state = self.db.get_sync_state(user_email)
        if not sync_state or not sync_state.get('history_id'):
            logger.info("No previous sync state, performing full sync")
            return self.full_sync(service, user_email, progress_callback=progress_callback)

        history_id = sync_state['history_id']
        logger.info(f"Incremental sync from historyId {history_id}")

        try:
            # Get history since last sync
            history_response = service.users().history().list(
                userId='me',
                startHistoryId=history_id,
                historyTypes=['messageAdded', 'messageDeleted'],
            ).execute()
        except Exception as e:
            # historyId may have expired (404) - need full sync
            if '404' in str(e) or 'notFound' in str(e).lower():
                logger.warning(f"historyId expired, performing full sync")
                return self.full_sync(service, user_email, progress_callback=progress_callback)
            raise

        # Process history
        added_ids = set()
        deleted_ids = set()

        history_list = history_response.get('history', [])
        for history in history_list:
            for msg in history.get('messagesAdded', []):
                added_ids.add(msg['message']['id'])
            for msg in history.get('messagesDeleted', []):
                deleted_ids.add(msg['message']['id'])

        # Remove from deleted those that were also added (moved)
        added_ids = added_ids - deleted_ids

        logger.info(f"History: {len(added_ids)} added, {len(deleted_ids)} deleted")

        indexed = 0
        deleted = 0

        # Handle deletions
        for msg_id in deleted_ids:
            self.db.delete_email(msg_id)
            deleted += 1

        # Handle additions
        if added_ids:
            added_list = list(added_ids)
            for i in range(0, len(added_list), BATCH_SIZE):
                batch_ids = added_list[i:i + BATCH_SIZE]
                messages = self._batch_get_messages(service, batch_ids)

                if messages:
                    emails_data = []
                    for msg in messages.values():
                        email_data = self._parse_message(msg, user_email)
                        if email_data:
                            emails_data.append(email_data)

                    if emails_data:
                        self.db.upsert_emails_batch(emails_data)
                        embeddings = self.embeddings.generate_email_batch_embeddings(emails_data)

                        for email_data in emails_data:
                            db_email = self.db.get_email_by_message_id(email_data['message_id'])
                            if db_email:
                                email_data['id'] = db_email['id']

                        self.vector_store.add_emails(emails_data, embeddings)
                        indexed += len(emails_data)

                if progress_callback:
                    progress_callback(indexed, len(added_ids))

                if i + BATCH_SIZE < len(added_list):
                    time.sleep(BATCH_DELAY_MS / 1000)

        # Update sync state with new historyId
        new_history_id = history_response.get('historyId', history_id)
        stats = self.db.get_stats(user_email)
        self.db.update_sync_state(user_email, new_history_id, stats['total_emails'])

        duration = time.time() - start_time
        logger.info(f"Incremental sync complete: +{indexed}, -{deleted} in {duration:.1f}s")

        return {
            'status': 'success',
            'added': indexed,
            'deleted': deleted,
            'duration_seconds': round(duration, 1),
            'history_id': new_history_id,
        }

    def _list_message_ids(
        self,
        service,
        max_results: int,
        query: str = "",
    ) -> list[str]:
        """List message IDs from Gmail."""
        message_ids = []
        page_token = None

        while len(message_ids) < max_results:
            remaining = max_results - len(message_ids)
            page_size = min(remaining, 500)  # Gmail max is 500

            request = service.users().messages().list(
                userId='me',
                maxResults=page_size,
                pageToken=page_token,
                q=query if query else None,
            )
            response = request.execute()

            messages = response.get('messages', [])
            message_ids.extend([m['id'] for m in messages])

            page_token = response.get('nextPageToken')
            if not page_token:
                break

        return message_ids[:max_results]

    def _batch_get_messages(
        self,
        service,
        message_ids: list[str],
    ) -> dict:
        """
        Batch fetch message details.

        Gmail API doesn't have native batchGet, so we use new_batch_http_request.
        """
        messages = {}

        def callback(request_id, response, exception):
            if exception:
                logger.warning(f"Error fetching message {request_id}: {exception}")
            else:
                messages[response['id']] = response

        batch = service.new_batch_http_request(callback=callback)

        for msg_id in message_ids:
            batch.add(
                service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='full',
                ),
                request_id=msg_id,
            )

        batch.execute()
        return messages

    def _parse_message(self, message: dict, user_email: str) -> Optional[dict]:
        """Parse Gmail message into indexable format."""
        try:
            payload = message.get('payload', {})
            headers = self._extract_headers(payload)

            # Extract body
            body_text = self._extract_body(payload)

            # Parse date
            date_sent = None
            if 'Date' in headers:
                try:
                    from email.utils import parsedate_to_datetime
                    date_sent = parsedate_to_datetime(headers['Date']).isoformat()
                except Exception:
                    pass

            if not date_sent and 'internalDate' in message:
                # internalDate is milliseconds since epoch
                ts = int(message['internalDate']) / 1000
                date_sent = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

            return {
                'message_id': message['id'],
                'thread_id': message.get('threadId'),
                'user_email': user_email,
                'subject': headers.get('Subject', ''),
                'sender': headers.get('From', ''),
                'body_text': body_text,
                'date_sent': date_sent,
            }
        except Exception as e:
            logger.warning(f"Failed to parse message {message.get('id')}: {e}")
            return None

    def _extract_headers(self, payload: dict) -> dict:
        """Extract common headers from message payload."""
        headers = {}
        for header in payload.get('headers', []):
            name = header.get('name', '')
            if name in ('Subject', 'From', 'To', 'Date', 'Message-ID'):
                headers[name] = header.get('value', '')
        return headers

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from message payload."""
        text_body = ""
        parts = [payload] if 'parts' not in payload else payload.get('parts', [])

        part_queue = list(parts)
        while part_queue:
            part = part_queue.pop(0)
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data')

            if body_data and mime_type == 'text/plain' and not text_body:
                try:
                    text_body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                except Exception:
                    pass

            if mime_type.startswith('multipart/') and 'parts' in part:
                part_queue.extend(part.get('parts', []))

        # Fallback to main payload body
        if not text_body and payload.get('body', {}).get('data'):
            try:
                text_body = base64.urlsafe_b64decode(
                    payload['body']['data']
                ).decode('utf-8', errors='ignore')
            except Exception:
                pass

        return text_body
