# Use official Python base image
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy project files
COPY pyproject.toml ./
COPY src ./src

# Install dependencies using uv
RUN uv pip install --no-cache -e .

# Create directories for data and watched files
RUN mkdir -p /app/data /brain-notes

# Create volume mount points
VOLUME ["/app/data", "/brain-notes"]

# Run the application
CMD ["python", "-m", "second_brain_ocr.main"]
