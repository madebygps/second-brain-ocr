#!/usr/bin/env python3
"""Check Azure AI Search index statistics and storage usage."""

import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv

# Load .env from repository root
repo_root = Path(__file__).parent.parent
load_dotenv(repo_root / ".env")

# Initialize client
index_client = SearchIndexClient(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"), credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_KEY"))
)

index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "second-brain-notes")

try:
    # Get index statistics
    index = index_client.get_index(index_name)
    stats = index_client.get_index_statistics(index_name)

    print("=" * 60)
    print(f"Index: {index_name}")
    print("=" * 60)

    # Handle both dict and object response types
    if isinstance(stats, dict):
        doc_count = stats.get('document_count', 0)
        storage_size = stats.get('storage_size', 0)
    else:
        doc_count = stats.document_count
        storage_size = stats.storage_size

    print(f"Document Count: {doc_count:,}")
    print(f"Storage Size: {storage_size:,} bytes ({storage_size / 1024 / 1024:.2f} MB)")
    print()

    # Calculate remaining capacity (Free tier = 50 MB, 10K docs max)
    free_tier_limit_mb = 50
    free_tier_doc_limit = 10000
    used_mb = storage_size / 1024 / 1024
    remaining_mb = free_tier_limit_mb - used_mb
    usage_percent = (used_mb / free_tier_limit_mb) * 100

    print("Free Tier Usage:")
    print(f"  Storage: {used_mb:.2f} MB / {free_tier_limit_mb} MB ({usage_percent:.1f}%)")
    print(f"  Documents: {doc_count:,} / {free_tier_doc_limit:,} ({(doc_count / free_tier_doc_limit) * 100:.1f}%)")
    print(f"  Remaining: {remaining_mb:.2f} MB, {free_tier_doc_limit - doc_count:,} docs")

    if usage_percent > 80:
        print("\n⚠️  WARNING: You're using over 80% of free tier storage!")
        print("   Consider upgrading or archiving old documents.")
    elif usage_percent > 90:
        print("\n🚨 CRITICAL: You're using over 90% of free tier storage!")
        print("   Upgrade soon to avoid service interruption.")
    else:
        print("\n✓ Storage usage is healthy")

    print()
    print("Estimated Capacity:")
    if doc_count > 0:
        avg_doc_size = storage_size / doc_count
        remaining_docs = int(remaining_mb * 1024 * 1024 / avg_doc_size)
        print(f"  Average document size: {avg_doc_size / 1024:.2f} KB")
        print(f"  Estimated remaining capacity: ~{remaining_docs:,} more documents")

    print("=" * 60)

except Exception as e:
    print(f"Error: {e}")
    print("\nMake sure:")
    print("  1. Your .env file is configured correctly")
    print("  2. The index exists (run the main app first)")
    print("  3. You have valid Azure AI Search credentials")
