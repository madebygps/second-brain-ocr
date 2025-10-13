"""Azure AI Search indexer for storing and searching documents."""

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from .config import Config

logger = Config.get_logger(__name__)


class SearchIndexer:
    """Manages document indexing in Azure AI Search with robust error handling and retry mechanisms."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        index_name: str,
        embedding_dimension: int = 1536,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: int = 30,
    ) -> None:
        """Initialize the search indexer with configuration and retry settings.

        Args:
            endpoint: Azure AI Search service endpoint
            api_key: API key for authentication
            index_name: Name of the search index
            embedding_dimension: Dimension of embedding vectors (default: 1536)
            max_retries: Maximum number of retry attempts for failed operations
            base_delay: Base delay in seconds for exponential backoff
            timeout: Request timeout in seconds
        """
        # Validate inputs
        if not self._validate_config(endpoint, api_key, index_name, embedding_dimension):
            raise ValueError("Invalid configuration parameters")

        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name
        self.embedding_dimension = embedding_dimension
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout

        # Performance tracking
        self.operation_count = 0
        self.error_count = 0

        try:
            credential = AzureKeyCredential(api_key)
            self.index_client = SearchIndexClient(endpoint=endpoint, credential=credential, timeout=timeout)
            self.search_client = SearchClient(
                endpoint=endpoint, index_name=index_name, credential=credential, timeout=timeout
            )

            logger.info(
                "Search indexer initialized - endpoint: %s, index: %s, dimensions: %d",
                endpoint,
                index_name,
                embedding_dimension,
            )
        except Exception as e:
            logger.error("Failed to initialize search indexer: %s", e)
            raise

    def _validate_config(self, endpoint: str, api_key: str, index_name: str, embedding_dimension: int) -> bool:
        """Validate configuration parameters.

        Args:
            endpoint: Azure AI Search service endpoint
            api_key: API key for authentication
            index_name: Name of the search index
            embedding_dimension: Dimension of embedding vectors

        Returns:
            True if all parameters are valid, False otherwise
        """
        try:
            # Validate endpoint
            if not endpoint or not isinstance(endpoint, str):
                logger.error("Invalid endpoint: must be a non-empty string")
                return False

            if not endpoint.startswith(("http://", "https://")):
                logger.error("Invalid endpoint: must start with http:// or https://")
                return False

            # Validate API key
            if not api_key or not isinstance(api_key, str):
                logger.error("Invalid API key: must be a non-empty string")
                return False

            if len(api_key) < 10:  # Basic length check
                logger.error("Invalid API key: too short")
                return False

            # Validate index name
            if not index_name or not isinstance(index_name, str):
                logger.error("Invalid index name: must be a non-empty string")
                return False

            # Azure Search index name constraints
            if not re.match(r"^[a-z][a-z0-9\-]*$", index_name):
                logger.error(
                    "Invalid index name: must start with letter, contain only lowercase letters, numbers, and hyphens"
                )
                return False

            if len(index_name) > 128:
                logger.error("Invalid index name: too long (max 128 characters)")
                return False

            # Validate embedding dimension
            if not isinstance(embedding_dimension, int) or embedding_dimension <= 0:
                logger.error("Invalid embedding dimension: must be a positive integer")
                return False

            if embedding_dimension > 3072:  # Azure AI Search limit
                logger.error("Invalid embedding dimension: exceeds maximum of 3072")
                return False

            return True

        except Exception as e:
            logger.error("Error validating configuration: %s", e)
            return False

    def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute an operation with retry logic and exponential backoff.

        Args:
            operation: Function to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation or None if all retries failed
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                self.operation_count += 1
                start_time = time.time()

                result = operation(*args, **kwargs)

                duration = time.time() - start_time
                logger.debug(
                    "Operation %s completed in %.2fs (attempt %d/%d)",
                    operation.__name__,
                    duration,
                    attempt + 1,
                    self.max_retries,
                )

                return result

            except (ServiceRequestError, HttpResponseError) as e:
                last_exception = e
                self.error_count += 1

                # Check if error is retryable
                status_code = getattr(e, "status_code", None)
                if (
                    status_code is not None
                    and isinstance(status_code, int)
                    and status_code < 500
                    and status_code != 429
                ):
                    logger.error(
                        "Non-retryable error in %s (attempt %d/%d): %s",
                        operation.__name__,
                        attempt + 1,
                        self.max_retries,
                        e,
                    )
                    break

                # Log retry attempt
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2**attempt)  # Exponential backoff
                    logger.warning(
                        "Retryable error in %s (attempt %d/%d): %s. Retrying in %.1fs...",
                        operation.__name__,
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error("Final attempt failed for %s: %s", operation.__name__, e)

            except (ClientAuthenticationError, ValueError) as e:
                # Non-retryable errors
                last_exception = e
                self.error_count += 1
                logger.error("Non-retryable error in %s: %s", operation.__name__, e)
                break

            except Exception as e:
                # Unexpected errors
                last_exception = e
                self.error_count += 1
                logger.error(
                    "Unexpected error in %s (attempt %d/%d): %s", operation.__name__, attempt + 1, self.max_retries, e
                )
                if attempt < self.max_retries - 1:
                    delay = self.base_delay
                    logger.info("Retrying in %.1fs...", delay)
                    time.sleep(delay)

        # All retries exhausted
        if last_exception:
            logger.error("All retry attempts exhausted for %s: %s", operation.__name__, last_exception)

        return None

    def create_or_update_index(self) -> bool:
        """Create or update the search index with retry logic.

        Returns:
            True if index was created/updated successfully, False otherwise
        """

        def _create_index():
            """Internal method to create/update index."""
            logger.info("Creating/updating search index: %s", self.index_name)

            vector_search = VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
                profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw-config")],
            )

            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
                SearchableField(name="content", type=SearchFieldDataType.String, searchable=True),
                SearchableField(name="file_path", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="file_name", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="title", type=SearchFieldDataType.String, searchable=True, filterable=True),
                SimpleField(name="created_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SimpleField(name="indexed_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SimpleField(name="word_count", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.embedding_dimension,
                    vector_search_profile_name="vector-profile",
                ),
            ]

            index = SearchIndex(name=self.index_name, fields=fields, vector_search=vector_search)
            return self.index_client.create_or_update_index(index)

        try:
            start_time = time.time()
            result = self._execute_with_retry(_create_index)

            if result is not None:
                duration = time.time() - start_time
                logger.info("Index '%s' created/updated successfully in %.2fs", self.index_name, duration)
                return True
            else:
                logger.error("Failed to create/update index after all retry attempts")
                return False

        except Exception as e:
            logger.error("Unexpected error creating/updating index: %s", e)
            return False

    def index_document(
        self, file_path: Path, content: str, embedding: list[float], metadata: dict | None = None
    ) -> bool:
        try:
            path_parts = file_path.parts
            category = "unknown"
            source = "unknown"

            if "brain-notes" in path_parts:
                brain_index = path_parts.index("brain-notes")
                if len(path_parts) > brain_index + 1:
                    category = path_parts[brain_index + 1]
                if len(path_parts) > brain_index + 2:
                    source = path_parts[brain_index + 2]

            title = source.replace("-", " ").replace("_", " ").title()

            import re

            # Replace path separators and special chars, then remove all whitespace (including non-breaking spaces)
            doc_id = str(file_path).replace("/", "_").replace("\\", "_")
            doc_id = re.sub(r"[^\w\-=]", "_", doc_id)  # Keep only letters, digits, underscore, dash, equals
            doc_id = doc_id.lstrip("_")

            document = {
                "id": doc_id,
                "content": content,
                "file_path": str(file_path),
                "file_name": file_path.name,
                "category": category,
                "source": source,
                "title": title,
                "created_at": datetime.now(UTC).isoformat(),
                "indexed_at": datetime.now(UTC).isoformat(),
                "word_count": len(content.split()),
                "content_vector": embedding,
            }

            # Add any additional metadata
            if metadata:
                document.update(metadata)

            result = self.search_client.upload_documents(documents=[document])

            if result[0].succeeded:
                logger.info("Successfully indexed document: %s", file_path.name)
                return True
            else:
                logger.error("Failed to index document: %s", file_path.name)
                return False

        except (ValueError, AttributeError, KeyError) as e:
            logger.error("Error indexing document %s: %s", file_path, e)
            return False

    def search(
        self,
        query: str,
        query_vector: list[float] | None = None,
        top: int = 5,
        filter_expression: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            from azure.search.documents.models import VectorizedQuery

            select_fields = ["file_name", "file_path", "content", "category", "source", "title", "created_at"]

            if query_vector:
                vector_query = VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="content_vector")
                results = self.search_client.search(
                    search_text=query,
                    select=select_fields,
                    vector_queries=[vector_query],
                    top=top,
                    filter=filter_expression,
                )
            else:
                results = self.search_client.search(
                    search_text=query, select=select_fields, top=top, filter=filter_expression
                )

            search_results: list[dict[str, Any]] = []
            for result in results:
                content_value = result.get("content", "")
                content_str = str(content_value)[:500] if content_value else ""

                search_results.append(
                    {
                        "file_name": result.get("file_name"),
                        "file_path": result.get("file_path"),
                        "content": content_str,
                        "category": result.get("category"),
                        "source": result.get("source"),
                        "title": result.get("title"),
                        "score": result.get("@search.score"),
                    }
                )

            logger.info("Search returned %d results", len(search_results))
            return search_results

        except (ValueError, AttributeError) as e:
            logger.error("Error searching index: %s", e)
            return []

    def health_check(self) -> bool:
        """Perform a health check on the search service.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            logger.info("Performing health check on search service")

            # Test index client connection
            indexes = list(self.index_client.list_indexes())

            # Check if our index exists
            index_exists = any(idx.name == self.index_name for idx in indexes)

            if index_exists:
                # Test search client with a simple query
                list(self.search_client.search(search_text="*", top=1, select=["id"]))

                logger.info("Health check passed: index '%s' exists and is searchable", self.index_name)
                return True
            else:
                logger.warning("Health check warning: index '%s' does not exist", self.index_name)
                return False

        except Exception as e:
            logger.error("Health check failed: %s", e)
            return False

    def get_index_stats(self) -> dict[str, Any]:
        """Get statistics about the search index.

        Returns:
            Dictionary containing index statistics
        """
        try:
            # Get document count
            search_results = list(self.search_client.search(search_text="*", include_total_count=True, top=0))

            doc_count = getattr(search_results, "get_count", lambda: 0)()

            # Get index information
            try:
                index_info = self.index_client.get_index(self.index_name)
                field_count = len(index_info.fields) if index_info.fields else 0
            except ResourceNotFoundError:
                field_count = 0

            stats = {
                "index_name": self.index_name,
                "document_count": doc_count,
                "field_count": field_count,
                "embedding_dimension": self.embedding_dimension,
                "operation_count": self.operation_count,
                "error_count": self.error_count,
                "error_rate": (self.error_count / max(self.operation_count, 1)) * 100,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            logger.info("Index stats retrieved: %d documents, %d fields", doc_count, field_count)
            return stats

        except Exception as e:
            logger.error("Error retrieving index stats: %s", e)
            return {
                "index_name": self.index_name,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def get_indexer_info(self) -> dict[str, Any]:
        """Get configuration information about the indexer.

        Returns:
            Dictionary containing indexer configuration
        """
        return {
            "endpoint": self.endpoint,
            "index_name": self.index_name,
            "embedding_dimension": self.embedding_dimension,
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "timeout": self.timeout,
            "operation_count": self.operation_count,
            "error_count": self.error_count,
            "version": "enhanced",
        }
