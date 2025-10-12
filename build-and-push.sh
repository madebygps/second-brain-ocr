#!/bin/bash

# Build and push Docker image for Second Brain OCR
# Usage: ./build-and-push.sh [registry/username] [tag]

set -e

REGISTRY=${1:-"your-username"}
TAG=${2:-"latest"}
IMAGE_NAME="second-brain-ocr"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo "Building Docker image: ${FULL_IMAGE}"
docker build -t ${FULL_IMAGE} .

echo ""
echo "Image built successfully!"
echo ""
echo "To push to registry, run:"
echo "  docker push ${FULL_IMAGE}"
echo ""
echo "To test locally first, run:"
echo "  docker-compose up"
