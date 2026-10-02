import { localeTag, type Key, type Locale, type T } from './i18n';
import type { FileKind, Protocol } from './protocol';

export type WorkStatus = 'running' | 'archived';
export interface Work {
  id: string; goal: string; parent: string | null; status: WorkStatus;
  created_by: string | null; created_at: string; archived_at: string | null; children?: Work[];
  viewers: string[];                                                  // 现在谁在看(按名字排;心跳算出来的,docs/designs/v5/work-store.md)
}
export interface Worklet {
  id: string; uri: string; scheme: string; cwd: string | null; alive: boolean;
  created_at: string; last_attached: string;
  column: string | null; position: number | null; collapsed: boolean;   // 在哪一列(`c3`)、列里从上往下第几个(从 0 起);收起只管显示
  window?: { url: string | null; embed: string | null } | null;
  handle?: { kind: string; capabilities: string[] } | null;
}
/** 列(GET /works/{id}/columns,按 position 从左到右,从 0 起):固定编号的 id(`c3`)+ 别名,可收起。列只承载弱编排。 */
export interface Column { id: string; alias: string; collapsed: boolean; position: number }
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
/** 轨迹(GET /works/{id}/trace):OTLP/JSON 的 TracesData + LogsData(docs/designs/v5/work-trace.md §3)。id 是十六进制,时间和 intValue 是十进制字符串。 */
export interface AnyValue {
  stringValue?: string; intValue?: string; boolValue?: boolean; doubleValue?: number;
  arrayValue?: { values?: AnyValue[] }; kvlistValue?: { values?: KeyValue[] };
}
export interface KeyValue { key: string; value: AnyValue }
export interface TraceSpan {
  traceId: string; spanId: string; parentSpanId?: string; name: string; kind: number;
  startTimeUnixNano: string; endTimeUnixNano?: string;              // 没有终点 = 还开着(另带 memorytalk.open = true)
  attributes?: KeyValue[]; links?: { traceId: string; spanId: string; attributes?: KeyValue[] }[]; status?: { code?: number };
}
export interface TraceLogRecord {
  timeUnixNano: string; observedTimeUnixNano?: string; eventName: string; traceId?: string; spanId?: string; attributes?: KeyValue[];
  body?: AnyValue;                                                  // 正文(bodies=1 才带):agent 的消息、工具的参数和结果
}
export interface WorkTrace {
  traces: { resourceSpans?: { scopeSpans?: { spans?: TraceSpan[] }[] }[] };
  logs: { resourceLogs?: { scopeLogs?: { logRecords?: TraceLogRecord[] }[] }[] };
  seq?: string;                                                     // 读的这一刻最大的变更序号:下次 after=它 接着读
}
export const traceSpans = (trace: WorkTrace) => (trace.traces.resourceSpans ?? []).flatMap(r => r.scopeSpans ?? []).flatMap(s => s.spans ?? []);
export const traceRecords = (trace: WorkTrace) => (trace.logs.resourceLogs ?? []).flatMap(r => r.scopeLogs ?? []).flatMap(s => s.logRecords ?? []);
/** 哪些工作单元的 output 由节点推进 trace(对话在 trace 里);其余 agent 还走旧的 rounds。 */
export const pushedSchemes = ['claude'];
export interface InboxItem { ts: string; layer: string; path: string; subject: string; by: string | null }
export const workStatuses: WorkStatus[] = ['running', 'archived'];
export const statusLabel = (t: T, status: WorkStatus) => t(`status.${status}`);
export const layerLabel = (t: T, layer: string) => (['origin', 'issue', 'card', 'all'].includes(layer) ? t(`layer.${layer}` as Key) : layer);
const schemeNames: Record<string, string> = { codex: 'Codex', claude: 'Claude Code', kimi: 'Kimi' };
/** 列 = 固定编号 + 别名(work-events.md §3):起了别名就只显示别名,没起就是「列 3」(编号从 id 里取,不按位置数)。 */
export const columnNumber = (t: T, column: { id: string }) => t('work.column', { n: column.id.replace(/^c/, '') });
export const columnLabel = (t: T, column: { id: string; alias?: string | null }) => column.alias || columnNumber(t, column);
export const workletLabel = (t: T, scheme: string) => schemeNames[scheme] || (['bash', 'http', 'https'].includes(scheme) ? t(`scheme.${scheme}` as Key) : scheme);
/** 从 OTLP 属性里取一个标量:intValue 是十进制字符串,这里转成 number(不然 +1 会变成拼字符串);数组 / kvlist 这里用不到,不取。 */
export function attrValue(attributes: KeyValue[] | undefined, key: string): string | number | boolean | undefined {
  const v = attributes?.find(a => a.key === key)?.value;
  if (!v) return undefined;
  if (v.stringValue !== undefined) return v.stringValue;
  if (v.intValue !== undefined) return Number(v.intValue);
  if (v.boolValue !== undefined) return v.boolValue;
  if (v.doubleValue !== undefined) return v.doubleValue;
  return undefined;
}
export function flattenWorks(works: Work[]): Work[] {
  return works.flatMap(w => [w, ...flattenWorks(w.children || [])]);
}
export function dateLabel(value: string, locale: Locale = 'zh') {
  return new Date(value).toLocaleDateString(localeTag(locale), { month: 'short', day: 'numeric' });
}
