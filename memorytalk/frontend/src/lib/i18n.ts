import { usePreferences, type Locale } from './store';

export type { Locale };
export const locales: { value: Locale; label: string }[] = [{ value: 'zh', label: '中文' }, { value: 'en', label: 'English' }];

const en = {
  'common.loading': 'Loading…', 'common.loadingBody': 'Loading content…', 'common.loadFailed': 'Failed to load. Please try again.', 'common.reload': 'Reload',
  'common.cancel': 'Cancel', 'common.save': 'Save', 'common.collapse': 'Collapse', 'common.expand': 'Expand', 'common.closeDialog': 'Close dialog',
  'api.unreachable': 'Cannot reach the server. Make sure the memory.talk backend is running.', 'api.failed': 'Request failed ({status})', 'api.badResponse': 'The server returned an unrecognized response.', 'api.separator': '; ',
  'status.todo': 'To do', 'status.doing': 'In progress', 'status.done': 'Done', 'status.abandoned': 'Set aside',
  'layer.origin': 'Origin', 'layer.issue': 'Issue', 'layer.card': 'Card', 'layer.all': 'All',
  'scheme.bash': 'Terminal', 'scheme.http': 'Web', 'scheme.https': 'Web',
  'nav.home': 'Workbench', 'nav.meta': 'Meta cognition', 'nav.settings': 'Settings', 'nav.workspace': 'Workspace', 'nav.main': 'Main navigation',
  'nav.mainText': 'Switch works, browse meta cognition, or open settings.', 'nav.closeNav': 'Close navigation', 'nav.openNav': 'Open navigation', 'nav.toggleSidebar': 'Toggle sidebar', 'nav.homeLink': 'memory.talk home', 'nav.newWork': 'New work', 'nav.yourWorks': 'Your works',
  'nav.noWorks': 'No works yet', 'nav.noWorksHint': 'Start from an idea.', 'nav.connected': 'Workspace connected', 'nav.disconnected': 'Workspace disconnected', 'nav.connecting': 'Connecting to workspace',
  'nav.teamWorkspace': 'Team workspace',
  'nav.openInspector': 'Open meta cognition panel', 'nav.closeInspector': 'Hide meta cognition panel', 'nav.inspector': 'Meta cognition panel', 'nav.closeInspectorPanel': 'Close meta cognition panel',
  'search.title': 'Search', 'search.description': 'Search works, meta cognition and members; use the arrow keys to select and press Enter to open.', 'search.placeholder': 'Search works, meta cognition, members…', 'search.inputLabel': 'Search',
  'search.loading': 'Searching…', 'search.empty': 'Nothing found.', 'search.hint': 'Type to search everything.', 'search.works': 'Works', 'search.metas': 'Meta cognition', 'search.users': 'Members', 'search.button': 'Search',
  'home.workCreated': 'Work created', 'home.subworkCreated': 'Sub-work created', 'home.goalLabel': 'Work goal', 'home.workPlaceholder': 'Describe what you want to get done…', 'home.subworkPlaceholder': 'What does this step accomplish?',
  'home.startHint': 'Start from a goal', 'home.splitHint': 'Split into a sub-work', 'home.create': 'Create work', 'home.subworkTitle': 'Split off a step and keep going', 'home.subworkDescription': 'The sub-work stays under the current work and has its own sessions.', 'home.greeting': 'What do you want to do today?', 'home.greetingNamed': '{name}, what do you want to do today?', 'home.description': 'Let the work happen, and let the knowledge stay.',
  'home.hintEnter': 'Enter to create', 'home.hintShift': 'Shift + Enter for a new line', 'home.fromMeta': 'Start from meta cognition',
  'home.recent': 'Continue recent work', 'home.emptyTitle': 'Leave a starting point for your future self',
  'home.emptyText': 'Once you create your first work, you can always continue from here.',
  'work.statusLabel': 'Work status', 'work.split': 'Split work', 'work.sessions': 'Work sessions', 'work.addSession': 'Add session', 'work.column': 'Column {n}', 'work.addColumn': 'Add column', 'work.removeColumn': 'Remove this empty column', 'work.collapseColumn': 'Collapse column', 'work.expandColumn': 'Expand column',
  'work.collapse': 'Collapse', 'work.expand': 'Expand', 'work.moveLeft': 'Move to the left column', 'work.moveRight': 'Move to the right column', 'work.moveUp': 'Move up', 'work.moveDown': 'Move down', 'work.emptyColumn': 'No sessions in this column', 'work.layoutConflict': 'Layout changed elsewhere; reloaded.',
  'work.endedTitle': 'This work has ended', 'work.readyTitle': 'Ready to start this work', 'work.endedText': 'You can still browse related knowledge, or reopen the work.',
  'work.readyText': 'Add an agent, a terminal, or a web page to get the ideas moving.', 'work.viewMeta': 'Open meta cognition',
  'attach.added': 'Session added', 'attach.title': 'Add a session', 'attach.description': 'One work can hold several sessions; switching pages does not end them.', 'attach.type': 'Session type',
  'attach.custom': 'Custom URI', 'attach.webUrl': 'Web address', 'attach.cwd': 'Working directory (optional)', 'attach.cwdPlaceholder': 'Leave empty to use the default workspace',
  'attach.hintWeb': 'Enter an address starting with http:// or https://.', 'attach.hintCustom': 'Enter a full URI with a scheme.', 'attach.hintCwd': 'The working directory must be an absolute path starting with /.',
  'attach.opening': 'Opening session…', 'attach.open': 'Open session',
  'session.alive': 'Running', 'session.dead': 'Not running', 'session.closed': 'Session closed', 'session.clipboardFailed': 'Clipboard unavailable. Please copy the session address manually.', 'session.current': 'Current session',
  'session.view': 'Session view', 'session.terminal': 'Terminal', 'session.transcript': 'Transcript', 'session.copy': 'Copy session address', 'session.openWindow': 'Open in new window', 'session.remove': 'End and remove session',
  'session.transcriptEnded': 'Work ended · transcript', 'session.transcriptLive': 'Transcript updates automatically · talk to the agent in the terminal', 'session.you': 'You', 'session.tool': 'Tool', 'session.toolOutput': 'Show tool output',
  'session.noTranscript': 'No transcript yet', 'session.noTranscriptText': 'Once you start talking in the terminal, the transcript shows up here.', 'session.endedTitle': 'Session has ended', 'session.endedText': 'The work is archived and the terminal is no longer running.',
  'session.notRunning': 'This session is not running', 'session.reconnectText': 'Reconnect to continue the current work.', 'session.reconnect': 'Reconnect', 'session.embedNote': 'If the page refuses to be embedded, open it in a new window from the top right.',
  'session.iframeTitle': '{scheme} session', 'session.snapshot': 'Terminal snapshot · read only', 'session.refreshSnapshot': 'Refresh terminal snapshot', 'session.waiting': 'Terminal is running, waiting for output…',
  'session.ttydTitle': 'Connect a browser terminal to work right here', 'session.ttydText': 'You can view output now. Configure ttyd to type and interact on the page.', 'session.ttydHow': 'How to connect',
  'session.confirmTitle': 'End this session?', 'session.confirmText': 'This stops the session process and removes its registration. To switch works, just pick another work; there is no need to close the session.', 'session.keep': 'Keep session', 'session.ending': 'Ending…', 'session.end': 'End session',
  'settings.subtitle': 'Your account, the team, and the environment.', 'settings.profile': 'Profile', 'settings.profileSaved': 'Profile saved', 'settings.members': 'Team members', 'settings.membersText': 'Everyone who can sign in. Ask the admin to add accounts or reset passwords.', 'settings.membersTextAdmin': 'Everyone who can sign in. You can add accounts and set passwords.',
  'settings.addMember': 'Add member', 'settings.addMemberText': 'Creates an account they can sign in with. Anyone signed in can take part in any work.', 'settings.add': 'Add', 'settings.language': 'Language', 'settings.languageText': 'Interface language, saved in this browser.',
  'auth.setupTitle': 'Set up memory.talk', 'auth.setupText': 'No admin account yet. Set a password for admin to get started.', 'auth.setupSubmit': 'Create admin and sign in', 'auth.loginTitle': 'Sign in', 'auth.loginText': 'Use the account the admin gave you.', 'auth.loginSubmit': 'Sign in',
  'auth.password': 'Password', 'auth.passwordHint': 'At least 6 characters.', 'auth.confirmPassword': 'Confirm password', 'auth.mismatch': 'Passwords do not match.', 'auth.logout': 'Sign out', 'auth.roleAdmin': 'Admin', 'auth.roleMember': 'Member',
  'auth.changePassword': 'Change password', 'auth.oldPassword': 'Current password', 'auth.newPassword': 'New password', 'auth.passwordChangedRelogin': 'Password changed. Sign in again.', 'auth.setPassword': 'Set password', 'auth.setPasswordFor': 'Set password for {name}', 'auth.setPasswordText': 'Their current sessions are signed out; they sign in with the new password.', 'auth.passwordSet': 'Password set for {name}',
  'auth.initialPassword': 'Initial password', 'auth.initialPasswordHint': 'Leave empty to set it later; they cannot sign in until then.',
  'settings.environment': 'Environment', 'settings.serviceStatus': 'Service', 'settings.connected': 'Connected', 'settings.workspace': 'Default workspace', 'settings.home': 'Data directory', 'settings.store': 'Storage',
  'settings.ttyd': 'Browser terminal', 'settings.notConfigured': 'Not configured', 'settings.ttydText': 'Sessions run in tmux on the server. With ttyd configured you can type and interact on the page; without it you can still view terminal snapshots and agent transcripts.',
  'settings.ttydTitle': 'Connect an existing ttyd service', 'settings.ttydHow': 'Have ttyd attach to the same tmux socket using the session argument, and set a browser-reachable address before starting memory.talk:', 'settings.ttydExample': 'https://your-terminal-service',
  'settings.ttydArg': 'The window address carries', 'settings.ttydSocket': '. Current tmux socket: ', 'settings.ttydRestart': '. Restart the backend after changing it.',
  'settings.added': 'Member added', 'settings.username': 'Username', 'settings.usernameHint': 'Letters, digits, underscore, dot and hyphen.', 'settings.displayName': 'Display name',
  'settings.displayNamePlaceholder': 'How should we call you', 'settings.email': 'Email (optional)',
  'editor.edit': 'Edit', 'meta.newObject': 'New…', 'editor.fields': 'Properties', 'editor.body': 'Content', 'editor.addFile': 'New {label}', 'editor.add': 'Add', 'editor.remove': 'Remove', 'editor.deleteFile': 'Delete file',
  'editor.checking': 'Checking…', 'editor.valid': 'Looks good', 'editor.pathFor': 'Path (the last segment is the {name})', 'editor.subject': 'Commit subject (optional)', 'editor.subjectPlaceholder': 'e.g. position …: …',
  'editor.refPlaceholder': 'Path of a {layer}', 'editor.origin': 'Content', 'meta.unranked': 'Unranked',
  'meta.view': 'View', 'meta.viewRecent': 'Recent', 'meta.viewTree': 'Files', 'meta.loadMore': 'Load more', 'meta.up': 'Up', 'meta.emptyDir': 'Empty directory',
  'meta.subtitle': 'Sources, questions and conclusions from your work, gradually connected.', 'meta.layers': 'Layers', 'meta.new': 'New {layer}', 'meta.root': 'root', 'meta.empty': 'No {layer} yet', 'meta.emptyText': 'Start from a source, a question, or a conclusion.', 'meta.createFirst': 'Create the first one',
  'meta.back': 'Back to catalog', 'meta.objectView': 'Object view', 'meta.tabContent': 'Content', 'meta.tabHistory': 'History', 'meta.invalidMeta': 'Metadata could not be parsed; showing the raw content.',
  'meta.revision': 'Revision {rev}', 'meta.backToCurrent': 'Back to current', 'meta.viewDiscussion': 'View the discussion of this card', 'meta.relatedCards': 'Related cards', 'meta.positions': 'Positions and arguments',
  'meta.saved': 'Saved', 'meta.created': 'Created', 'meta.deleted': 'Deleted', 'meta.newFile': 'New {layer} file', 'meta.untitled': 'Untitled', 'meta.fileName': 'File name', 'meta.noSuchFile': 'This file does not exist', 'meta.siblings': 'Other files in this object', 'meta.confirmDelete': 'Delete {path}?',
  'meta.pathLabel': 'Path', 'meta.pathPlaceholder': 'project/topic/name', 'meta.markdown': 'Markdown supported', 'meta.reason': 'Reason (optional)', 'meta.reasonPlaceholder': 'Why you are recording or changing this',
};
export type Key = keyof typeof en;

const zh: Record<Key, string> = {
  'common.loading': '正在加载…', 'common.loadingBody': '正在加载正文…', 'common.loadFailed': '加载失败，请稍后重试。', 'common.reload': '重新加载',
  'common.cancel': '取消', 'common.save': '保存', 'common.collapse': '收起', 'common.expand': '展开', 'common.closeDialog': '关闭对话框',
  'api.unreachable': '无法连接服务，请确认 memory.talk 后端已启动。', 'api.failed': '请求失败（{status}）', 'api.badResponse': '服务返回了无法识别的响应。', 'api.separator': '；',
  'status.todo': '待开始', 'status.doing': '进行中', 'status.done': '已完成', 'status.abandoned': '已放下',
  'layer.origin': '原文', 'layer.issue': '问题', 'layer.card': '卡片', 'layer.all': '全部',
  'scheme.bash': '终端', 'scheme.http': '网页', 'scheme.https': '网页',
  'nav.home': '工作台', 'nav.meta': '元认知', 'nav.settings': '设置', 'nav.workspace': '工作空间', 'nav.main': '主导航',
  'nav.mainText': '切换工作、浏览元认知或打开设置。', 'nav.closeNav': '收起导航', 'nav.openNav': '打开导航', 'nav.toggleSidebar': '切换侧栏', 'nav.homeLink': 'memory.talk 首页', 'nav.newWork': '新建工作', 'nav.yourWorks': '你的工作',
  'nav.noWorks': '还没有工作', 'nav.noWorksHint': '从一个想法开始。', 'nav.connected': '工作空间已连接', 'nav.disconnected': '工作空间未连接', 'nav.connecting': '正在连接工作空间',
  'nav.teamWorkspace': '团队工作空间',
  'nav.openInspector': '打开元认知面板', 'nav.closeInspector': '收起元认知面板', 'nav.inspector': '元认知面板', 'nav.closeInspectorPanel': '关闭元认知面板',
  'search.title': '搜索', 'search.description': '搜索工作、元认知和成员；使用上下方向键选择，按 Enter 打开。', 'search.placeholder': '搜索工作、元认知、成员…', 'search.inputLabel': '搜索',
  'search.loading': '正在搜索…', 'search.empty': '没有找到。', 'search.hint': '输入关键词，搜索全部。', 'search.works': '工作', 'search.metas': '元认知', 'search.users': '成员', 'search.button': '搜索',
  'home.workCreated': '工作已创建', 'home.subworkCreated': '子工作已创建', 'home.goalLabel': '工作目标', 'home.workPlaceholder': '描述你想完成的事…', 'home.subworkPlaceholder': '这一步要完成什么？',
  'home.startHint': '从一个目标开始', 'home.splitHint': '拆分为子工作', 'home.create': '创建工作', 'home.subworkTitle': '拆分一步，继续推进', 'home.subworkDescription': '子工作会保留在当前工作下，拥有独立的会话。', 'home.greeting': '今天想做些什么？', 'home.greetingNamed': '{name}，今天想做些什么？', 'home.description': '让工作发生，让认知留下。',
  'home.hintEnter': 'Enter 创建工作', 'home.hintShift': 'Shift + Enter 换行', 'home.fromMeta': '从元认知出发',
  'home.recent': '继续最近的工作', 'home.emptyTitle': '留一个起点给未来的自己',
  'home.emptyText': '创建第一项工作后，你可以随时从这里继续。',
  'work.statusLabel': '工作状态', 'work.split': '拆分工作', 'work.sessions': '工作会话', 'work.addSession': '添加会话', 'work.column': '第 {n} 列', 'work.addColumn': '添加一列', 'work.removeColumn': '删掉这一空列', 'work.collapseColumn': '收起这一列', 'work.expandColumn': '展开这一列',
  'work.collapse': '收起', 'work.expand': '展开', 'work.moveLeft': '挪到左边一列', 'work.moveRight': '挪到右边一列', 'work.moveUp': '上移', 'work.moveDown': '下移', 'work.emptyColumn': '这一列还没有会话', 'work.layoutConflict': '布局在别处改过了，已重新载入。',
  'work.endedTitle': '这项工作已结束', 'work.readyTitle': '准备好，开始这项工作', 'work.endedText': '你仍可以查阅相关认知，或重新开启工作。',
  'work.readyText': '添加一个 agent、终端或网页，让思路开始落地。', 'work.viewMeta': '查看元认知',
  'attach.added': '会话已添加', 'attach.title': '添加一个会话', 'attach.description': '同一个工作可以容纳多个现场，切换页面不会结束会话。', 'attach.type': '会话类型',
  'attach.custom': '自定义 URI', 'attach.webUrl': '网页地址', 'attach.cwd': '工作目录（可选）', 'attach.cwdPlaceholder': '留空使用默认工作目录',
  'attach.hintWeb': '请输入以 http:// 或 https:// 开头的地址。', 'attach.hintCustom': '请输入带协议的完整 URI。', 'attach.hintCwd': '工作目录需要使用以 / 开头的绝对路径。',
  'attach.opening': '正在建立会话…', 'attach.open': '打开会话',
  'session.alive': '运行中', 'session.dead': '未运行', 'session.closed': '会话已关闭', 'session.clipboardFailed': '无法访问剪贴板，请手动复制会话地址。', 'session.current': '当前会话',
  'session.view': '会话视图', 'session.terminal': '终端', 'session.transcript': '对话记录', 'session.copy': '复制会话地址', 'session.openWindow': '在新窗口打开', 'session.remove': '结束并移除会话',
  'session.transcriptEnded': '工作已结束 · 会话记录', 'session.transcriptLive': '会话记录自动更新 · 请在终端中与 agent 交互', 'session.you': '你', 'session.tool': '工具', 'session.toolOutput': '查看工具输出',
  'session.noTranscript': '还没有对话记录', 'session.noTranscriptText': '在终端中开始对话后，记录会显示在这里。', 'session.endedTitle': '现场已结束', 'session.endedText': '工作已归档，终端不再运行。',
  'session.notRunning': '这个会话暂未运行', 'session.reconnectText': '重新连接，继续当前工作。', 'session.reconnect': '重新连接', 'session.embedNote': '若网页不允许嵌入，可在右上角的新窗口中打开。',
  'session.iframeTitle': '{scheme} 会话', 'session.snapshot': '终端快照 · 只读', 'session.refreshSnapshot': '刷新终端快照', 'session.waiting': '终端正在运行，等待输出…',
  'session.ttydTitle': '连接浏览器终端，直接在这里操作', 'session.ttydText': '当前可以查看输出。配置 ttyd 后，即可在页面中输入和操作。', 'session.ttydHow': '查看接入方式',
  'session.confirmTitle': '结束这个会话？', 'session.confirmText': '这会停止会话进程并移除登记。只想切换工作时，直接选择其他工作即可，无需关闭会话。', 'session.keep': '保留会话', 'session.ending': '正在结束…', 'session.end': '结束会话',
  'settings.subtitle': '你的账号、团队和工作环境。', 'settings.profile': '个人资料', 'settings.profileSaved': '资料已保存', 'settings.members': '团队成员', 'settings.membersText': '能登录的所有人。要加账号或重置密码，找管理员。', 'settings.membersTextAdmin': '能登录的所有人。你可以添加账号、给人设密码。',
  'settings.addMember': '添加成员', 'settings.addMemberText': '建一个能登录的账号。登录后的每个人都能参与任何工作。', 'settings.add': '添加', 'settings.language': '语言', 'settings.languageText': '界面语言，保存在这台浏览器上。',
  'auth.setupTitle': '初始化 memory.talk', 'auth.setupText': '还没有管理员账号。给 admin 设一个密码就可以开始。', 'auth.setupSubmit': '创建 admin 并登录', 'auth.loginTitle': '登录', 'auth.loginText': '用管理员给你的账号登录。', 'auth.loginSubmit': '登录',
  'auth.password': '密码', 'auth.passwordHint': '至少 6 位。', 'auth.confirmPassword': '确认密码', 'auth.mismatch': '两次输入的密码不一致。', 'auth.logout': '退出登录', 'auth.roleAdmin': '管理员', 'auth.roleMember': '成员',
  'auth.changePassword': '修改密码', 'auth.oldPassword': '当前密码', 'auth.newPassword': '新密码', 'auth.passwordChangedRelogin': '密码已修改，请重新登录。', 'auth.setPassword': '设置密码', 'auth.setPasswordFor': '给 {name} 设置密码', 'auth.setPasswordText': '对方当前的登录态会作废，用新密码重新登录。', 'auth.passwordSet': '已给 {name} 设置密码',
  'auth.initialPassword': '初始密码', 'auth.initialPasswordHint': '留空则之后再设；设好之前不能登录。',
  'settings.environment': '工作环境', 'settings.serviceStatus': '服务状态', 'settings.connected': '已连接', 'settings.workspace': '默认工作目录', 'settings.home': '数据目录', 'settings.store': '存储方式',
  'settings.ttyd': '浏览器终端', 'settings.notConfigured': '尚未配置', 'settings.ttydText': '会话运行在服务端的 tmux 中。配置 ttyd 后，就能在页面里直接输入与操作；未配置时仍可查看终端快照和 agent 会话记录。',
  'settings.ttydTitle': '接入现有 ttyd 服务', 'settings.ttydHow': '让 ttyd 按会话参数连接同一个 tmux socket，并在启动 memory.talk 前设置浏览器可访问的地址：', 'settings.ttydExample': 'https://你的终端服务地址',
  'settings.ttydArg': '窗口地址会携带', 'settings.ttydSocket': '。当前 tmux socket：', 'settings.ttydRestart': '。修改配置后需要重启后端。',
  'settings.added': '成员已添加', 'settings.username': '用户名', 'settings.usernameHint': '支持英文字母、数字、下划线、点和连字符。', 'settings.displayName': '显示名称',
  'settings.displayNamePlaceholder': '如何称呼你', 'settings.email': '邮箱（可选）',
  'editor.edit': '编辑', 'meta.newObject': '新建…', 'editor.fields': '属性', 'editor.body': '正文', 'editor.addFile': '新建{label}', 'editor.add': '添加', 'editor.remove': '移除', 'editor.deleteFile': '删除文件',
  'editor.checking': '校验中…', 'editor.valid': '通过校验', 'editor.pathFor': '路径（最后一段是{name}）', 'editor.subject': '提交主题（可选）', 'editor.subjectPlaceholder': '例如 position …: …',
  'editor.refPlaceholder': '某个{layer}的路径', 'editor.origin': '原文', 'meta.unranked': '未判定',
  'meta.view': '视图', 'meta.viewRecent': '最近修改', 'meta.viewTree': '文件目录', 'meta.loadMore': '更多', 'meta.up': '上一级', 'meta.emptyDir': '空目录',
  'meta.subtitle': '工作中的原文、问题与结论，在这里逐渐连接。', 'meta.layers': '认知层', 'meta.new': '新建{layer}', 'meta.root': '根目录', 'meta.empty': '还没有{layer}', 'meta.emptyText': '从一份原文、一个问题或一条结论开始。', 'meta.createFirst': '创建第一条内容',
  'meta.back': '返回目录', 'meta.objectView': '对象视图', 'meta.tabContent': '内容', 'meta.tabHistory': '历史', 'meta.invalidMeta': '元数据无法解析，当前显示原始正文。',
  'meta.revision': '历史版本 {rev}', 'meta.backToCurrent': '回到当前版本', 'meta.viewDiscussion': '查看这张卡片的讨论', 'meta.relatedCards': '相关卡片', 'meta.positions': '立场与论证',
  'meta.saved': '内容已保存', 'meta.created': '内容已创建', 'meta.deleted': '已删除', 'meta.newFile': '新建{layer}文件', 'meta.untitled': '未命名', 'meta.fileName': '文件名', 'meta.noSuchFile': '这个文件不存在', 'meta.siblings': '同一对象里的其他文件', 'meta.confirmDelete': '删除 {path}？',
  'meta.pathLabel': '保存路径', 'meta.pathPlaceholder': '项目/主题/名称', 'meta.markdown': '支持 Markdown', 'meta.reason': '修改说明（可选）', 'meta.reasonPlaceholder': '为什么记录或修改这条内容',
};

const dictionaries: Record<Locale, Record<Key, string>> = { zh, en };

export function translate(locale: Locale, key: Key, vars?: Record<string, string | number>): string {
  let text = dictionaries[locale][key] ?? en[key] ?? key;
  for (const [name, value] of Object.entries(vars || {})) text = text.split(`{${name}}`).join(String(value));
  return text;
}
export type T = (key: Key, vars?: Record<string, string | number>) => string;

/** 组件里用:随语言切换重渲染。 */
export function useT(): T {
  const locale = usePreferences(s => s.locale);
  return (key, vars) => translate(locale, key, vars);
}
/** 非组件(api.ts 等)用。 */
export const t: T = (key, vars) => translate(usePreferences.getState().locale, key, vars);

export const localeTag = (locale: Locale) => (locale === 'zh' ? 'zh-CN' : 'en-US');
