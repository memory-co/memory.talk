---
name: recall
description: Use when needing to recall past conversations, decisions, or context from previous sessions
---

# Recall

Three-level cascading retrieval. Start coarse, go deeper only if needed.

## Level 1: Vector Search

```
memory-talk recall "<query>" --top-k 5
```

Returns the most semantically relevant Talk-Cards. Each card has a cognition summary and compressed rounds. **Most queries stop here.**

Read the returned cards. If they provide enough context, use them directly.

## Level 2: Link Expansion

If the cards hint at related context you need but don't have:

```
memory-talk cards links <card_id>
```

Follow `temporal` links for what happened before/after. Follow `causal` links for premises or consequences. Follow `topical` links for parallel discussions on the same theme.

Read the linked cards. If they fill the gaps, stop here.

## Level 3: Raw Fallback

If you need exact wording, complete code snippets, or detailed error logs that were lost in compression:

```
memory-talk raw read <session_id> <round_start> <round_end>
```

This reads the original uncompressed conversation rounds. Use sparingly — it's verbose.

## Tips

- Formulate specific queries: "LanceDB vs ChromaDB decision" beats "database".
- When multiple cards are returned, synthesize across them rather than using just one.
- If recall returns nothing useful, the topic may not have been built yet — suggest `/explore` + `/build`.
