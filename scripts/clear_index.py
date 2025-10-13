#!/usr/bin/env python3
"""Clear all documents from the Azure AI Search index."""

import os
import sys
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "second-brain-notes")


def clear_index():
    """Delete all documents from the search index."""
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_KEY:
        print("Error: Azure Search credentials not found in environment")
        sys.exit(1)

    print(f"Connecting to index: {AZURE_SEARCH_INDEX_NAME}")
    search_client = SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX_NAME,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )

    # Get all document IDs
    print("Fetching all documents...")
    results = search_client.search(search_text="*", select="id")
    doc_ids = [doc["id"] for doc in results]

    if not doc_ids:
        print("Index is already empty")
        return

    print(f"Found {len(doc_ids)} documents to delete")

    # Delete all documents
    print("Deleting documents...")
    documents_to_delete = [{"id": doc_id} for doc_id in doc_ids]
    search_client.delete_documents(documents=documents_to_delete)

    print("Delete operation completed")

    # Wait for eventual consistency
    print("Waiting for index to update...")
    time.sleep(2)

    # Verify deletion
    results = list(search_client.search(search_text="*", select="id"))
    remaining = len(results)

    if remaining == 0:
        print("✓ Index cleared successfully")
    else:
        print(f"⚠ Warning: {remaining} documents still present (eventual consistency delay)")


if __name__ == "__main__":
    clear_index()
