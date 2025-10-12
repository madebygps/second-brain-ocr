# CI/CD Setup Guide

This guide will help you set up the complete CI/CD pipeline for automated testing and deployment to Azure Container Registry.

## Overview

The CI/CD pipeline automatically:
1. **Runs tests** on every push and pull request
2. **Checks code quality** with ruff linting
3. **Validates types** with mypy
4. **Builds and pushes Docker images** to ACR when tests pass on main branch

## Prerequisites

- GitHub repository for this project
- Azure Container Registry (ACR) created
- Azure subscription with appropriate permissions

## Step 1: Create Azure Container Registry

If you don't already have an ACR:

```bash
# Login to Azure
az login

# Create resource group (if needed)
az group create --name second-brain-rg --location eastus

# Create ACR
az acr create \
  --resource-group second-brain-rg \
  --name yourregistryname \
  --sku Basic

# Enable admin user (for GitHub Actions authentication)
az acr update --name yourregistryname --admin-enabled true

# Get credentials
az acr credential show --name yourregistryname
```

**Note the output:**
- `loginServer`: e.g., `yourregistryname.azurecr.io`
- `username`: Usually the registry name
- `password`: Use either `password` or `password2`

## Step 2: Configure GitHub Secrets

Go to your GitHub repository:
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

### Required Secrets

| Secret Name | Value | Description |
|------------|-------|-------------|
| `ACR_REGISTRY` | `yourregistryname.azurecr.io` | Your ACR login server |
| `ACR_USERNAME` | `yourregistryname` | ACR admin username |
| `ACR_PASSWORD` | `your-acr-password` | ACR admin password from Step 1 |

### Optional Secrets

| Secret Name | Value | Description |
|------------|-------|-------------|
| `CODECOV_TOKEN` | `your-codecov-token` | For coverage reporting (optional) |

### Getting ACR Credentials

**Option 1: Azure Portal**
1. Go to Azure Portal → Container registries
2. Select your registry
3. Go to **Access keys**
4. Enable **Admin user**
5. Copy the credentials

**Option 2: Azure CLI**
```bash
az acr credential show --name yourregistryname --output table
```

## Step 3: Verify Workflow Configuration

The workflow file is at `.github/workflows/ci-cd.yml`

It will automatically:
- ✅ Run on every push to `main` branch
- ✅ Run on every pull request to `main` branch
- ✅ Only push to ACR when tests pass on `main` branch

## Step 4: Initial Push

Once secrets are configured, push your code:

```bash
# Create a new GitHub repository
gh repo create second-brain-ocr --private --source=. --remote=origin

# Or add existing repo as remote
git remote add origin https://github.com/your-username/second-brain-ocr.git

# Initial commit
git add .
git commit -m "Initial commit with CI/CD pipeline"

# Push to main
git push -u origin main
```

## Step 5: Monitor the Pipeline

Go to your GitHub repository:
**Actions** tab → View the workflow run

You should see:
1. ✅ **Run Tests** - Executes test suite with coverage
2. ✅ **Code Linting** - Runs ruff checks
3. ✅ **Type Checking** - Runs mypy validation
4. ✅ **Build & Push to ACR** - Builds Docker image and pushes to ACR (only on main)

## Pipeline Behavior

### On Pull Requests
- Runs tests, linting, and type checking
- **Does NOT** build or push Docker images
- Provides feedback on code quality

### On Push to Main
- Runs all checks (tests, linting, type checking)
- **Builds Docker image** if all checks pass
- **Pushes to ACR** with tags:
  - `latest` - Always points to the latest main branch
  - `main-<sha>` - Specific commit hash
  - `main` - Branch reference

### On Push to Other Branches
- Runs tests, linting, and type checking only
- **Does NOT** build or push images

## Using the Images from ACR

After successful build, pull the image:

```bash
# Login to ACR
az acr login --name yourregistryname

# Pull latest image
docker pull yourregistryname.azurecr.io/second-brain-ocr:latest

# Pull specific commit
docker pull yourregistryname.azurecr.io/second-brain-ocr:main-abc1234
```

## Updating Portainer Stack

Once images are in ACR, update your Portainer stack to use:

```yaml
services:
  second-brain-ocr:
    image: yourregistryname.azurecr.io/second-brain-ocr:latest
    # ... rest of config
```

Portainer will pull the latest image from ACR on restart.

## Troubleshooting

### Build Failing: "Error: Unable to locate credentials"

**Problem:** GitHub Actions can't authenticate with ACR

**Solution:**
1. Verify secrets are named exactly: `ACR_REGISTRY`, `ACR_USERNAME`, `ACR_PASSWORD`
2. Check ACR admin user is enabled: `az acr update --name yourregistryname --admin-enabled true`
3. Regenerate credentials: `az acr credential renew --name yourregistryname --password-name password`

### Build Failing: "denied: requested access to the resource is denied"

**Problem:** Credentials are incorrect or expired

**Solution:**
```bash
# Get fresh credentials
az acr credential show --name yourregistryname

# Update GitHub secrets with new values
```

### Tests Failing in CI but Pass Locally

**Problem:** Environment differences

**Solution:**
1. Check Python version matches (3.13)
2. Run `uv sync` to ensure dependencies match
3. Check for hardcoded paths or environment-specific code

### Images Not Showing in ACR

**Problem:** Build succeeded but images aren't visible

**Solution:**
1. Check workflow logs for actual push confirmation
2. Verify in Azure Portal: Container registries → Repositories
3. List repositories: `az acr repository list --name yourregistryname --output table`

## Manual Build and Push (Bypass CI/CD)

If needed, build and push manually:

```bash
# Login
az acr login --name yourregistryname

# Build
docker build -t yourregistryname.azurecr.io/second-brain-ocr:manual .

# Push
docker push yourregistryname.azurecr.io/second-brain-ocr:manual
```

## Monitoring and Logs

### View Workflow Runs
- GitHub → Actions → Select workflow run

### View ACR Activity
```bash
# List all images
az acr repository show-tags \
  --name yourregistryname \
  --repository second-brain-ocr \
  --output table

# Show manifest details
az acr repository show \
  --name yourregistryname \
  --repository second-brain-ocr \
  --output table
```

## Security Best Practices

1. **Use Service Principal** (instead of admin user) for production:
   ```bash
   # Create service principal
   az ad sp create-for-rbac \
     --name second-brain-ocr-sp \
     --role acrpush \
     --scopes /subscriptions/{subscription-id}/resourceGroups/{rg}/providers/Microsoft.ContainerRegistry/registries/{registry}
   ```

2. **Rotate credentials** regularly:
   ```bash
   az acr credential renew --name yourregistryname --password-name password
   ```

3. **Use separate credentials** for CI/CD vs production deployments

4. **Enable vulnerability scanning** in ACR (requires Standard tier or higher)

## Next Steps

After CI/CD is working:
1. Set up **Dependabot** for automatic dependency updates
2. Add **branch protection rules** requiring checks to pass
3. Configure **automatic deployments** to Synology/Portainer
4. Set up **monitoring** and **alerts** for failed builds

## Support

- GitHub Actions docs: https://docs.github.com/en/actions
- Azure ACR docs: https://docs.microsoft.com/en-us/azure/container-registry/
- Docker docs: https://docs.docker.com/
