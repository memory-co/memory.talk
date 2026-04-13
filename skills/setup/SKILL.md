---
name: setup
description: Use on first install or when user wants to configure memory.talk storage backends
---

# Setup

First-time environment configuration for memory.talk.

## Steps

1. Ask the user which backends they want (or accept defaults):
   - **Vector store**: LanceDB (default, local) / Qdrant / Milvus
   - **Relation store**: SQLite (default, local) / PostgreSQL / MySQL
   - **Embedding model**: local sentence-transformers (default) / OpenAI API

2. Run setup:
   ```
   memory-talk setup [--vector lancedb] [--relation sqlite] [--embedding local]
   ```

3. Verify:
   ```
   memory-talk status
   ```

Defaults are zero-config local: LanceDB + SQLite + sentence-transformers. Most users just run `memory-talk setup` with no flags.
