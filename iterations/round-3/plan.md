# Round 3 计划

## 目标
1. 更新 stories/claude_code_import.md 中的字段（session_id → conversation_id），并同步更新集成测试代码
2. 集成测试使用 connector 中的 export_sessions.py 脚本导入数据
3. Subject 增加 match 和 priority 字段，导入时使用 jinja2 表达式匹配

---

## 任务 1：更新 stories/claude_code_import.md

### 1.1 字段名称更新
- `session_id` → `conversation_id`
- API 路径更新：`/api/ingest` → `/api/v1/ingest`

### 1.2 同步更新集成测试
- 修改 `tests/integration/test_claude_code_import.py` 中的 API 路径
- 修改 session_id 相关字段名为 conversation_id

---

## 任务 2：集成测试使用 connector 脚本导入

### 2.1 创建测试用 mock 数据
- 使用 tempfile 创建临时 Claude Code 会话文件
- 调用 export_sessions.py 的解析逻辑生成测试数据
- 通过 HTTP API 导入

### 2.2 或者直接使用 export_sessions.py
- 创建测试用会话 JSONL 文件到临时目录
- 运行 export_sessions.py 导入数据

---

## 任务 3：Subject 增加 match 和 priority 字段

### 3.1 模型更新

**models/subject.py**
```python
class Subject(BaseModel):
    id: str
    name: str
    match: Optional[str] = None      # jinja2 表达式
    priority: Optional[int] = 0       # 优先级，数字越大越优先
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**storage/repository/domain/subject.py**
```python
@dataclass
class SubjectDO:
    id: str
    name: str
    match: Optional[str] = None
    priority: int = 0
    metadata: dict
    created_at: datetime
    updated_at: datetime
```

### 3.2 数据库迁移
- subjects 表增加 `match` VARCHAR 列
- subjects 表增加 `priority` INTEGER 列（默认 0）

### 3.3 导入时匹配逻辑

修改 `memory_talk/api/ingest.py`:

1. 导入时根据 platform + role 匹配 subject
2. 优先级：priority 数值越大越优先匹配
3. jinja2 表达式可用变量：`platform`, `role`, `message.metadata`
4. 导入完成后不再动态判断（subject_id 已固化到消息中）

```python
def find_subject_by_match(platform: str, role: str, metadata: dict) -> Optional[str]:
    """Find subject by matching jinja2 expressions."""
    # 查询所有有 match 表达式的 subject
    subjects = storage.list_subjects_with_match()

    # 按 priority 降序排序
    for subject in sorted(subjects, key=lambda s: s.priority, reverse=True):
        if evaluate_match_expr(subject.match, platform, role, metadata):
            return subject.id

    return None
```

### 3.4 保留自动匹配逻辑
- 如果没有匹配的 subject，回退到现有的自动匹配逻辑

---

## 依赖
- jinja2 (已安装或需要安装)

---

## 验证
- 运行集成测试：`pytest tests/integration/test_claude_code_import.py -v`
- 单元测试：`pytest tests/unit/test_storage.py -v`
