# memory.talk

Install into Claude Code / Codex, give your Agent persistent memory across sessions.

memory.talk is a **Skill** that lets AI agents remember past conversations. It stores memories as **Talk-Cards** — compact, searchable units with summaries, compressed context, and links to related memories.

## Install

```bash
# As a Claude Code plugin
claude plugin install memory-talk

# Or from source
pip install -e .
```

## How It Works

```
Setup → Explore → Build → Recall
         (CLI)    (LLM)   (CLI + LLM)
```

- **Setup**: Choose storage backends, initialize (`memory-talk setup`)
- **Explore**: Import conversations from Claude Code, Codex, etc. (`/explore`)
- **Build**: LLM organizes raw conversations into Talk-Cards (`/build`)
- **Recall**: Vector search + link expansion + raw fallback (`/recall`)

The Python CLI does mechanical data operations. The Skills tell the LLM how to think.

## Talk-Card

A memory unit (≤1024 tokens) with:

- **Cognition Summary** — one sentence, the embedding anchor
- **Compressed Rounds** — key decisions and reasoning, no filler
- **Raw Ref** — pointer to original conversation for full context
- **Card Links** — temporal, topical, causal connections to other cards

## Storage

```
~/.memory-talk/
├── config.yaml
├── sessions/{source}/{hash}/{session_id}.jsonl
├── cards/{hash}/{card_id}.json
└── data/
    ├── vectors/      # LanceDB
    └── relation.db   # SQLite
```

Default: LanceDB + SQLite, local, zero-config. Pluggable to Qdrant, PostgreSQL, etc.

## License

MIT
