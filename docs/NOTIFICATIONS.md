# Webhook Notifications

Get notified when files are processed using webhook notifications.

## Setup

Add a `WEBHOOK_URL` to your `.env` file:

```bash
WEBHOOK_URL=https://your-webhook-endpoint
```

## Notification Events

The webhook sends JSON payloads for three event types:

### 1. File Processed

Sent when a single file is successfully processed:

```json
{
  "event": "file_processed",
  "timestamp": "2025-10-12T17:45:30.123456",
  "file": {
    "name": "page1.jpg",
    "path": "/brain-notes/books/atomic-habits/page1.jpg",
    "word_count": 423
  },
  "metadata": {
    "category": "books",
    "source": "atomic-habits",
    "title": "Atomic Habits"
  },
  "message": "Processed: Atomic Habits (423 words)"
}
```

### 2. Batch Complete

Sent after processing multiple files on startup:

```json
{
  "event": "batch_complete",
  "timestamp": "2025-10-12T17:50:15.789012",
  "summary": {
    "files_processed": 5,
    "duration_seconds": 42.31
  },
  "message": "Batch complete: 5 file(s) processed in 42.3s"
}
```

### 3. Processing Error

Sent when file processing fails:

```json
{
  "event": "processing_error",
  "timestamp": "2025-10-12T17:52:00.456789",
  "file": {
    "name": "corrupted.jpg",
    "path": "/brain-notes/books/test/corrupted.jpg"
  },
  "error": "Failed to extract text: invalid image format",
  "message": "Error processing corrupted.jpg: Failed to extract text: invalid image format"
}
```

## Popular Services

### ntfy.sh (Easiest - No Account Required!)

Get instant push notifications on your phone:

```bash
# 1. Choose a unique topic name (or use a random one)
WEBHOOK_URL=https://ntfy.sh/my-second-brain-ocr-12345

# 2. Subscribe on your phone:
# - Install ntfy app (iOS/Android)
# - Subscribe to: my-second-brain-ocr-12345
```

**Pros:** No account, instant setup, mobile apps available
**Cons:** Public topic name (anyone can subscribe if they know it)

### Discord Webhook

Send notifications to a Discord channel:

```bash
# 1. In Discord: Server Settings → Integrations → Webhooks → New Webhook
# 2. Copy the webhook URL
WEBHOOK_URL=https://discord.com/api/webhooks/123456789/abcdefghijklmnop
```

Discord webhooks are automatically detected and formatted. The application sends only the message text to Discord's `content` field, ensuring clean notifications.

**Pros:** Rich formatting, permanent history, team access
**Cons:** Requires Discord server

### Slack Webhook

Send notifications to a Slack channel:

```bash
# 1. Create Slack App: https://api.slack.com/apps
# 2. Enable Incoming Webhooks
# 3. Add webhook to workspace
WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX
```

**Pros:** Professional, integrates with workflows
**Cons:** Requires Slack workspace

### IFTTT / Zapier

Connect to thousands of services:

```bash
# 1. Create webhook trigger in IFTTT/Zapier
# 2. Use the provided webhook URL
WEBHOOK_URL=https://maker.ifttt.com/trigger/file_processed/with/key/YOUR_KEY

# Connect to:
# - Email notifications
# - SMS messages
# - Smart home devices
# - Google Sheets logging
# - And more...
```

**Pros:** Endless integration possibilities
**Cons:** May require paid plan for some features

## Custom Webhook Server

Process webhook events with your own code:

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    event = data.get('event')

    if event == 'file_processed':
        print(f"Processed: {data['file']['name']} ({data['file']['word_count']} words)")
    elif event == 'batch_complete':
        print(f"Batch done: {data['summary']['files_processed']} files")
    elif event == 'processing_error':
        print(f"Error: {data['file']['name']}")

    return {'status': 'ok'}, 200

if __name__ == '__main__':
    app.run(port=8080)
```

Then use: `WEBHOOK_URL=http://your-server:8080/webhook`

## Testing

Test your webhook with curl:

```bash
curl -X POST https://your-webhook-url \
  -H "Content-Type: application/json" \
  -d '{
    "event": "file_processed",
    "timestamp": "2025-10-12T17:45:30",
    "file": {"name": "test.jpg", "word_count": 100},
    "message": "Test notification"
  }'
```

## Disabling Notifications

Simply remove or comment out `WEBHOOK_URL` in your `.env` file:

```bash
# WEBHOOK_URL=https://...
```

No notifications will be sent when `WEBHOOK_URL` is empty.

## Security Considerations

- **ntfy.sh**: Use a unique, hard-to-guess topic name
- **Discord/Slack**: Keep webhook URLs secret (they grant posting access)
- **Custom server**: Implement authentication if exposing publicly
- **HTTPS**: Always use HTTPS webhooks for encrypted transmission

## Troubleshooting

**Notifications not arriving?**
- Check logs for webhook errors: `docker-compose logs -f`
- Verify webhook URL is correct
- Test URL with curl command above
- Check firewall/network allows outbound HTTPS

**Too many notifications?**
- Notifications are sent per-file during processing
- Consider using batch complete event only for bulk imports
- Implement filtering in your webhook receiver

**Need more control?**
- Fork the `notifier.py` module
- Add custom logic for when to send notifications
- Filter by file type, category, or word count
