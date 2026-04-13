# memory.talk — Contributor Guidelines

## Architecture

memory.talk is a Skill (not a standalone service). Two layers:

- **Data layer (Python CLI)**: `memory-talk` commands do mechanical data operations — CRUD, embedding, vector search. No LLM calls.
- **Orchestration layer (Skills)**: SKILL.md files tell the Agent what to read, think about, and write back. Cognitive work is done by the LLM.

## Development

```bash
uv pip install -e ".[dev]"
pytest tests/ -v
```

## Rules

- Python code must NOT call any LLM API. All cognition happens in Skills.
- CLI commands output JSON to stdout.
- One command = one mechanical operation.
- Tests must not require network access (mock embedding models in tests).
