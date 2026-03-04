# talk-memory

Extract and store conversation data from various chat platforms (ChatGPT, Gemini, Claude, DingTalk, Email, etc.) to a local directory. Data is stored in JSONL format with attachments stored separately, making it easy to manage with git.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Exporters                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ 浏览器插件 │ │ 脚本     │ │ 本地文件读取器   │ │
│  │ (ChatGPT │ │ (DingTalk│ │ (Claude Code     │ │
│  │  Gemini) │ │  Email)  │ │  本地 JSONL)     │ │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘ │
└───────┼────────────┼───────────────┼─────────────┘
        │            │               │
        │  POST /api/ingest          │
        ▼            ▼               ▼
┌─────────────────────────────────────────────────┐
│              talk-memory server                  │
│              localhost:7900                       │
│  ┌───────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ REST API  │ │ Web UI   │ │ 存储引擎        │  │
│  └───────────┘ └──────────┘ └────────────────┘  │
└─────────────────────────────────────────────────┘
        ▲
        │  HTTP
        │
┌───────┴──────┐
│  CLI 客户端   │
│  talk-memory │
└──────────────┘
```

## Quick Start

### Installation

**Python (recommended):**

```bash
# Install server and CLI
pip install -e ./server-py
pip install -e ./cli-py

# Or use the combined package
pip install talk-memory
```

**Node.js:**

```bash
# Install dependencies
cd server-node && npm install && npm run build
cd ../cli-node && npm install && npm run build
```

### Usage

```bash
# Start server
talk-memory serve                    # Default localhost:7900
talk-memory serve --port 8080       # Custom port

# Pull conversations
talk-memory pull chatgpt            # Trigger exporter for platform
talk-memory pull --all              # Run all exporters

# List and search
talk-memory list                    # List all conversations
talk-memory list chatgpt            # Filter by platform
talk-memory search "kubernetes"     # Full-text search

# Export
talk-memory export <session-id>     # Export as JSON
talk-memory export <session-id> --format md  # Export as Markdown
```

## Data Storage

All data is stored in `~/.talk-memory/`:

```
~/.talk-memory/
├── conversations/
│   └── <platform>/
│       └── <session-id>/
│           ├── meta.yaml          # Conversation metadata
│           └── messages.jsonl    # Message records
├── blobs/
│   └── <platform>/
│       └── <hash[0:2]>/
│           └── <hash[2:4]>/
│               └── <full-sha256>.<ext>
└── config.yaml
```

## Server API

### Push Conversation

```
POST /api/ingest
Content-Type: application/json
```

```json
{
  "platform": "chatgpt",
  "session_id": "abc-123",
  "messages": [
    {
      "uuid": "msg-001",
      "role": "user",
      "content": "Hello",
      "timestamp": "2024-01-01T00:00:00Z"
    }
  ],
  "metadata": {
    "title": "My Conversation",
    "participants": [
      {"name": "User", "role": "user"},
      {"name": "ChatGPT", "role": "assistant", "model": "gpt-4o"}
    ]
  }
}
```

### Push Attachment

```
POST /api/ingest/blob
Content-Type: multipart/form-data

platform=chatgpt&file=@attachment.pdf
```

### List Conversations

```
GET /api/conversations
GET /api/conversations?platform=chatgpt
```

### Get Conversation

```
GET /api/conversations/<platform>/<session_id>
```

### Search

```
GET /api/search?q=kubernetes
```

## Web UI

Open `web/index.html` in a browser to use the graphical interface.

## License

MIT
