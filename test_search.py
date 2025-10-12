#!/usr/bin/env python3
"""Test script for searching indexed documents."""

import os

from dotenv import load_dotenv

from src.second_brain_ocr.embeddings import EmbeddingGenerator
from src.second_brain_ocr.indexer import SearchIndexer

# Load environment
load_dotenv()

print("=" * 60)
print("Second Brain OCR - Search Test")
print("=" * 60)
print()

# Initialize clients
print("Initializing Azure clients...")
embedding_gen = EmbeddingGenerator(
    endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    deployment_name=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

# Determine embedding dimension based on model
deployment_name = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
embedding_dimension = 1536  # Default
if "text-embedding-3-large" in deployment_name:
    embedding_dimension = 3072
elif "text-embedding-3-small" in deployment_name:
    embedding_dimension = 1536

indexer = SearchIndexer(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
    api_key=os.getenv("AZURE_SEARCH_KEY"),
    index_name=os.getenv("AZURE_SEARCH_INDEX_NAME", "second-brain-notes"),
    embedding_dimension=embedding_dimension,
)
print("✓ Clients initialized\n")

# Test search
query = input("Enter your search query (or press Enter for 'public speaking'): ").strip()
if not query:
    query = "public speaking"

print(f"\nSearching for: '{query}'...")
print("Generating query embedding...")

# Generate query embedding
query_vector = embedding_gen.generate_embedding(query)

if not query_vector:
    print("✗ Failed to generate embedding")
    exit(1)

print("✓ Embedding generated")
print("Searching index...")

# Search
results = indexer.search(query=query, query_vector=query_vector, top=5)

# Display results
print("\n" + "=" * 60)
if not results:
    print("No results found.")
    print("\nTips:")
    print("- Make sure you've processed some images first")
    print("- Try running the main application to index documents")
    print("- Check that documents were successfully indexed (check logs)")
else:
    print(f"Found {len(results)} result(s):\n")
    for i, result in enumerate(results, 1):
        print(f"{'─' * 60}")
        print(f"Result {i}: {result.get('title', 'Unknown')}")
        print(f"{'─' * 60}")
        print(f"From: {result.get('category', 'Unknown').title()} > {result.get('title', 'Unknown')}")
        print(f"File: {result.get('file_name', 'Unknown')}")
        print(f"Relevance Score: {result.get('score', 0):.4f}")
        print("\nContent Preview:")
        print(f"{result.get('content', '')[:300]}...")
        print()

print("=" * 60)
