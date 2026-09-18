import { parse, stringify } from 'yaml';

/** 层协议(后端 GET /layers 给的 protocol),前端只认它,不认识具体哪一层。 */
export interface FieldSpec {
  type: 'string' | 'text' | 'number' | 'bool' | 'date' | 'enum' | 'ref' | 'list' | 'object';
  required?: boolean; description?: string; values?: string[]; layer?: string; item?: FieldSpec; fields?: Record<string, FieldSpec>;
}
export interface FileKind {
  pattern: string; label: string; fixed: boolean; example: string; required: boolean; name?: string;
  format: { fields?: Record<string, FieldSpec>; body: 'markdown' | 'text' }; template: string;
}
export interface Protocol {
  layer: string; description: string;
  object: { pattern: string; name: string; under: string; example: string } | null;
  files: FileKind[];
}

const FM = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

export function splitFile(text: string): { fields: Record<string, unknown>; body: string } {
  const m = text.match(FM);
  if (!m) return { fields: {}, body: text };
  const parsed = parse(m[1]);
  return { fields: parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}, body: m[2] };
}
export function joinFile(fields: Record<string, unknown>, body: string): string {
  const clean = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && v.length === 0)));
  const head = Object.keys(clean).length ? `---\n${stringify(clean).trimEnd()}\n---\n\n` : '';
  const text = body.replace(/\n+$/, '');
  return head + text + (text ? '\n' : '');
}
/** Python 的 (?P<name>…) → JS 的 (?<name>…)。 */
export function toRegExp(pattern: string): RegExp {
  return new RegExp(pattern.replace(/\(\?P</g, '(?<'));
}
export function kindOf(protocol: Protocol | undefined, rel: string): FileKind | undefined {
  return protocol?.files.find(k => toRegExp(k.pattern).test(rel));
}
export function instantiate(kind: FileKind, name: string): string {
  return kind.example.replace('{name}', name);
}
/** 一个字段的空值(表单初始值)。 */
export function emptyValue(f: FieldSpec): unknown {
  if (f.type === 'list') return [];
  if (f.type === 'bool') return false;
  if (f.type === 'object') return Object.fromEntries(Object.entries(f.fields || {}).map(([k, v]) => [k, emptyValue(v)]));
  return '';
}
/** 字段值 → 写进 frontmatter 的值(空的去掉、数字转数字)。 */
export function normalize(f: FieldSpec, value: unknown): unknown {
  if (value === undefined || value === null) return undefined;
  if (f.type === 'number') { if (value === '') return undefined; const n = Number(value); return Number.isNaN(n) ? value : n; }
  if (f.type === 'bool') return value ? true : undefined;
  if (f.type === 'list') return Array.isArray(value) ? value.map(v => normalize(f.item!, v)).filter(v => v !== undefined) : undefined;
  if (f.type === 'object') { const o: Record<string, unknown> = {}; for (const [k, sub] of Object.entries(f.fields || {})) { const v = normalize(sub, (value as Record<string, unknown>)[k]); if (v !== undefined) o[k] = v; } return o; }
  return value === '' ? undefined : value;
}
