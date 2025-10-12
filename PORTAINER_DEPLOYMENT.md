# Portainer Deployment Guide

Quick guide for deploying Second Brain OCR to Synology NAS using Portainer.

## Prerequisites

- Portainer installed on Synology
- Azure Container Registry with the second-brain-ocr image
- Nextcloud installed with brain-notes directory
- Azure credentials ready

## Step 1: Add Azure Container Registry to Portainer

1. Open Portainer web interface
2. Go to **Registries** in left sidebar
3. Click **Add registry**
4. Select **Azure** as provider
5. Fill in details:
   - Name: `Azure CR`
   - Registry URL: `yourregistryname.azurecr.io`
   - Username: Your ACR username
   - Password: Your ACR password
6. Click **Add registry**

Get ACR credentials:
```bash
az acr credential show --name yourregistryname
```

## Step 2: Create Data Directory on Synology

SSH into Synology or use File Station:
```bash
mkdir -p /volume1/docker/second-brain-ocr/data
chmod 755 /volume1/docker/second-brain-ocr/data
```

## Step 3: Find Your Nextcloud Path

Typical Nextcloud path structure:
```
/volume1/nextcloud/data/YOUR_USERNAME/files/brain-notes
```

Verify it exists:
```bash
ls -la /volume1/nextcloud/data/YOUR_USERNAME/files/brain-notes
```

## Step 4: Create Stack in Portainer

1. Go to **Stacks** in Portainer
2. Click **Add stack**
3. Name: `second-brain-ocr`
4. Choose **Web editor**
5. Paste this docker-compose content:

```yaml
version: '3.8'

services:
  second-brain-ocr:
    image: yourregistryname.azurecr.io/second-brain-ocr:latest
    container_name: second-brain-ocr
    restart: unless-stopped

    environment:
      - WATCH_DIR=/brain-notes
      - USE_POLLING=true
      - POLLING_INTERVAL=60
      - AZURE_DOC_INTELLIGENCE_ENDPOINT=${AZURE_DOC_INTELLIGENCE_ENDPOINT}
      - AZURE_DOC_INTELLIGENCE_KEY=${AZURE_DOC_INTELLIGENCE_KEY}
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_KEY=${AZURE_OPENAI_KEY}
      - AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}
      - AZURE_OPENAI_API_VERSION=2024-02-01
      - AZURE_SEARCH_ENDPOINT=${AZURE_SEARCH_ENDPOINT}
      - AZURE_SEARCH_KEY=${AZURE_SEARCH_KEY}
      - AZURE_SEARCH_INDEX_NAME=second-brain-notes
      - BATCH_SIZE=10
      - STATE_FILE=/app/data/processed_files.json
      - WEBHOOK_URL=${WEBHOOK_URL}

    volumes:
      - /volume1/nextcloud/data/YOUR_USERNAME/files/brain-notes:/brain-notes:ro
      - /volume1/docker/second-brain-ocr/data:/app/data

    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"
```

6. Update the image name with your ACR registry
7. Update the Nextcloud path with your username

## Step 5: Add Environment Variables

Scroll down to **Environment variables** section and add:

| Name | Value |
|------|-------|
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Your endpoint URL |
| `AZURE_DOC_INTELLIGENCE_KEY` | Your key |
| `AZURE_OPENAI_ENDPOINT` | Your endpoint URL |
| `AZURE_OPENAI_KEY` | Your key |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Your deployment name |
| `AZURE_SEARCH_ENDPOINT` | Your endpoint URL |
| `AZURE_SEARCH_KEY` | Your key |
| `WEBHOOK_URL` | Discord/ntfy.sh URL (optional) |

## Step 6: Deploy the Stack

1. Click **Deploy the stack**
2. Wait for deployment to complete
3. Go to **Containers**
4. Find `second-brain-ocr` container
5. Click on it to view details

## Step 7: Verify Deployment

Check the logs:
1. Click on the container
2. Go to **Logs** tab
3. Look for:
```
============================================================
Second Brain OCR - Starting
============================================================
✓ Webhook notifications enabled
✓ Using embedding dimension: 3072
✓ Search index ready: second-brain-notes
✓ Initialization complete
============================================================

Scanning for unprocessed files...
✓ No unprocessed files found

Starting file watcher...
Watching: /brain-notes
Polling interval: 60 seconds (~1 minutes)
Reason: Reliable detection of Nextcloud web uploads (atomic writes)
File watcher started in polling mode, watching: /brain-notes
============================================================
✓ Ready - Monitoring for new files
============================================================
```

## Step 8: Test the System

1. Upload an image to Nextcloud:
   - Path: `brain-notes/books/test-book/page1.jpg`
2. Wait for Nextcloud to sync to Synology
3. Wait up to 60 seconds for polling cycle to detect the file
4. Check container logs for processing messages
5. If webhook is configured, check for notification

Expected log output:
```
→ Processing: page1.jpg
  [1/3] Extracting text...
  ✓ Extracted 360 words
  [2/3] Generating embedding...
  ✓ Embedding generated
  [3/3] Indexing document...
  ✓ Successfully indexed
✓ Completed: page1.jpg (360 words)
```

## Updating the Application

When you push new code to GitHub:

1. CI/CD automatically builds and pushes to ACR
2. In Portainer:
   - Go to your stack
   - Click **Editor**
   - Click **Update the stack**
   - Enable **Pull latest image**
   - Click **Update**

Or manually pull and recreate:
1. Click on container
2. Click **Recreate**
3. Enable **Pull latest image**
4. Click **Recreate**

## Troubleshooting

**Container won't start:**
- Check logs for error messages
- Verify all environment variables are set
- Verify ACR credentials are correct

**Files not being detected:**
- Wait up to 60 seconds for polling cycle (check logs for "Polling interval" message)
- Verify volume path: `/volume1/nextcloud/data/YOUR_USERNAME/files/brain-notes`
- Check file permissions: `ls -la /volume1/nextcloud/data/YOUR_USERNAME/files/brain-notes`
- Ensure Nextcloud sync is working
- For instant detection of direct file additions (not Nextcloud web uploads), set `USE_POLLING=false`

**"Configuration errors" in logs:**
- Check that all required Azure credentials are set
- Verify endpoints are correct (must start with https://)

**State not persisting across restarts:**
- Verify data volume is mounted: `/volume1/docker/second-brain-ocr/data`
- Check permissions on data directory

**Can't pull image from ACR:**
- Verify ACR is added to Portainer registries
- Test ACR credentials manually:
```bash
docker login yourregistryname.azurecr.io
docker pull yourregistryname.azurecr.io/second-brain-ocr:latest
```

## Monitoring

View real-time logs:
1. Go to container in Portainer
2. Click **Logs** tab
3. Enable **Auto-refresh logs**

Check resource usage:
1. Go to container in Portainer
2. Click **Stats** tab
3. Monitor CPU and memory usage

## Next Steps

- Set up webhook notifications for Discord or ntfy.sh
- Add more categories to your brain-notes directory
- Use test_search.py locally to verify indexing is working
- Monitor Azure service costs and usage
