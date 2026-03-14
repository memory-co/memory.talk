# 本轮目标

1. docs页面中 conversations / messages / search / subjects 分别加不同的tag，能够清晰展示.
2. 接口变成 /api/v1 使得接口有版本信息
3. 测试用例跑挂了。
```
TOTAL                                  690    463  32.90%
Coverage XML written to file coverage.xml
=========================== short test summary info ============================
FAILED tests/unit/test_storage.py::TestStorage::test_save_conversation - AttributeError: 'Storage' object has no attribute 'get_conversation'. Did you mean: 'list_conversations'?
FAILED tests/unit/test_storage.py::TestStorage::test_save_conversation_updates_metadata - AttributeError: 'Storage' object has no attribute 'get_conversation'. Did you mean: 'list_conversations'?
FAILED tests/unit/test_storage.py::TestStorage::test_save_conversation_deduplication - AttributeError: 'Storage' object has no attribute 'get_conversation'. Did you mean: 'list_conversations'?
FAILED tests/unit/test_storage.py::TestStorage::test_get_conversation - AttributeError: 'Storage' object has no attribute 'get_conversation'. Did you mean: 'list_conversations'?
FAILED tests/unit/test_storage.py::TestStorage::test_get_conversation_not_found - AttributeError: 'Storage' object has no attribute 'get_conversation'. Did you mean: 'list_conversations'?
ERROR tests/integration/test_claude_code_import.py::TestClaudeCodeImport::test_import_claude_code_conversation - AssertionError: Server failed to start
assert False
 +  where False = wait_for_server('http://localhost:18788/health', timeout=30)
ERROR tests/integration/test_claude_code_import.py::TestClaudeCodeImport::test_list_claude_code_conversations - AssertionError: Server failed to start
assert False
 +  where False = wait_for_server('http://localhost:18788/health', timeout=30)
ERROR tests/integration/test_claude_code_import.py::TestClaudeCodeImport::test_get_conversation_details - AssertionError: Server failed to start
assert False
 +  where False = wait_for_server('http://localhost:18788/health', timeout=30)
ERROR tests/integration/test_claude_code_import.py::TestClaudeCodeImport::test_subject_matching - AssertionError: Server failed to start
assert False
 +  where False = wait_for_server('http://localhost:18788/health', timeout=30)
ERROR tests/integration/test_claude_code_import.py::TestClaudeCodeImport::test_subject_creation - AssertionError: Server failed to start
assert False
 +  where False = wait_for_server('http://localhost:18788/health', timeout=30)
======== 5 failed, 27 passed, 13 skipped, 5 errors in 152.12s (0:02:32) ========
```


