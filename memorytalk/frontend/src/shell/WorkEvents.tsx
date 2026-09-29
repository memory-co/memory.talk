import { useQuery } from '@tanstack/react-query';
import { Archive, ArchiveRestore, ArrowRightLeft, CirclePlus, Columns3, History, Pencil, Snowflake, SquareArrowOutUpRight, SquareX, Trash2, type LucideIcon } from 'lucide-react';
import { api } from '@/lib/api';
import { localeTag, useT, type T } from '@/lib/i18n';
import { usePreferences } from '@/lib/store';
import { columnLabel, workletLabel, type WorkEvent } from '@/lib/types';
import { Empty, ErrorState, Loading } from '@/components/Shared';
import { cn } from '@/lib/utils';

/** 右侧面板:这个 work 的时间线(GET /works/{id}/events),新的在上。画布动作带列标记 `{id, alias}`(当时的别名),每条带 `by`(docs/designs/v5/work-events.md);
 *  旧事件没有这两样就少一截。认不出的 type 原样显示。 */
export function WorkEvents({ id }: { id: string }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const events = useQuery({ queryKey: ['events', id], queryFn: ({ signal }) => api<WorkEvent[]>(`/works/${encodeURIComponent(id)}/events`, { signal }), refetchInterval: 5_000 });
  if (events.isPending) return <Loading />;
  if (events.isError) return <div className="p-4"><ErrorState error={events.error} retry={() => { void events.refetch(); }} /></div>;
  const list = events.data;
  if (!list.length) return <div className="flex flex-1 p-4"><Empty icon={<History className="size-5" />} title={t('events.empty')} /></div>;
  const time = (ts: string) => new Date(ts).toLocaleString(localeTag(locale), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  return <div className="min-h-0 flex-1 overflow-auto p-4">
    <ol className="ml-1.5 space-y-4 border-l pl-5">{list.map((e, i) => ({ e, i })).reverse().map(({ e, i }) => {
      const { icon: Icon, title, detail } = describe(t, e, list.slice(0, i));
      return <li key={i} className="relative">
        <span className="absolute -left-[31px] top-0 flex size-5 items-center justify-center rounded-full border bg-background text-muted-foreground"><Icon className="size-3" /></span>
        <p className="text-sm font-medium">{title}</p>
        {detail && <p className={cn('mt-0.5 break-all text-xs text-muted-foreground', e.type.startsWith('worklet.') && 'font-mono')}>{detail}</p>}
        <p className="mt-1 text-xs text-muted-foreground">{typeof e.data.by === 'string' && e.data.by && <>{e.data.by} · </>}<time dateTime={e.ts}>{time(e.ts)}</time></p>
      </li>;
    })}</ol>
  </div>;
}

const statusName = (t: T, s: unknown) => (s === 'running' || s === 'archived' ? t(`status.${s}`) : String(s));
const scheme = (uri: unknown) => String(uri || '').split(':')[0];
type ColumnMark = { id: string; alias?: string };
const isColumn = (c: unknown): c is ColumnMark => !!c && typeof c === 'object' && typeof (c as ColumnMark).id === 'string';
const alias = (a: unknown) => (typeof a === 'string' && a ? `「${a}」` : '');

function describe(t: T, e: WorkEvent, before: WorkEvent[]): { icon: LucideIcon; title: string; detail?: string } {
  const d = e.data;
  const col = (c: unknown) => (isColumn(c) ? columnLabel(t, c) : '');
  // 工作单元叫什么:事件里有 uri 就用,没有(旧的关闭 / 挪动事件)就往前找最近一次打开它的事件
  const uriOf = (): string => (typeof d.uri === 'string' ? d.uri : String([...before].reverse().find(x => x.type === 'worklet.attached' && x.data.worklet === d.worklet)?.data.uri ?? ''));
  const name = () => { const uri = uriOf(); return uri ? workletLabel(t, scheme(uri)) : String(d.worklet ?? ''); };
  const at = (key: 'events.attachedIn' | 'events.detachedIn', plain: 'events.attached' | 'events.detached') => (isColumn(d.column) ? t(key, { name: name(), column: col(d.column) }) : t(plain, { name: name() }));
  switch (e.type) {
    case 'created': return { icon: CirclePlus, title: t('events.created'), detail: String(d.goal ?? '') };
    case 'status': return { icon: d.to === 'archived' ? Archive : ArchiveRestore, title: t('events.status', { from: statusName(t, d.from), to: statusName(t, d.to) }) };
    case 'frozen': return { icon: Snowflake, title: t('events.frozen') };
    case 'column.added': return { icon: Columns3, title: t('events.columnAdded', { column: col(d.column) }) };
    case 'column.renamed': {
      const number = isColumn(d.column) ? t('work.column', { n: d.column.id.replace(/^c/, '') }) : '';
      const to = isColumn(d.column) ? d.column.alias : '';
      return { icon: Pencil, title: to ? t('events.columnRenamed', { column: number, alias: alias(to) }) : t('events.columnUnnamed', { column: number }), detail: d.from ? t('events.columnWas', { alias: alias(d.from) }) : undefined };
    }
    case 'column.removed': return { icon: Trash2, title: t('events.columnRemoved', { column: col(d.column) }) };
    case 'worklet.attached': return { icon: SquareArrowOutUpRight, title: at('events.attachedIn', 'events.attached'), detail: uriOf() };
    case 'worklet.detached': return { icon: SquareX, title: at('events.detachedIn', 'events.detached'), detail: uriOf() || undefined };
    case 'worklet.moved': {
      const from = d.from as { column?: unknown } | undefined, to = d.to as { column?: unknown; index?: number } | undefined;
      const same = isColumn(from?.column) && isColumn(to?.column) && from.column.id === to.column.id;
      return { icon: ArrowRightLeft, title: same ? t('events.reordered', { name: name(), column: col(to?.column), n: (to?.index ?? 0) + 1 }) : t('events.moved', { name: name(), from: col(from?.column), to: col(to?.column) }), detail: uriOf() || undefined };
    }
    default: return { icon: History, title: e.type, detail: Object.keys(d).length ? JSON.stringify(d) : undefined };
  }
}
