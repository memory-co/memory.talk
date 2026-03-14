# Claude Code 对话导入

## 背景

小李是一个全栈工程师，每天用 Claude Code 写代码。他的编码对话散落在本地的 Claude Code 会话记录里，时间一长就很难回溯「上周那个 bug 我是怎么修的」「那段部署脚本 Claude 帮我写的，在哪段对话里」。

他听说 memory-talk 可以把这些对话统一存档、检索，决定试试看。

---

## 小李的第一次导入

小李今天用 Claude Code 完成了一个 Python 项目的 Web 服务器开发——他跟 Claude 来回聊了好几轮，从「帮我看看这个项目」到「写个 Flask 服务器」再到「加个路由」，中间 Claude 还读了几个文件、写了代码。下班前，他想把这段对话存到 memory-talk 里。

### 场景 1：导入对话

> 关联测试：`TestClaudeCodeImport.test_import_claude_code_conversation`

小李打开终端，运行导出命令。工具自动扫描他的项目目录，找到今天的会话记录，向 `POST /api/v1/ingest` 发送数据。请求里带着 `platform: "claude-code"` 标明来源、`conversation_id` 标识这次会话、`messages` 数组包含所有消息，以及 `metadata` 里的项目路径和标题。

终端显示导入成功，返回了 `conversation_id`。一条命令，几秒钟，今天的工作痕迹就存好了。

### 场景 2：在列表里找到它

> 关联测试：`TestClaudeCodeImport.test_list_claude_code_conversations`

小李打开 memory-talk 的界面，想确认刚才的导入确实成功了。他请求 `GET /api/v1/conversations`，对话列表里出现了刚刚那条记录，每条记录带着 `conversation_id` 和 `platform` 字段。他加上 `?platform=claude-code` 筛选，列表只剩来自 Claude Code 的对话。他又试着筛一个不存在的来源，结果如预期是空列表，没有报错。

能筛选就好——以后对话多了，不同来源混在一起也不怕。

### 场景 3：打开对话，回看完整过程

> 关联测试：`TestClaudeCodeImport.test_get_conversation_details`

小李从列表里点开了那段对话，请求 `GET /api/v1/messages?platform=claude-code&conversation_id=test-project-2025-01-15`。返回结果包含 `total`、`limit`、`offset` 和 `messages` 四个字段，支持分页。`messages` 里完整呈现了 8 条消息——他的三次提问、Claude 的三次回复、中间两次工具调用（读文件、写文件），一条不少。每条消息都有 `role` 和 `content`，最顶上就是他说的第一句话。

就像翻聊天记录一样，当时的上下文全都在。

### 场景 4：每条消息都标注了「谁说的」

> 关联测试：`TestClaudeCodeImport.test_subject_matching`

小李通过 `GET /api/v1/messages?platform=claude-code&conversation_id=test-project-2025-01-15` 查看消息时，注意到每条消息上都多了一个 `subject_id` 字段，标识这条消息的「发言者」是谁。他还可以用 `role`、`subject_id` 等参数做多维度筛选。规则很直觉：

- 他自己发的消息（`role: "user"`），`subject_id` 统一是 `human-default`
- Claude 的回复如果带了 `metadata.model`，`subject_id` 就是 `ai-{model}`——他能看出用的是哪个版本的 Claude
- 工具调用如果带了 `metadata.tool_name`，`subject_id` 就是 `tool-{tool_name}`——Read 和 Write 各有各的标识
- Claude 的回复如果既没有 model 也没有 tool_name，兜底为 `ai-assistant`，不会空着

不光知道谁说了什么，还知道是哪个模型、用了什么工具。回溯问题的时候太有用了。

### 场景 5：系统自动建好了参与者档案

> 关联测试：`TestClaudeCodeImport.test_subject_creation`

小李好奇地请求了 `GET /api/v1/subjects`，发现系统已经自动建好了所有参与者。返回的列表里每个 subject 都有 `id` 字段：`human-default` 代表他自己，`ai-assistant` 是通用 AI 角色，还有以 `ai-` 开头的具体模型记录，以及以 `tool-` 开头的工具参与者——Read 和 Write 各占一行。

这些都不需要他手动配置。他只是导入了一段对话，系统就自动把对话中出现的所有参与者识别出来，各自建好了档案。以后按角色筛选消息也方便。

---

## 延伸思考

小李完成了「导入→确认→回看→理解」的完整流程。用着用着，他可能还会想要：

- **批量导入**：一次性把过去一个月的对话全部导进来，而不是一条一条跑
- **去重处理**：同一段对话导入两次，系统应该识别出来，不要产生重复记录
- **跨项目检索**：在 A 项目的对话里提到了 B 项目的一个工具函数，能不能搜到？
- **对话摘要**：一段对话有 200 条消息，能不能自动生成一段摘要，不用从头翻？
- **团队共享**：同事也在用 Claude Code，能不能把大家的对话汇总到一个地方，做团队知识库？
- **时间线视图**：按时间轴看所有项目的编码活动，发现「那周改了好多东西」
