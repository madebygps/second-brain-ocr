"""Azure OpenAI embeddings generation."""

import logging

from openai import AzureOpenAI

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates embeddings using Azure OpenAI."""

    def __init__(self, endpoint: str, api_key: str, deployment_name: str, api_version: str = "2024-02-01") -> None:
        self.client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        self.deployment_name = deployment_name

    def generate_embedding(self, text: str) -> list[float] | None:
        try:
            if not text or not text.strip():
                logger.warning("Empty text provided for embedding generation")
                return None

            logger.debug("Generating embedding for text of length %d", len(text))

            response = self.client.embeddings.create(model=self.deployment_name, input=text)

            embedding_data: list[float] = list(response.data[0].embedding)

            logger.debug("Generated embedding with dimension %d", len(embedding_data))
            return embedding_data

        except (ValueError, AttributeError) as e:
            logger.error("Error generating embedding: %s", e)
            return None

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float] | None]:
        embeddings = []

        for i, text in enumerate(texts):
            logger.info("Generating embedding %d/%d", i + 1, len(texts))
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)

        return embeddings

    def chunk_text(self, text: str, max_tokens: int = 8000, overlap: int = 200) -> list[str]:
        max_chars = max_tokens * 4
        overlap_chars = overlap * 4

        if len(text) <= max_chars:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + max_chars

            if end < len(text):
                for punct in [". ", "! ", "? ", "\n\n"]:
                    last_punct = text.rfind(punct, start, end)
                    if last_punct > start:
                        end = last_punct + len(punct)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - overlap_chars if end < len(text) else end

        logger.info("Split text into %d chunks", len(chunks))
        return chunks
