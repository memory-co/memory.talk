# Round 2 Implementation Plan

## Goals
1. DELETE /api/v1/conversations 能够用来清理会话，可以按照 platform 全部删除
2. storage.py 参考 java 的 repository 结构，引入DO来解决数据库映射的问题
3. Conversation 中的 session_id 变成 conversation_id
4. 解决 connectors/claude-code/export_sessions.py 的 API 404 错误

---

## Task 1: Add DELETE /api/v1/conversations

**Files to modify:**
- `memory_talk/storage.py` - add `delete_conversations` method
- `memory_talk/api/conversations.py` - add DELETE endpoint

**Changes:**
- Add `delete_conversations(platform: str, conversation_id: Optional[str] = None)` to Storage
  - If only platform provided: delete all conversations for that platform
  - If both platform and conversation_id: delete specific conversation
- Add DELETE endpoint `/api/v1/conversations`

---

## Task 2: introduce DO + Repository Pattern

**New directory structure:**
```
memory_talk/storage/
  __init__.py
  storage.py           # Main Storage class (keep, refactor to use repositories)
  repository/
    __init__.py
    domain/
      __init__.py
      conversation.py   # ConversationDO
      message.py        # MessageDO
      subject.py        # SubjectDO
    mapper/
      __init__.py
      conversation_mapper.py
      message_mapper.py
      subject_mapper.py
```

**Domain (DO) - Data Objects:**
```python
# memory_talk/storage/repository/domain/conversation.py
class ConversationDO:
    """Database entity for conversations table."""
    conversation_id: str
    platform: str
    title: str
    created_at: datetime
    updated_at: datetime
    participants: list  # JSON
    message_count: int
```

```python
# memory_talk/storage/repository/domain/message.py
class MessageDO:
    """Database entity for messages table."""
    uuid: str
    parent_uuid: Optional[str]
    platform: str
    conversation_id: str
    role: str
    subject_id: Optional[str]
    content: str
    timestamp: datetime
    attachments: list  # JSON
    metadata: dict      # JSON
```

```python
# memory_talk/storage/repository/domain/subject.py
class SubjectDO:
    """Database entity for subjects table."""
    id: str
    name: str
    metadata: dict     # JSON
    created_at: datetime
    updated_at: datetime
```

**Mapper functions:**
```python
# memory_talk/storage/repository/mapper/conversation_mapper.py
def row_to_conversation_do(row) -> ConversationDO: ...
def conversation_do_to_row(do: ConversationDO) -> dict: ...
```

**Storage class refactor:**
- Keep Storage class, but delegate to mapper functions for SQL→DO conversions
- Storage methods call mapper functions to transform database rows to DOs

---

## Task 3: Rename session_id → conversation_id

**Files to modify:**
- `memory_talk/models/conversation.py` - rename fields
- `memory_talk/models/message.py` - rename session_id field
- `memory_talk/storage.py` - rename in table schema and all methods
- `memory_talk/storage/repository/domain/*.py` - rename fields
- `memory_talk/storage/repository/mapper/*.py` - rename in SQL and mappings
- `memory_talk/api/conversations.py` - rename query parameters
- `memory_talk/api/search.py` - check and update if needed

**Changes:**

1. **Database Schema:**
   - `conversations` table: `session_id` → `conversation_id`
   - `messages` table: `session_id` → `conversation_id`

2. **Models:**
   - `ConversationSummary.session_id` → `conversation_id`
   - `ConversationMetadata.session_id` → `conversation_id`
   - `Message.session_id` → `conversation_id`

3. **Storage Methods:**
   - `save_conversation(..., session_id=...)` → `save_conversation(..., conversation_id=...)`
   - `list_conversations()` - update SQL
   - `get_conversation(...)` - update SQL
   - `get_messages(..., session_id=...)` → `get_messages(..., conversation_id=...)`
   - `search()` - update SQL

4. **API:**
   - Add endpoint: `/api/v1/conversations/{platform}/{conversation_id}` to get single conversation

---

## Task 4: Fix export_sessions.py API 404 Error

**Files to modify:**
- `connectors/claude-code/export_sessions.py`

**Changes:**
Update API URLs from `/api/` to `/api/v1/`:
- Line 120: `f"{API_URL}/api/ingest"` → `f"{API_URL}/api/v1/ingest"`
- Line 139: `f"{API_URL}/api/status"` → `f"{API_URL}/api/v1/status"`

---

## Verification
- Run unit tests
- Check that API endpoints work correctly
- Verify database migration (may need to handle existing data)
