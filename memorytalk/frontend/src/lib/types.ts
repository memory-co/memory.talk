import { localeTag, type Key, type Locale, type T } from './i18n';
import type { FileKind, Protocol } from './protocol';

export type WorkStatus = 'todo' | 'doing' | 'done' | 'abandoned';
export interface Work {
  id: string; goal: string; parent: string | null; status: WorkStatus;
  created_by: string | null; created_at: string; done_at: string | null; children?: Work[];
}
export interface Worklet {
  id: string; uri: string; scheme: string; cwd: string | null; alive: boolean;
  created_at: string; last_attached: string;
  window?: { url: string | null; embed: string | null } | null;
  handle?: { kind: string; capabilities: string[] } | null;
}
export interface Panel { worklet: string; collapsed: boolean }
export interface Column { id: string; panels: Panel[]; collapsed: boolean }
export interface Canvas { version: number; columns: Column[] }
export interface Round { id: string; timestamp: string | null; role: string; text: string }
export interface User {
  name: string; display_name: string; email: string; created_at: string; role: 'admin' | 'member';
  works_created: number; works_touched: number; commits: number;
}
export interface AuthStatus { setup_required: boolean; authenticated: boolean; user: User | null }
export interface LoginResult { token: string; user: User }
export interface Server { name: string; protocols: string[]; description: string }
export interface SystemInfo {
  home: string; metas: string; workspace: string; tmux_socket: string;
  tmuxd: { port: number; bind: string; url_host: string | null }; store: { family: string; backend: string };
}
export interface Layer {
  name: string; description: string; builtin: boolean; suffix: string | null;
  protocol: Protocol;
}
export interface TreeView {
  path: string; layer: string | null; items: TreeItem[];
  can_create: { objects: { layer: string; example: string; name: string; can: boolean; reason?: string }[]; files: (Partial<FileKind> & { layer?: string; can: boolean; reason?: string; existing?: string[] })[] };
  candidate?: { name: string; matches: unknown; exists?: boolean; can: boolean; reason?: string } | null;
}
export interface RecentItem { layer: string; path: string; title: string; files: string[]; sha: string; subject: string; author: string; date: string }
export interface RecentPage { items: RecentItem[]; next: string | null }
export interface TreeItem { name: string; path: string; kind: 'dir' | 'file' | 'object'; layer: string | null; object?: string | null; rel?: string | null }
export interface MetaObject {
  layer: string; path: string; title: string; files: Record<string, string>; content: string | null;
}
export interface Revision { sha: string; author: string; date: string; subject: string; body: string }
export interface SearchHit { kind: 'work' | 'meta' | 'user'; id: string; title: string; snippet: string; layer: string | null; file: string | null; line: number | null; status: string | null }
export interface SearchResult { query: string; hits: SearchHit[]; counts: Record<string, number> }
export interface InboxItem { ts: string; layer: string; path: string; subject: string; by: string | null }
export const workStatuses: WorkStatus[] = ['todo', 'doing', 'done', 'abandoned'];
export const statusLabel = (t: T, status: WorkStatus) => t(`status.${status}`);
export const layerLabel = (t: T, layer: string) => (['origin', 'issue', 'card', 'all'].includes(layer) ? t(`layer.${layer}` as Key) : layer);
const schemeNames: Record<string, string> = { codex: 'Codex', claude: 'Claude Code', kimi: 'Kimi' };
export const workletLabel = (t: T, scheme: string) => schemeNames[scheme] || (['bash', 'http', 'https'].includes(scheme) ? t(`scheme.${scheme}` as Key) : scheme);
export function flattenWorks(works: Work[]): Work[] {
  return works.flatMap(w => [w, ...flattenWorks(w.children || [])]);
}
export function dateLabel(value: string, locale: Locale = 'zh') {
  return new Date(value).toLocaleDateString(localeTag(locale), { month: 'short', day: 'numeric' });
}
