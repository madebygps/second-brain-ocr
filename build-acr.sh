#!/bin/bash

# Build and push Docker image to Azure Container Registry
# Usage: ./build-acr.sh [registry-name.azurecr.io] [tag]

set -e

if [ -z "$1" ]; then
    echo "Usage: ./build-acr.sh [registry-name.azurecr.io] [tag]"
    echo "Example: ./build-acr.sh myregistry.azurecr.io latest"
    exit 1
fi

REGISTRY=$1
TAG=${2:-"latest"}
IMAGE_NAME="second-brain-ocr"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

# Extract registry name (everything before .azurecr.io)
REGISTRY_NAME=$(echo $REGISTRY | sed 's/.azurecr.io//')

echo "================================================"
echo "Building and pushing to Azure Container Registry"
echo "================================================"
echo "Registry: ${REGISTRY}"
echo "Image: ${FULL_IMAGE}"
echo ""

# Login to ACR
echo "Logging in to Azure Container Registry..."
az acr login --name ${REGISTRY_NAME}

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to login to ACR. Make sure:"
    echo "  1. Azure CLI is installed (az --version)"
    echo "  2. You're logged in to Azure (az login)"
    echo "  3. You have access to the registry"
    exit 1
fi

echo ""
echo "Building Docker image..."
docker build -t ${FULL_IMAGE} .

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Docker build failed"
    exit 1
fi

echo ""
echo "Pushing image to ACR..."
docker push ${FULL_IMAGE}

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Docker push failed"
    exit 1
fi

echo ""
echo "================================================"
echo "SUCCESS! Image pushed successfully"
echo "================================================"
echo ""
echo "Image: ${FULL_IMAGE}"
echo ""
echo "Next steps:"
echo "  1. In Portainer, add ACR as a registry:"
echo "     - Go to Registries > Add Registry"
echo "     - Select Azure"
echo "     - Registry: ${REGISTRY}"
echo "     - Get credentials from: Azure Portal > ${REGISTRY_NAME} > Access keys"
echo ""
echo "  2. Update docker-compose.yml image to:"
echo "     image: ${FULL_IMAGE}"
echo ""
echo "  3. Deploy the stack in Portainer"
echo ""
