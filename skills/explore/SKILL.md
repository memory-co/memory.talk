---
name: explore
description: Use when importing conversation history from Claude Code, Codex, or other platforms
---

# Explore

Discover and import raw conversations from AI platforms.

## Steps

1. **Scan** for new sessions:
   ```
   memory-talk explore scan --source claude-code
   ```
   Returns only sessions not yet imported (automatic dedup).

2. **Review** the list. Decide which sessions to import — all of them, or a subset.

3. **Import** each session:
   ```
   memory-talk explore ingest <session_path>
   ```

4. After importing, suggest running `/build` to organize the raw sessions into Talk-Cards.

## Supported Sources

- `claude-code` — Reads `~/.claude/projects/` JSONL files
- More adapters coming (Codex, OpenClaw)
