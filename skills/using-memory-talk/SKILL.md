---
name: using-memory-talk
description: Use when starting any conversation - provides persistent cross-session memory via Talk-Cards
---

# memory.talk

You have persistent cross-session memory. Past conversations are stored as **Talk-Cards** — compact memory units (≤1024 token) with a cognition summary, compressed rounds, and links to related cards.

## CLI Quick Reference

All commands output JSON. Use `memory-talk` via Bash tool.

```
memory-talk setup                              # First-time: choose backends + init
memory-talk explore scan --source claude-code   # List new sessions to import
memory-talk explore ingest <session_path>       # Import a single session
memory-talk sessions list [--unbuilt]           # List sessions
memory-talk sessions read <session_id>          # Read session rounds
memory-talk sessions mark-built <session_id>    # Mark session as organized
memory-talk cards create '<json>'               # Create Talk-Card (auto-embeds)
memory-talk cards get <card_id>                 # Read a card
memory-talk cards list [--session-id <id>]      # List cards
memory-talk cards links <card_id>               # Get linked cards
memory-talk links create '<json>'               # Add link between existing cards
memory-talk recall "<query>" [--top-k N]        # Vector search for relevant cards
memory-talk raw read <session_id> [start] [end] # Read original rounds
memory-talk status                              # Storage stats
```

## When to Use

- **Session start**: Run `memory-talk recall` with a query about the current project/task to load relevant past context.
- **User references past work**: Use `/recall` to search for related memories.
- **User asks to import conversations**: Use `/explore` to discover and import.
- **After importing**: Use `/build` to organize raw sessions into Talk-Cards.
