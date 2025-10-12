# Local Testing Guide

This guide will help you test the Second Brain OCR application locally before deploying to Synology.

## Prerequisites

- Python 3.13 installed
- uv installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Azure resources created (Document Intelligence, OpenAI, AI Search)
- Azure credentials ready

## Step 1: Set Up Environment

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your Azure credentials:**
   ```bash
   # Use your preferred editor
   nano .env
   # or
   code .env
   ```

   Fill in:
   - `AZURE_DOC_INTELLIGENCE_ENDPOINT` - Your Document Intelligence endpoint
   - `AZURE_DOC_INTELLIGENCE_KEY` - Your Document Intelligence key
   - `AZURE_OPENAI_ENDPOINT` - Your OpenAI endpoint
   - `AZURE_OPENAI_KEY` - Your OpenAI key
   - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` - Your embedding model deployment name
   - `AZURE_SEARCH_ENDPOINT` - Your AI Search endpoint
   - `AZURE_SEARCH_KEY` - Your AI Search admin key

## Step 2: Install Dependencies

```bash
uv sync
```

This will create a virtual environment and install all dependencies.

## Step 3: Create Test Directory Structure

```bash
# Create the test directory structure
mkdir -p brain-notes/books/win-every-argument
mkdir -p brain-notes/books/test-book
mkdir -p brain-notes/articles/sample-article
mkdir -p brain-notes/essays/test-essay

# Create a data directory for state tracking
mkdir -p data
```

## Step 4: Add Test Images

For testing, you'll need some images with text. Options:

### Option A: Use Your Own Images
Copy some photos of book pages or documents to the test directories:
```bash
cp ~/path/to/your/image.jpg brain-notes/books/test-book/page1.jpg
```

### Option B: Create Test Images with Text
If you don't have images handy, you can create simple test images with text using Python:

```bash
uv run python -c "
from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs('brain-notes/books/test-book', exist_ok=True)

# Create a simple test image with text
img = Image.new('RGB', (800, 600), color='white')
d = ImageDraw.Draw(img)

text = '''
Chapter 1: Introduction to Public Speaking

Public speaking is both an art and a science.
The key to effective communication is:

1. Know your audience
2. Structure your message clearly
3. Practice, practice, practice
4. Use body language effectively
5. Connect emotionally with listeners

Remember: The goal is not perfection,
but authentic connection.
'''

# Use default font
d.text((50, 50), text, fill='black')
img.save('brain-notes/books/test-book/page1.jpg')
print('Test image created!')
"
```

You'll need Pillow for this:
```bash
uv add pillow
```

## Step 5: Run the Application Locally

### Option A: Direct Python Execution

```bash
# Update .env to use local paths
# Make sure WATCH_DIR is set to the local path
export WATCH_DIR=$(pwd)/brain-notes
export STATE_FILE=$(pwd)/data/processed_files.json

# Run the application
uv run python -m second_brain_ocr.main
```

### Option B: Using Docker Compose (Recommended for testing)

1. **Update `docker-compose.yml` for local testing:**
   ```yaml
   volumes:
     # Use local brain-notes directory
     - ./brain-notes:/brain-notes:ro
     - ./data:/app/data
   ```

2. **Run with docker-compose:**
   ```bash
   docker-compose up --build
   ```

## Step 6: Monitor the Application

You should see output like:

```
Initializing Second Brain OCR...
Index 'second-brain-notes' created/updated successfully
Initialization complete
Scanning for existing unprocessed files...
Found 1 unprocessed files
Processing new file: /brain-notes/books/test-book/page1.jpg
[1/3] Extracting text from page1.jpg
Extracted 45 words from page1.jpg
[2/3] Generating embedding for page1.jpg
[3/3] Indexing document: page1.jpg
Successfully processed: page1.jpg
Starting file watcher...
Second Brain OCR is now running. Press Ctrl+C to stop.
```

## Step 7: Test Adding New Files

While the application is running, add a new image to one of the directories:

```bash
# In another terminal
cp another-test-image.jpg brain-notes/books/test-book/page2.jpg
```

Watch the logs - you should see it automatically detect and process the new file!

## Step 8: Test Searching

Use the search test script to verify your indexed documents are searchable:

```bash
uv run python test_search.py
```

Enter a query like "public speaking tips" and see if it finds your test document!

## Troubleshooting

### "Configuration errors" on startup

Check that all required environment variables are set in `.env`:
```bash
# Verify your .env file
cat .env | grep -v "^#" | grep -v "^$"
```

### "Failed to initialize search index"

- Verify your Azure AI Search endpoint and key are correct
- Check that you have admin key access (not just query key)
- Ensure the AI Search resource is active in Azure Portal

### "Error processing OCR"

- Verify your Document Intelligence endpoint and key
- Check quota limits in Azure Portal
- Ensure the image is a supported format (JPG, PNG, PDF)

### "Failed to generate embedding"

- Verify your Azure OpenAI endpoint and key
- Check that the deployment name matches exactly
- Ensure your OpenAI resource has an active embedding deployment

### Files not being detected

- Check that the watch directory path is correct
- Verify file permissions (should be readable)
- Look for errors in the logs
- Try manually adding a file while watching the logs

### "Module not found" errors

```bash
# Reinstall dependencies
uv sync --reinstall
```

## Local Testing Checklist

- [ ] Azure credentials configured in `.env`
- [ ] Dependencies installed (`uv sync`)
- [ ] Test directory structure created
- [ ] Test images added
- [ ] Application starts without errors
- [ ] Search index created successfully
- [ ] Initial scan processes existing files
- [ ] File watcher starts successfully
- [ ] New files are detected and processed
- [ ] Search returns results

## Next Steps

Once local testing is successful:

1. Build the Docker image:
   ```bash
   docker build -t second-brain-ocr:latest .
   ```

2. Push to ACR:
   ```bash
   ./build-acr.sh yourregistryname.azurecr.io
   ```

3. Deploy to Synology using Portainer (see [ACR_DEPLOYMENT.md](ACR_DEPLOYMENT.md))

## Cleaning Up Test Data

After testing, you can clean up:

```bash
# Remove test images
rm -rf brain-notes/

# Remove state file
rm -rf data/

# Delete the test search index (optional)
# Use Azure Portal to delete the search index if you want to start fresh
```
