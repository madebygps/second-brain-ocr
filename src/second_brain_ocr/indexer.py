"""Azure AI Search indexer for storing and searching documents."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.core.credentials import AzureKeyCredential
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

logger = logging.getLogger(__name__)


class SearchIndexer:
    """Manages document indexing in Azure AI Search."""

    def __init__(self, endpoint: str, api_key: str, index_name: str, embedding_dimension: int = 1536) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name
        self.embedding_dimension = embedding_dimension

        credential = AzureKeyCredential(api_key)
        self.index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
        self.search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)

    def create_or_update_index(self) -> None:
        try:
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

            self.index_client.create_or_update_index(index)
            logger.info("Index '%s' created/updated successfully", self.index_name)

        except (ValueError, AttributeError) as e:
            logger.error("Error creating/updating index: %s", e)
            raise

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
