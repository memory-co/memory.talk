# Round 1 Implementation Plan

## Goals
1. Fix broken tests (add missing `get_conversation` method to Storage)
2. Add API versioning: change `/api/` to `/api/v1/`
3. Add tags to Swagger docs for conversations/messages/search/subjects

---

## Task 1: Fix Storage.get_conversation method

**Files to modify:**
- `memory_talk/storage.py`

**Changes:**
- Add `get_conversation(platform, session_id)` method to Storage class
- Should return tuple of (ConversationSummary, messages) or None if not found

---

## Task 2: API Versioning (/api/v1/)

**Files to modify:**
- `memory_talk/api/conversations.py` - routes: `/api/conversations`, `/api/messages`
- `memory_talk/api/search.py` - route: `/api/search`
- `memory_talk/api/subjects.py` - routes: `/api/subjects`
- `memory_talk/api/status.py` - route: `/api/status`
- `memory_talk/api/ingest.py` - routes: `/api/ingest`, `/api/ingest/blob`
- `memory_talk/api/sources.py` - route: `/api/sources`

**Changes:**
- Change all routes from `/api/...` to `/api/v1/...`

---

## Task 3: Add Tags to Swagger Docs

**Files to modify:**
Same files as Task 2, plus `memory_talk/api/__init__.py`

**Changes:**
Add `tags` parameter to each APIRouter:

| File | Tag |
|------|-----|
| conversations.py | "Conversations" |
| messages (conversations.py) | "Messages" |
| search.py | "Search" |
| subjects.py | "Subjects" |
| status.py | "Status" |
| ingest.py | "Ingest" |
| sources.py | "Sources" |

Example:
```python
# Before
router = APIRouter()

# After
router = APIRouter(tags=["Conversations"])
```

---

## Verification
- Run tests: `pytest tests/unit/test_storage.py`
- Start server and visit `/docs` to verify Swagger UI shows grouped tags
