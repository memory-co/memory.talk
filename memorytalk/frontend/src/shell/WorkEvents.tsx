import { useQuery } from '@tanstack/react-query';
import { Archive, ArchiveRestore, CirclePlus, History, Snowflake, SquareArrowOutUpRight, SquareX, type LucideIcon } from 'lucide-react';
import { api } from '@/lib/api';
import { localeTag, useT, type T } from '@/lib/i18n';
import { usePreferences } from '@/lib/store';
import { workletLabel, type WorkEvent } from '@/lib/types';
import { Empty, ErrorState, Loading } from '@/components/Shared';
import { cn } from '@/lib/utils';

/** 右侧面板:这个 work 的时间线(GET /works/{id}/events),新的在上。事件只有后端会写的那几种,认不出的原样显示 type。 */
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
        <p className="mt-1 text-xs text-muted-foreground"><time dateTime={e.ts}>{time(e.ts)}</time></p>
      </li>;
    })}</ol>
  </div>;
}

const statusName = (t: T, s: unknown) => (s === 'running' || s === 'archived' ? t(`status.${s}`) : String(s));
const scheme = (uri: unknown) => String(uri || '').split(':')[0];

function describe(t: T, e: WorkEvent, before: WorkEvent[]): { icon: LucideIcon; title: string; detail?: string } {
  const d = e.data;
  switch (e.type) {
    case 'created': return { icon: CirclePlus, title: d.by ? t('events.createdBy', { by: String(d.by) }) : t('events.created'), detail: String(d.goal ?? '') };
    case 'status': return { icon: d.to === 'archived' ? Archive : ArchiveRestore, title: t('events.status', { from: statusName(t, d.from), to: statusName(t, d.to) }) };
    case 'frozen': return { icon: Snowflake, title: t('events.frozen') };
    case 'worklet.attached': return { icon: SquareArrowOutUpRight, title: t('events.attached', { name: workletLabel(t, scheme(d.uri)) }), detail: String(d.uri ?? '') };
    case 'worklet.detached': {
      // 关闭事件只带工作单元 id(id 会复用),往前找最近一次打开它的事件拿 URI
      const opened = [...before].reverse().find(x => x.type === 'worklet.attached' && x.data.worklet === d.worklet);
      return { icon: SquareX, title: t('events.detached', { name: opened ? workletLabel(t, scheme(opened.data.uri)) : String(d.worklet ?? '') }), detail: opened ? String(opened.data.uri ?? '') : undefined };
    }
    default: return { icon: History, title: e.type, detail: Object.keys(d).length ? JSON.stringify(d) : undefined };
  }
}
