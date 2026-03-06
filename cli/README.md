# talk-memory-cli

Command line tool for managing conversation data from various chat platforms.

## Installation

```bash
pip install -e .
```

## Usage

```bash
talk-memory serve                    # Start server (default localhost:7900)
talk-memory serve --port 8080       # Custom port

talk-memory pull chatgpt            # Trigger exporter for platform
talk-memory pull --all              # Run all configured exporters

talk-memory list                    # List all conversations
talk-memory list chatgpt            # Filter by platform

talk-memory search "keyword"        # Full-text search
talk-memory search "keyword" chatgpt # Search within platform

talk-memory export <session-id>     # Export conversation
talk-memory export <session-id> --format md  # Export as Markdown
```
