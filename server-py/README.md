# talk-memory-server

Local server for storing conversation data from various chat platforms.

## Installation

```bash
pip install -e .
```

## Usage

```bash
python -m talk_memory_server
# Or: talk-memory-server
```

## API

- `POST /api/ingest` - Push conversation data
- `POST /api/ingest/blob` - Push attachment
- `GET /api/conversations` - List all conversations
- `GET /api/conversations/<platform>/<session_id>` - Get specific conversation
- `GET /api/search?q=<query>` - Search conversations
