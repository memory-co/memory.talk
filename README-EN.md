# memory.talk

> Persistent cross-session memory for AI agents.

memory.talk turns your past conversations with Claude Code, Codex, and other AI platforms into **searchable cognition cards** (Talk-Cards) so the next session can "remember" prior decisions, pitfalls hit, and architectural choices made. Local-first storage, zero-config to start, pluggable to Qdrant / PostgreSQL / etc.

[中文](README.md) · [CLI Docs](docs/cli/v2/README.md)

---

## What problem it solves

Every fresh AI session starts blank — you re-explain the project, walk down the same dead ends, re-make the same decisions. memory.talk turns that loop into:

1. **Sync** past sessions (`memory-talk sync`)
2. **Distill** them into cards (LLM does the cognition; `card` lands the data)
3. AI startup hook **auto-recalls** relevant memories (`recall`)
4. AI **actively retrieves** during reasoning (`search`)

Not yet another RAG library — memory.talk separates retrieval into **unconscious recall** (hook-stage auto-injection) and **conscious search** (intentional retrieval), two orthogonal semantics with different output shapes.

## Quick start

### Install

```bash
pip install memorytalk
```

Or from source:

```bash
git clone https://github.com/memory-co/memory.talk.git
cd memory.talk
pip install -e .
```

### Initialize

```bash
memory-talk setup
```

The interactive wizard asks for embedding provider (`local` / `openai`), port, vector backend, relation backend, etc., writes `~/.memory-talk/settings.json`, optionally starts the background server, and creates a `memory.talk` symlink (equivalent to `memory-talk`).

> setup is idempotent — run it again to reconfigure. Each prompt's default is the current value; press Enter to keep, edit to change. If anything changes and the server is running, you'll be asked whether to restart.

### Use it

```bash
# Import past sessions from Claude Code / Codex
memory-talk sync

# Search
memory-talk search "LanceDB selection"

# View one card
memory-talk view card_01jz8k2m

# See the lifecycle events of a session
memory-talk log sess_xxx
```

Full command list → [docs/cli/v2/](docs/cli/v2/README.md)

---

## Core concepts

### Talk-Card

A compressed cognition unit (≤1024 tokens), distilled by an LLM from specific rounds of a session:

- **Summary** — one sentence, the embedding anchor
- **Rounds** — key decision / reasoning excerpts
- **Links** — semantic relations to other cards / sessions
- **Default Link** — each card auto-links back to its source session; lives and dies with the card

> Cards are "already-thought-through ideas". Sessions are "raw conversations".

### Search vs Recall

| | `search` | `recall` |
|---|---|---|
| Trigger | AI calls during reasoning | harness hook auto-calls |
| Mode | Conscious / decided to look | Unconscious / surfaces on prompt |
| Output | Full structure (snippets / links / tags) | Minimal (`memory-talk view <id>  # summary`) |
| Dedup | None | Same session won't re-recall a card |

Both ride the same **hybrid FTS + vector** layer (LanceDB underneath).

### Storage layout

```
~/.memory-talk/
├── settings.json
├── sessions/<source>/<bucket>/<sess_id>/
│   ├── meta.json
│   ├── rounds.jsonl              # conversation stream (append-only)
│   └── events.jsonl              # lifecycle events
├── cards/<bucket>/<card_id>/
│   ├── card.json
│   └── events.jsonl
├── links/<bucket>/<link_id>.json
├── vectors/                       # LanceDB
├── memory.db                      # SQLite (derived index)
└── logs/search/<UTC-day>.jsonl
```

**Files are the source of truth.** SQLite + LanceDB are derived indices, fully reconstructible from the on-disk JSONL/JSON tree. Run `memory-talk rebuild` anytime to regenerate everything from files.

---

## Output formatting

The CLI defaults to **Markdown**, switching its rendering by stdout:

- TTY terminal → rendered with `rich` (styled headings, tables, code blocks)
- Pipe / script / LLM consumer → raw Markdown (Markdown is native to LLM training data)
- `--json` → structured JSON for machine consumers

Errors follow the same contract: Markdown mode writes `**error:** <msg>` to stderr; JSON mode writes `{"error": ...}` to stdout. Both exit 1.

---

## Design principles

- **Python never calls an LLM.** The data layer is pure CRUD / embedding / vector search. Cognition (summarization, link inference, card composition) happens in an LLM that calls into this CLI from outside.
- **Pluggable storage abstraction.** `provider/storage.py` exposes primitives (`write_text` / `read_text` / `append_text` / `list_subkeys` / etc.); local-fs is the current implementation. Domain ops (`write_session_meta`, `append_rounds`, ...) live in `repository/<domain>.py` and only ever speak to the primitive layer — swapping to S3 is one new class.
- **Rebuild always works.** Delete `memory.db` and `vectors/`, run `memory-talk rebuild`, and everything reconstitutes from the file tree.
- **Rebuild flips the server into maintenance mode.** While rebuilding, every API except `GET /v2/status` returns 503 to keep callers from reading torn intermediate state.

---

## Command reference

| Command | Purpose |
|---|---|
| [`setup`](docs/cli/v2/setup.md) | Interactive install / reconfigure / restart |
| [`sync`](docs/cli/v2/sync.md) | Import sessions from Claude Code et al. |
| [`search`](docs/cli/v2/search.md) | Conscious retrieval (hybrid FTS + vector) |
| [`recall`](docs/cli/v2/recall.md) | Hook-stage automatic recall (minimal output) |
| [`view`](docs/cli/v2/view.md) | Read one card or session |
| [`log`](docs/cli/v2/log.md) | Lifecycle event stream of an object |
| [`card`](docs/cli/v2/card.md) | Create a card |
| [`tag`](docs/cli/v2/tag.md) | Tag a session |
| [`link`](docs/cli/v2/link.md) | Write a user link |
| [`server`](docs/cli/v2/server.md) | Manage the local API server |
| [`rebuild`](docs/cli/v2/rebuild.md) | Rebuild indices from file truth |

---

## Development

```bash
pip install -e ".[dev]"
pytest memorytalk/tests/
```

To run the search-quality regression suite (uses real DashScope embeddings):

```bash
export QWEN_KEY=sk-...
pytest memorytalk/tests/search/
```

Test layout:

```
memorytalk/tests/
├── api/            # FastAPI TestClient
├── cli/            # Real CLI invocations (ASGI-routed + subprocess server)
├── service/        # Service layer (real SQLite + LanceDB + dummy embedder)
├── provider/       # Storage / embedding primitives
├── config/         # Config load + validate
├── util/           # dsl / ids / snippet / ttl
└── search/         # Search-quality regression
                    # (5-tier scoring: Excellent / Acceptable / Marginal / Degraded / Failed)
```

184+ tests, organized as **per-scenario directories** — each test case lives in its own dir with a `README.md` (what it tests, why) plus `test.py`. See [tests/](memorytalk/tests/) for the full layout.

---

## License

[Apache License 2.0](LICENSE)
