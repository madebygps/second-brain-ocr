# Azure Container Registry Deployment Guide

This guide walks you through deploying Second Brain OCR to your Synology NAS using Azure Container Registry (ACR) and Portainer.

## Prerequisites

- Azure subscription with access to create resources
- Azure CLI installed on your development machine
- Docker installed on your development machine
- Portainer running on your Synology NAS
- Nextcloud installed on Synology with brain-notes directory

## Step 1: Create Azure Container Registry

If you don't already have an ACR, create one:

```bash
# Login to Azure
az login

# Create resource group (or use existing)
az group create --name second-brain-rg --location eastus

# Create ACR (choose a unique name)
az acr create \
  --resource-group second-brain-rg \
  --name yourregistryname \
  --sku Basic
```

**Note:** ACR names must be globally unique and contain only lowercase letters and numbers.

## Step 2: Build and Push Image

### Option A: Using the Helper Script

```bash
./build-acr.sh yourregistryname.azurecr.io
```

### Option B: Manual Build and Push

```bash
# Login to ACR
az acr login --name yourregistryname

# Build the image
docker build -t yourregistryname.azurecr.io/second-brain-ocr:latest .

# Push to ACR
docker push yourregistryname.azurecr.io/second-brain-ocr:latest
```

## Step 3: Get ACR Credentials

You'll need these for Portainer:

```bash
# Enable admin user on ACR
az acr update --name yourregistryname --admin-enabled true

# Get credentials
az acr credential show --name yourregistryname
```

Or get them from Azure Portal:
1. Go to your ACR resource
2. Navigate to **Settings > Access keys**
3. Enable **Admin user**
4. Note the **Login server**, **Username**, and **Password**

## Step 4: Configure Portainer

### Add ACR as a Registry in Portainer

1. Login to Portainer on your Synology
2. Go to **Registries** (in the left menu)
3. Click **Add registry**
4. Select **Azure** as the provider
5. Fill in the details:
   - **Name**: Azure CR (or any name you prefer)
   - **Registry**: `yourregistryname.azurecr.io`
   - **Username**: (from Step 3)
   - **Password**: (from Step 3)
6. Click **Add registry**

### Create the Stack

1. Go to **Stacks** in Portainer
2. Click **Add stack**
3. Give it a name: `second-brain-ocr`
4. Choose **Web editor**
5. Copy the contents of `docker-compose.acr.yml`
6. Update the following in the YAML:
   - Image name: `yourregistryname.azurecr.io/second-brain-ocr:latest`
   - Nextcloud path: `/volume1/nextcloud/data/YOUR_USER/files/brain-notes`
   - Data path: `/volume1/docker/second-brain-ocr/data`

7. Scroll down to **Environment variables**
8. Add all required variables from `.env.example`:
   - `AZURE_DOC_INTELLIGENCE_ENDPOINT`
   - `AZURE_DOC_INTELLIGENCE_KEY`
   - `AZURE_OPENAI_ENDPOINT`
   - `AZURE_OPENAI_KEY`
   - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
   - `AZURE_SEARCH_ENDPOINT`
   - `AZURE_SEARCH_KEY`
   - `AZURE_SEARCH_INDEX_NAME`

9. Click **Deploy the stack**

## Step 5: Verify Deployment

1. In Portainer, go to **Containers**
2. Find `second-brain-ocr` container
3. Click on it and go to **Logs**
4. You should see:
   ```
   Initializing Second Brain OCR...
   Index 'second-brain-notes' created/updated successfully
   Initialization complete
   Scanning for existing unprocessed files...
   Starting file watcher...
   Second Brain OCR is now running. Press Ctrl+C to stop.
   ```

## Step 6: Test the System

1. Take a photo with your phone
2. Upload it to Nextcloud: `brain-notes/books/test-book/page1.jpg`
3. Wait for it to sync to your Synology
4. Check the container logs - you should see:
   ```
   New file detected: /brain-notes/books/test-book/page1.jpg
   Processing new file: /brain-notes/books/test-book/page1.jpg
   [1/3] Extracting text from page1.jpg
   [2/3] Generating embedding for page1.jpg
   [3/3] Indexing document: page1.jpg
   Successfully processed: page1.jpg
   ```

## Updating the Application

When you make changes to the code:

```bash
# Rebuild and push
./build-acr.sh yourregistryname.azurecr.io

# In Portainer, go to your stack
# Click "Pull and redeploy"
# Or recreate the container to pull the latest image
```

## Troubleshooting

### Container won't start

Check the logs in Portainer. Common issues:
- Missing environment variables
- Invalid Azure credentials
- Volume mount path doesn't exist

### Files not being detected

- Verify the volume mount path is correct
- Check that files are syncing to Synology
- Look for "Scanning for existing files" in logs
- Check file permissions on the mounted directory

### ACR authentication fails

```bash
# Re-login to ACR
az acr login --name yourregistryname

# Or use admin credentials
docker login yourregistryname.azurecr.io -u USERNAME -p PASSWORD
```

### Can't pull image in Portainer

- Verify ACR registry is added correctly in Portainer
- Check that admin user is enabled on ACR
- Ensure credentials are correct
- Try pulling manually on Synology:
  ```bash
  docker login yourregistryname.azurecr.io
  docker pull yourregistryname.azurecr.io/second-brain-ocr:latest
  ```

## Cost Considerations

Azure Container Registry pricing:
- **Basic**: ~$5/month (10GB storage, best for development)
- **Standard**: ~$20/month (100GB storage)
- **Premium**: ~$50/month (500GB storage, geo-replication)

For this project, the **Basic** tier is more than sufficient.

## Security Best Practices

1. **Use Managed Identity** (advanced): Instead of storing API keys in environment variables, use Azure Managed Identity for ACR access
2. **Rotate credentials**: Periodically rotate your Azure service keys
3. **Restrict ACR access**: Use Azure RBAC to limit who can push/pull images
4. **Use image scanning**: Enable Defender for Cloud on ACR for vulnerability scanning
5. **Network security**: Consider Azure Private Link for ACR if concerned about public endpoints

## Alternative: Use ACR Tasks for Automated Builds

You can also set up automated builds in ACR:

```bash
# Create a build task that builds on every git push
az acr task create \
  --registry yourregistryname \
  --name second-brain-ocr-build \
  --image second-brain-ocr:{{.Run.ID}} \
  --image second-brain-ocr:latest \
  --context https://github.com/YOUR_USERNAME/second-brain-ocr.git \
  --file Dockerfile \
  --git-access-token YOUR_GITHUB_PAT
```

This automatically builds and pushes new images when you push to your repository.
