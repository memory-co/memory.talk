import { parse, stringify } from 'yaml';
import type { CollectionObject } from './types';

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export function readMeta(files: Record<string, string>): Record<string, unknown> {
  return record(parse(files['meta.yaml'] || '{}'));
}
/** Domain views are derived from the public file contract, never persisted separately. */
export function objectView(object?: CollectionObject): Record<string, unknown> {
  if (!object) return {};
  let meta: Record<string, unknown>;
  try { meta = readMeta(object.files); }
  catch { return { readme: object.files['readme.md'], body: object.files['readme.md'], invalidMeta: true }; }
  if (object.layer === 'card') return { ...meta, body: object.files['readme.md'] || '' };
  if (object.layer === 'issue') {
    const files = Object.entries(object.files).filter(([name]) => name.startsWith('positions/') && name.endsWith('.md'));
    const ranked = Array.isArray(meta.positions) ? meta.positions.map(record) : [];
    const claims = files.map(([name]) => name.slice(10, -3));
    const order = [...new Set([...ranked.map(r => String(r.claim)), ...claims.sort()])].filter(claim => claims.includes(claim));
    return { ...meta, readme: object.files['readme.md'] || '', positions: order.map(claim => ({
      claim, note: ranked.find(r => r.claim === claim)?.note || '', body: object.files[`positions/${claim}.md`],
    })) };
  }
  return object.files;
}
export function cardFiles(content: string, context: string, previous?: Record<string, string>) {
  return { 'readme.md': content, 'meta.yaml': stringify({ ...readMeta(previous || {}), context }) };
}
