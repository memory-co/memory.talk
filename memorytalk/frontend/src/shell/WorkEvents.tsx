import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Archive, ArchiveRestore, ArrowRightLeft, Bot, ChartGantt, CircleOff, CirclePlus, Columns3, History, Keyboard, MessageSquare, Pencil, SendHorizontal, SquareArrowOutUpRight, SquareX, Trash2, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { localeTag, useT, type T } from '@/lib/i18n';
import { api } from '@/lib/api';
import { useTrace } from '@/lib/queries';
import { navigate, useRoute } from '@/lib/router';
import { usePreferences } from '@/lib/store';
import { attrValue, columnLabel, columnNumber, traceRecords, traceSpans, workletLabel, type KeyValue, type TraceLogRecord, type TraceSpan, type WorkTrace } from '@/lib/types';
import { Empty, ErrorState, Loading } from '@/components/Shared';
import { cn } from '@/lib/utils';

/** 右侧面板「轨迹」(原来叫「动态」)= 这个 work 轨迹的列表视图(GET /works/{id}/trace,docs/designs/v5/work-trace.md §6),新的在上。
 *  一行是一个段的开始、一个段的结束(开着的段只有开始)或一个点;按时间排(纳秒超出 Number 的精度,用 BigInt 比),同一时刻开始 < 点 < 结束,再按接口给的先后。
 *  写法沿用 work-events.md §7:列的动作和挪工作单元带列标记(当时的别名,没有就「列 n」),下面一行是 `谁 · 时间`;工作单元叫什么从它的 worklet 段上取(点按 spanId 找段)。
 *  agent 那几层默认不读(接口默认不带,一轮两行、一条消息一个点,会把别的都挤走):有 agent 工作单元才给开关,点开再带 agent=1 读,
 *  只取其中的轮次段;认不出的段 / 点原样显示名字和属性。 */
export function WorkEvents({ id }: { id: string }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const trace = useTrace(id);
  const route = useRoute();
  const [turns, setTurns] = useState(false);
  const agentTrace = useQuery({ queryKey: ['trace', id, 'agent'], queryFn: ({ signal }) => api<WorkTrace>(`/works/${encodeURIComponent(id)}/trace?agent=1`, { signal }),
    enabled: turns, refetchInterval: 5_000 });
  const source = turns && agentTrace.data ? agentTrace.data : trace.data;
  const timeline = useMemo(() => (source ? build(source) : null), [source]);
  if (trace.isPending) return <Loading />;
  if (trace.isError) return <div className="p-4"><ErrorState error={trace.error} retry={() => { void trace.refetch(); }} /></div>;
  if (!timeline) return null;
  const hasAgent = timeline.spans.some(s => s.name === 'worklet' && ['claude', 'codex', 'kimi'].includes(text(s.attributes, 'memorytalk.worklet.scheme')));
  const turnCount = timeline.spans.filter(s => s.name === TURN).length;
  const rows = turns ? timeline.rows : timeline.rows.filter(r => r.span?.name !== TURN);
  const analysis = route.view === 'analysis';
  const toggle = <div className="mb-3 flex items-center gap-1">
    {hasAgent && <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs font-normal text-muted-foreground" aria-pressed={turns} onClick={() => setTurns(v => !v)}>
      <Bot className="size-3.5" />{turns ? t('events.hideTurns') : agentTrace.data ? t('events.showTurns', { n: turnCount }) : t('events.showAgentTurns')}
    </Button>}
    {/* 轨迹分析:左边换成甘特 + 火焰图(再点一下回到各列) */}
    <Button variant={analysis ? 'secondary' : 'ghost'} size="sm" className="ml-auto h-7 gap-1.5 px-2 text-xs font-normal" aria-pressed={analysis}
      onClick={() => navigate({ page: 'work', work: id, ...(analysis ? {} : { view: 'analysis' as const }) })}><ChartGantt className="size-3.5" />{t('analysis.open')}</Button>
  </div>;
  if (!rows.length) return <div className="flex flex-1 flex-col p-4">{toggle}<Empty icon={<History className="size-5" />} title={t('events.empty')} /></div>;
  const time = (date: Date) => date.toLocaleString(localeTag(locale), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  return <div className="min-h-0 flex-1 overflow-auto p-4">
    {toggle}
    <ol className="ml-1.5 space-y-4 border-l pl-5">{rows.map(row => {
      const { icon: Icon, title, detail, mono, by } = describe(t, row, timeline);
      const date = new Date(Number(row.at / 1000000n));
      return <li key={row.key} className="relative">
        <span className="absolute -left-[31px] top-0 flex size-5 items-center justify-center rounded-full border bg-background text-muted-foreground"><Icon className="size-3" /></span>
        <p className="text-sm font-medium">{title.replace(/\s*(「[^」]*」)\s*/g, '$1')}</p>
        {detail && <p className={cn('mt-0.5 break-all text-xs text-muted-foreground', mono && 'font-mono')}>{detail}</p>}
        <p className="mt-1 text-xs text-muted-foreground">{by && <>{by} · </>}<time dateTime={date.toISOString()}>{time(date)}</time></p>
      </li>;
    })}</ol>
  </div>;
}

const TURN = 'agent.turn';
type Edge = 'start' | 'point' | 'end';
const EDGE_ORDER: Record<Edge, number> = { start: 0, point: 1, end: 2 };
/** 一行:段的开始 / 结束带着那个段,点带着那条 log record;seq 是它在接口里的先后(段按开始时间,点按写入顺序)。 */
interface Row { at: bigint; edge: Edge; seq: number; key: string; span?: TraceSpan; point?: TraceLogRecord }
interface Timeline { rows: Row[]; spans: TraceSpan[]; byId: Map<string, TraceSpan>; uris: Map<string, string> }

const nanos = (value: string | undefined) => { try { return BigInt(value || 0); } catch { return 0n; } };

function build(trace: WorkTrace): Timeline {
  const spans = traceSpans(trace).filter(s => !s.name.startsWith('agent.') || s.name === TURN);         // agent 那几层只要轮次
  const points = traceRecords(trace).filter(p => !p.eventName.startsWith('agent.'));
  const rows: Row[] = [];
  spans.forEach((span, seq) => {
    rows.push({ at: nanos(span.startTimeUnixNano), edge: 'start', seq, key: `${span.spanId}:start`, span });
    if (span.endTimeUnixNano) rows.push({ at: nanos(span.endTimeUnixNano), edge: 'end', seq, key: `${span.spanId}:end`, span });
  });
  points.forEach((point, seq) => rows.push({ at: nanos(point.timeUnixNano), edge: 'point', seq, key: `${point.spanId}:${point.timeUnixNano}:${seq}`, point }));
  rows.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : EDGE_ORDER[a.edge] - EDGE_ORDER[b.edge] || a.seq - b.seq));
  rows.reverse();                                                     // 新的在上
  const uris = new Map<string, string>();                             // worklet id → uri(agent 轮次按 id 找它的工作单元)
  for (const span of spans) if (span.name === 'worklet') { const w = text(span.attributes, 'memorytalk.worklet.id'), uri = text(span.attributes, 'memorytalk.worklet.uri'); if (w && uri) uris.set(w, uri); }
  return { rows, spans, byId: new Map(spans.map(s => [s.spanId, s])), uris };
}

const text = (attributes: KeyValue[] | undefined, key: string) => { const v = attrValue(attributes, key); return v === undefined ? '' : String(v); };
const scheme = (uri: string) => uri.split(':')[0];
type ColumnMark = { id: string; alias: string };
/** 列标记是平的两个属性:`<prefix>column.id`(`c3`)和 `<prefix>column.alias`(当时的别名)。 */
const columnOf = (attributes: KeyValue[] | undefined, prefix = 'memorytalk.'): ColumnMark | null => {
  const id = text(attributes, `${prefix}column.id`);
  return id ? { id, alias: text(attributes, `${prefix}column.alias`) } : null;
};
const aliasOf = (t: T, a: string) => (a ? t('events.alias', { alias: a }) : '');
const raw = (attributes: KeyValue[] | undefined) => (attributes ?? []).filter(a => a.key !== 'user.id').map(a => `${a.key}=${String(attrValue(attributes, a.key) ?? '')}`).join(', ') || undefined;

interface Described { icon: LucideIcon; title: string; detail?: string; mono?: boolean; by?: string }

function describe(t: T, row: Row, { byId, uris }: Timeline): Described {
  const col = (c: ColumnMark | null) => (c ? (c.alias ? t('events.alias', { alias: c.alias }) : columnLabel(t, c)) : '');   // 有别名就用(当时的)别名,没有就「列 n」
  // 工作单元叫什么:worklet 段上有 uri;挪动的点挂在 worklet 段上(spanId),agent 轮次的父段是 worklet 段,再不行按 worklet id 找
  const uriOf = (attributes: KeyValue[] | undefined, owner?: TraceSpan) => text(attributes, 'memorytalk.worklet.uri') || text(owner?.attributes, 'memorytalk.worklet.uri')
    || uris.get(text(attributes, 'memorytalk.worklet.id') || text(owner?.attributes, 'memorytalk.worklet.id')) || '';
  const nameOf = (uri: string, attributes: KeyValue[] | undefined) => (uri ? workletLabel(t, scheme(uri)) : text(attributes, 'memorytalk.worklet.id'));
  if (row.point) {
    const p = row.point, a = p.attributes, by = text(a, 'user.id') || undefined;
    switch (p.eventName) {
      case 'column.added': return { icon: Columns3, title: t('events.columnAdded', { column: col(columnOf(a)) }), by };
      case 'column.removed': return { icon: Trash2, title: t('events.columnRemoved', { column: col(columnOf(a)) }), by };
      case 'column.renamed': {
        const c = columnOf(a), number = c ? columnNumber(t, c) : '', from = text(a, 'memorytalk.from');
        return { icon: Pencil, title: c?.alias ? t('events.columnRenamed', { column: number, alias: aliasOf(t, c.alias) }) : t('events.columnUnnamed', { column: number }), detail: from ? t('events.was', { alias: aliasOf(t, from) }) : undefined, by };
      }
      case 'worklet.moved': {
        const uri = uriOf(a, p.spanId ? byId.get(p.spanId) : undefined), name = nameOf(uri, a);
        const from = columnOf(a, 'memorytalk.from.'), to = columnOf(a);
        const title = from && to && from.id === to.id ? t('events.reordered', { name, column: col(to), n: Number(attrValue(a, 'memorytalk.index') ?? 0) + 1 }) : t('events.moved', { name, from: col(from), to: col(to) });
        return { icon: ArrowRightLeft, title, detail: uri || undefined, mono: true, by };
      }
      case 'worklet.closed': {                                        // 关的时候已经没有开着的段了(现场没了 / 归档过),段不动,单记一个点
        const uri = uriOf(a, p.spanId ? byId.get(p.spanId) : undefined), name = nameOf(uri, a), c = columnOf(a);
        return { icon: SquareX, title: c ? t('events.detachedIn', { name, column: col(c) }) : t('events.detached', { name }), detail: uri || undefined, mono: true, by };
      }
      case 'worklet.input': {                                         // 往现场里送了一次:原文不存,只有哪种、多长
        const name = nameOf(uriOf(a, p.spanId ? byId.get(p.spanId) : undefined), a);
        return text(a, 'memorytalk.input.kind') === 'keys' ? { icon: Keyboard, title: t('events.keys', { name }), by }
          : { icon: SendHorizontal, title: t('events.input', { name }), detail: t('events.inputLength', { n: Number(attrValue(a, 'memorytalk.input.length') ?? 0) }), by };
      }
      case 'work.renamed': {
        const from = text(a, 'memorytalk.from');
        return { icon: Pencil, title: t('events.workRenamed', { goal: aliasOf(t, text(a, 'memorytalk.work.goal')) }), detail: from ? t('events.was', { alias: aliasOf(t, from) }) : undefined, by };
      }
      default: return { icon: History, title: p.eventName, detail: raw(a), by };
    }
  }
  const span = row.span!, a = span.attributes, end = row.edge === 'end';
  const by = (end ? text(a, 'memorytalk.end.user.id') || text(a, 'user.id') : text(a, 'user.id')) || undefined;   // 关的人和开的人不同才另记 end.user.id
  const reason = text(a, 'memorytalk.end.reason');
  switch (span.name) {
    case 'work':
      if (end) return { icon: Archive, title: t('events.archived'), by };
      return attrValue(a, 'memorytalk.work.reopened') === true || span.links?.length
        ? { icon: ArchiveRestore, title: t('events.reopened'), by }
        : { icon: CirclePlus, title: t('events.created'), detail: text(a, 'memorytalk.work.goal') || undefined, by };
    case 'worklet': {
      const uri = uriOf(a), name = nameOf(uri, a), detail = uri || undefined;
      if (!end) { const c = columnOf(a); return { icon: SquareArrowOutUpRight, title: c ? t('events.attachedIn', { name, column: col(c) }) : t('events.attached', { name }), detail, mono: true, by }; }
      if (reason === 'gone') return { icon: CircleOff, title: t('events.gone', { name }), detail, mono: true };   // 现场自己没了,不算谁关的
      if (reason === 'archived') return { icon: SquareX, title: t('events.closedOnArchive', { name }), detail, mono: true, by };
      const c = columnOf(a, 'memorytalk.end.');                       // 关的时候在哪一列(开的时候那列记在 memorytalk.column.*)
      return { icon: SquareX, title: c ? t('events.detachedIn', { name, column: col(c) }) : t('events.detached', { name }), detail, mono: true, by };
    }
    case TURN: {
      const uri = uriOf(a, span.parentSpanId ? byId.get(span.parentSpanId) : undefined), name = nameOf(uri, a);
      return end ? { icon: Bot, title: t('events.turnEnded', { name, n: Number(attrValue(a, 'memorytalk.message.count') ?? attrValue(a, 'memorytalk.round.count') ?? 0) }) }
        : { icon: MessageSquare, title: t('events.turnStarted', { name }) };    // 轮次不记是谁(user.id 为空)
    }
    default: return { icon: History, title: t(end ? 'events.ended' : 'events.started', { name: span.name }), detail: raw(a), by };
  }
}
