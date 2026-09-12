export type WorkStatus = 'todo' | 'doing' | 'done' | 'abandoned';
export interface Work {
  id: string; goal: string; parent: string | null; status: WorkStatus;
  created_by: string | null; created_at: string; done_at: string | null; children?: Work[];
}
export interface Session {
  id: string; uri: string; scheme: string; cwd: string | null; alive: boolean;
  created_at: string; last_attached: string;
  window?: { url: string | null; embed: string | null } | null;
  handle?: { kind: string; capabilities: string[] } | null;
}
export interface Round { id: string; timestamp: string | null; role: string; text: string }
export interface User {
  name: string; display_name: string; email: string;
  works_created: number; works_touched: number; commits: number;
}
export interface Server { name: string; protocols: string[]; description: string }
export interface SystemInfo {
  home: string; collections: string; workspace: string; tmux_socket: string;
  ttyd_url: string | null; store: { family: string; backend: string };
}
export interface Layer {
  name: string; description: string; builtin: boolean; suffix: string | null;
  files: string[]; schema: Record<string, unknown> | null;
}
export interface Catalog {
  dir: string; objects: { path: string; title: string | null }[]; subdirs: Catalog[];
}
export interface CollectionObject {
  layer: string; path: string; title: string; files: Record<string, string>; content: string | null;
}
export interface Revision { sha: string; author: string; date: string; subject: string; body: string }
export interface SearchHit { layer: string; path: string; file: string; line: number; text: string }
export interface InboxItem { ts: string; layer: string; path: string; subject: string; by: string | null }
export const statusLabels: Record<WorkStatus, string> = {
  todo: '待开始', doing: '进行中', done: '已完成', abandoned: '已放下',
};
export const layerLabels: Record<string, string> = { origin: '原文', issue: '问题', card: '卡片' };
export const sessionLabels: Record<string, string> = {
  codex: 'Codex', claude: 'Claude Code', kimi: 'Kimi', bash: '终端', http: '网页', https: '网页',
};
export function flattenWorks(works: Work[]): Work[] {
  return works.flatMap(w => [w, ...flattenWorks(w.children || [])]);
}
export function flattenCatalog(c: Catalog): { path: string; title: string | null }[] {
  return [...c.objects, ...c.subdirs.flatMap(flattenCatalog)];
}
export function dateLabel(value: string) {
  return new Date(value).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}
