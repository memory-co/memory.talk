# Exporter Guide

This guide explains how to create a custom exporter for talk-memory.

## What is an Exporter?

An exporter is a component that extracts conversation data from a chat platform and sends it to the talk-memory server.

## Exporter Types

| Type | Description | Examples |
|------|-------------|----------|
| Browser Extension | Extracts from web-based chat platforms | ChatGPT, Gemini, Claude Web |
| Script | Uses APIs or reads exported files | DingTalk, Email (IMAP) |
| Local Reader | Reads local data files | Claude Code JSONL files |

## Basic Structure

```
exporters/
├── my-exporter/
│   ├── exporter.yaml    # Metadata
│   └── export.py        # Export script
```

## exporter.yaml

```yaml
name: my-exporter
platform: my-platform
type: script             # browser-extension | script | local-reader
version: "0.1.0"
description: "Description of what this exporter does"
author: "Your Name"
```

## Minimal Example

A minimal exporter is just a script that POSTs data to the server:

```python
#!/usr/bin/env python3
"""talk-memory exporter: My Custom Platform"""
import requests
import json
from datetime import datetime

# Get messages from your platform
messages = [
    {
        "uuid": "msg-001",
        "role": "user",
        "content": "Hello",
        "timestamp": datetime.now().isoformat() + "Z"
    },
    {
        "uuid": "msg-002",
        "parentUuid": "msg-001",
        "role": "assistant",
        "content": "Hi there!",
        "timestamp": datetime.now().isoformat() + "Z"
    }
]

# Send to talk-memory server
requests.post("http://localhost:7900/api/ingest", json={
    "platform": "my-platform",
    "session_id": "session-001",
    "messages": messages,
    "metadata": {
        "title": "My Conversation",
        "participants": [
            {"name": "User", "role": "user"},
            {"name": "AI Assistant", "role": "assistant", "model": "gpt-4"}
        ]
    }
})
```

## Message Format

Messages should follow this structure:

```json
{
  "uuid": "unique-message-id",
  "parentUuid": "parent-message-id",  // optional, for threading
  "role": "user | assistant | system",
  "content": "Message text",
  "timestamp": "2024-01-01T00:00:00Z",
  "attachments": [  // optional
    {
      "hash": "sha256-hash",
      "name": "filename.pdf",
      "size": 1024,
      "mime": "application/pdf"
    }
  ]
}
```

## Uploading Attachments

To upload attachments (images, files):

```python
# First upload the blob
with open("attachment.pdf", "rb") as f:
    files = {"file": f}
    data = {"platform": "my-platform"}
    response = requests.post(
        "http://localhost:7900/api/ingest/blob",
        data=data,
        files=files
    )
    file_hash = response.json()["hash"]

# Then reference it in the message
message = {
    "uuid": "msg-001",
    "role": "user",
    "content": "Here is the file",
    "timestamp": datetime.now().isoformat() + "Z",
    "attachments": [{
        "hash": file_hash,
        "name": "attachment.pdf",
        "size": 1024,
        "mime": "application/pdf"
    }]
}
```

## Deduplication

The server automatically deduplicates messages by UUID. If you export the same conversation multiple times, duplicate messages will be ignored.

## Best Practices

1. **Use stable UUIDs**: Generate consistent UUIDs for messages so they can be updated without duplication
2. **Handle incremental exports**: Only send new messages since last export
3. **Include metadata**: Provide conversation title, participants, and timestamps
4. **Error handling**: Handle network errors gracefully and implement retries
5. **Progress logging**: Show progress for long exports

## Testing Your Exporter

1. Start the server: `talk-memory serve`
2. Run your exporter
3. Verify data: `talk-memory list`
4. Search: `talk-memory search "keyword"`
