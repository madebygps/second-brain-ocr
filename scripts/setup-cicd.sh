#!/bin/bash
set -e

echo "🚀 Second Brain OCR - CI/CD Setup Script"
echo "=========================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check if az CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI (az) is not installed."
    echo "Install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

echo "✅ Required tools found"
echo ""

# Get ACR name
read -p "Enter your Azure Container Registry name (e.g., myregistry): " ACR_NAME

if [ -z "$ACR_NAME" ]; then
    echo "❌ ACR name is required"
    exit 1
fi

echo ""
echo "📦 Getting ACR credentials..."

# Get ACR credentials
ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)
ACR_CREDENTIALS=$(az acr credential show --name "$ACR_NAME" --output json)
ACR_USERNAME=$(echo "$ACR_CREDENTIALS" | grep -o '"username": *"[^"]*"' | cut -d'"' -f4)
ACR_PASSWORD=$(echo "$ACR_CREDENTIALS" | grep -o '"password": *"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$ACR_LOGIN_SERVER" ] || [ -z "$ACR_USERNAME" ] || [ -z "$ACR_PASSWORD" ]; then
    echo "❌ Failed to get ACR credentials. Make sure:"
    echo "   1. You're logged in to Azure: az login"
    echo "   2. The ACR exists: az acr show --name $ACR_NAME"
    echo "   3. Admin user is enabled: az acr update --name $ACR_NAME --admin-enabled true"
    exit 1
fi

echo "✅ Retrieved ACR credentials"
echo "   Registry: $ACR_LOGIN_SERVER"
echo "   Username: $ACR_USERNAME"
echo ""

# Check if in a git repo
if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    echo "❌ Not in a git repository. Run 'git init' first."
    exit 1
fi

# Check if GitHub remote exists
if ! git remote get-url origin &> /dev/null; then
    echo "⚠️  No GitHub remote 'origin' found."
    read -p "Enter your GitHub repository (e.g., username/repo): " GITHUB_REPO

    if [ -z "$GITHUB_REPO" ]; then
        echo "❌ Repository name is required"
        exit 1
    fi

    echo "Creating GitHub repository..."
    gh repo create "$GITHUB_REPO" --private --source=. --remote=origin
fi

echo ""
echo "🔐 Setting GitHub secrets..."

# Set secrets using gh CLI
gh secret set ACR_REGISTRY --body "$ACR_LOGIN_SERVER"
gh secret set ACR_USERNAME --body "$ACR_USERNAME"
gh secret set ACR_PASSWORD --body "$ACR_PASSWORD"

echo "✅ GitHub secrets configured:"
echo "   - ACR_REGISTRY"
echo "   - ACR_USERNAME"
echo "   - ACR_PASSWORD"
echo ""

# Optional: Codecov token
read -p "Do you have a Codecov token? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter Codecov token: " CODECOV_TOKEN
    if [ -n "$CODECOV_TOKEN" ]; then
        gh secret set CODECOV_TOKEN --body "$CODECOV_TOKEN"
        echo "✅ CODECOV_TOKEN configured"
    fi
fi

echo ""
echo "✅ CI/CD Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Commit and push your code:"
echo "   git add ."
echo "   git commit -m 'Initial commit with CI/CD'"
echo "   git push -u origin main"
echo ""
echo "2. View workflow runs:"
echo "   gh workflow view"
echo "   gh run list"
echo ""
echo "3. Monitor in browser:"
echo "   gh browse --actions"
echo ""
echo "📚 For more details, see docs/CICD_SETUP.md"
