import { splitFile } from './protocol';
import type { CollectionObject } from './types';

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export interface Position { rel: string; claim: string; fields: Record<string, unknown>; body: string; rank: number | null }
/** 只读视图,从公开的文件契约派生;写入永远走文件本身。 */
export function objectView(object?: CollectionObject): { fields: Record<string, unknown>; body: string; positions: Position[]; invalid?: boolean } {
  if (!object) return { fields: {}, body: '', positions: [] };
  const readme = object.files['readme.md'] ?? '';
  let main: { fields: Record<string, unknown>; body: string };
  try { main = splitFile(readme); } catch { return { fields: {}, body: readme, positions: [], invalid: true }; }
  const positions: Position[] = Object.entries(object.files).filter(([name]) => name.startsWith('positions/') && name.endsWith('.md')).map(([rel, text]) => {
    let parsed: { fields: Record<string, unknown>; body: string };
    try { parsed = splitFile(text); } catch { parsed = { fields: {}, body: text }; }
    const rank = typeof parsed.fields.rank === 'number' ? parsed.fields.rank : null;
    return { rel, claim: rel.slice(10, -3), fields: parsed.fields, body: parsed.body, rank };
  }).sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.claim.localeCompare(b.claim));
  return { ...main, positions };
}
