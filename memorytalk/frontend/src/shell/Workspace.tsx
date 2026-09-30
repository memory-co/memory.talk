import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, BookOpen, Bot, ChevronDown, ChevronRight, ChevronsLeft, ChevronsRight, ExternalLink, Globe, LoaderCircle, Plus, Sparkles, Terminal, Wand2, X } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useServers, useSystem, useWork } from '@/lib/queries';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { columnLabel, columnNumber, workletLabel, type Canvas, type Column, type Worklet } from '@/lib/types';
import { Empty, ErrorState, Loading, Modal } from '@/components/Shared';
import { PanelView } from './PanelView';

/** 画布 = 几列,每列从上到下摆工作单元(docs/structure/v5/work.md#canvas)。服务端总给至少一列;没提到的工作单元补到第一列,已不存在的丢掉。 */
function layout(canvas: Canvas | undefined, worklets: Worklet[]): Column[] {
  const ids = new Set(worklets.map(s => s.id));
  const columns: Column[] = (canvas?.columns.length ? canvas.columns : [{ id: 'c1', alias: '', panels: [], collapsed: false }]).map(c => ({ id: c.id, alias: c.alias || '', collapsed: !!c.collapsed, panels: c.panels.filter(p => ids.has(p.worklet)) }));
  const placed = new Set(columns.flatMap(c => c.panels.map(p => p.worklet)));
  for (const s of worklets) if (!placed.has(s.id)) columns[0].panels.push({ worklet: s.id, collapsed: false });
  return columns;
}

/** 列标题:有别名显示别名,没有显示「列 3」。点一下就地改别名(无边框,回车 / 失焦保存,Esc 放弃);编号不动,清空别名回到「列 3」。 */
function ColumnName({ column, onRename }: { column: Column; onRename: (alias: string) => void }) {
  const t = useT();
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => { if (draft === null) return; const next = draft.trim(); setDraft(null); if (next !== column.alias) onRename(next); };
  if (draft !== null) return <Input autoFocus value={draft} maxLength={80} placeholder={columnNumber(t, column)} aria-label={t('work.renameColumn')} className="h-6 min-w-0 flex-1 rounded border-0 bg-accent/70 px-1 py-0 text-xs text-foreground shadow-none focus-visible:ring-0 md:text-xs" onFocus={e => e.currentTarget.select()} onChange={e => setDraft(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === 'Enter') commit(); else if (e.key === 'Escape') { e.stopPropagation(); setDraft(null); } }} />;
  return <button type="button" className={cn('min-w-0 truncate rounded px-1 py-0.5 text-left hover:bg-accent hover:text-foreground', column.alias && 'text-foreground')} title={t('work.renameColumn')} onClick={() => setDraft(column.alias)}>{columnLabel(t, column)}</button>;
}

export function Workspace({ id, onMeta }: { id: string; onMeta: () => void }) {
  const t = useT();
  const work = useWork(id);
  const base = `/works/${encodeURIComponent(id)}`;
  const worklets = useQuery({ queryKey: ['worklets', id], queryFn: ({ signal }) => api<Worklet[]>(`${base}/worklets`, { signal }), refetchInterval: 8_000 });
  const canvas = useQuery({ queryKey: ['canvas', id], queryFn: ({ signal }) => api<Canvas>(`${base}/canvas`, { signal }) });
  const [adding, setAdding] = useState<string | null>(null);          // 往哪一列加工作单元
  const columns = useMemo(() => layout(canvas.data, worklets.data || []), [canvas.data, worklets.data]);
  const byId = useMemo(() => new Map((worklets.data || []).map(s => [s.id, s])), [worklets.data]);
  // 布局改动:一个动作一个请求(work-events.md),服务端在当前画布上做、记事件,交回新画布
  const op = useMutation({ mutationFn: ({ path, method, body }: { path: string; method: 'POST' | 'PATCH' | 'DELETE'; body?: unknown }) => api<Canvas>(`${base}${path}`, { method, body }),
    onSuccess: data => { queryClient.setQueryData(['canvas', id], data); void queryClient.invalidateQueries({ queryKey: ['events', id] }); },
    onError: (error: Error) => { toast.error(error.message); void queryClient.invalidateQueries({ queryKey: ['canvas', id] }); },
  });
  const worklet$ = (w: string) => `/worklets/${encodeURIComponent(w)}`;
  const column$ = (c: string) => `/columns/${encodeURIComponent(c)}`;
  const find = (worklet: string) => { for (let ci = 0; ci < columns.length; ci++) { const pi = columns[ci].panels.findIndex(p => p.worklet === worklet); if (pi >= 0) return [ci, pi] as const; } return null; };
  const toggle = (worklet: string) => { const at = find(worklet); if (at) op.mutate({ path: worklet$(worklet), method: 'PATCH', body: { collapsed: !columns[at[0]].panels[at[1]].collapsed } }); };
  const move = (worklet: string, dir: 'left' | 'right' | 'up' | 'down') => {
    const at = find(worklet); if (!at) return;
    const [ci, pi] = at;
    const body = dir === 'left' || dir === 'right' ? { column: columns[Math.max(0, Math.min(columns.length - 1, ci + (dir === 'left' ? -1 : 1)))].id }
      : { column: columns[ci].id, index: Math.max(0, pi + (dir === 'up' ? -1 : 1)) };
    op.mutate({ path: `${worklet$(worklet)}/move`, method: 'POST', body });
  };
  const addColumn = (beside: string, side: 'left' | 'right') => op.mutate({ path: '/columns', method: 'POST', body: { beside, side } });
  const removeColumn = (colId: string) => op.mutate({ path: column$(colId), method: 'DELETE' });    // 只有空列能删(服务端也拦)
  const renameColumn = (colId: string, alias: string) => op.mutate({ path: column$(colId), method: 'PATCH', body: { alias } });
  const toggleColumn = (column: Column) => op.mutate({ path: column$(column.id), method: 'PATCH', body: { collapsed: !column.collapsed } });
  if (work.isPending) return <Loading />;
  if (work.isError) return <div className="p-4"><ErrorState error={work.error} retry={() => { void work.refetch(); }} /></div>;
  const ended = work.data.status === 'archived';
  const total = worklets.data?.length ?? 0;
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold" title={work.data.goal}>{work.data.goal}</h1>
    </div>
    {worklets.isPending || canvas.isPending ? <Loading /> : worklets.isError ? <div className="p-4"><ErrorState error={worklets.error} retry={() => { void worklets.refetch(); }} /></div>
      : total === 0 && columns.length === 1 ? <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={ended ? t('work.endedTitle') : t('work.readyTitle')}>
        <p>{ended ? t('work.endedText') : t('work.readyText')}</p>
        <div className="flex flex-wrap justify-center gap-2">{!ended && <Button onClick={() => setAdding(columns[0].id)}><Plus />{t('work.addSession')}</Button>}<Button variant="outline" onClick={onMeta}><BookOpen />{t('work.viewMeta')}</Button></div>
      </Empty></div>
      : <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 md:flex-row md:items-start md:overflow-x-auto md:overflow-y-hidden" aria-label={t('work.worklets')}>
        {columns.map((column, ci) => column.collapsed
          ? <button key={column.id} type="button" className="flex shrink-0 items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground hover:bg-accent md:h-full md:w-10 md:flex-col md:justify-start md:px-0 md:py-3" aria-label={t('work.expandColumn')} title={t('work.expandColumn')} aria-expanded={false} onClick={() => toggleColumn(column)}>
            <ChevronsRight className="size-4" /><span className="md:[writing-mode:vertical-rl]">{columnLabel(t, column)} · {column.panels.length}</span>
          </button>
          : <section key={column.id} className={cn('flex min-w-0 flex-col gap-3 md:h-full md:min-w-[28rem] md:flex-1 md:overflow-y-auto md:pr-1', columns.length > 1 && 'md:basis-0')} aria-label={columnLabel(t, column)}>
          {columns.length > 1 && <div className="flex items-center gap-2 text-xs text-muted-foreground"><ColumnName column={column} onRename={alias => renameColumn(column.id, alias)} />
            <div className="ml-auto flex items-center">
              {column.panels.length === 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.removeColumn')} title={t('work.removeColumn')} onClick={() => removeColumn(column.id)}><X className="size-3.5" /></Button>}
              <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs font-normal text-muted-foreground" aria-label={`${t('work.collapseColumn')} · ${column.panels.length}`} title={t('work.collapseColumn')} aria-expanded onClick={() => toggleColumn(column)}>{column.panels.length}<ChevronsLeft className="size-3.5" /></Button>
            </div></div>}
          {column.panels.map((panel, pi) => { const worklet = byId.get(panel.worklet); if (!worklet) return null; const index = (worklets.data || []).findIndex(s => s.id === worklet.id) + 1; return <div key={worklet.id} className="flex shrink-0 flex-col overflow-hidden rounded-lg border bg-card">
            <div className="flex items-center gap-1 border-b bg-muted/40 px-2 py-1">
              <Button variant="ghost" size="icon" className="size-7" aria-label={panel.collapsed ? t('work.expand') : t('work.collapse')} aria-expanded={!panel.collapsed} onClick={() => toggle(worklet.id)}>{panel.collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}</Button>
              {['http', 'https'].includes(worklet.scheme) ? <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" /> : <Terminal className="size-3.5 shrink-0 text-muted-foreground" />}
              <span className="text-sm font-medium">{workletLabel(t, worklet.scheme)}</span><span className="text-xs text-muted-foreground">{index}</span>
              <span className={cn('size-1.5 shrink-0 rounded-full', worklet.alive ? 'bg-emerald-500' : 'bg-muted-foreground/40')} title={worklet.alive ? t('worklet.alive') : t('worklet.dead')} />
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={worklet.uri}>{worklet.cwd || worklet.uri}</span>
              <div className="flex items-center">
                {ci > 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveLeft')} title={t('work.moveLeft')} onClick={() => move(worklet.id, 'left')}><ArrowLeft className="size-3.5" /></Button>}
                {ci < columns.length - 1 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveRight')} title={t('work.moveRight')} onClick={() => move(worklet.id, 'right')}><ArrowRight className="size-3.5" /></Button>}
                {pi > 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveUp')} title={t('work.moveUp')} onClick={() => move(worklet.id, 'up')}><ArrowUp className="size-3.5" /></Button>}
                {pi < column.panels.length - 1 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveDown')} title={t('work.moveDown')} onClick={() => move(worklet.id, 'down')}><ArrowDown className="size-3.5" /></Button>}
              </div>
            </div>
            {!panel.collapsed && <div className="flex h-[60vh] min-h-64 resize-y flex-col overflow-hidden"><PanelView work={work.data} worklet={worklet} /></div>}
          </div>; })}
          {!column.panels.length && <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">{t('work.emptyColumn')}</p>}
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="text-muted-foreground" disabled={op.isPending} onClick={() => addColumn(column.id, 'left')} title={t('work.addColumnLeft')}><ChevronsLeft />{t('work.addColumnLeft')}</Button>
            {!ended && <Button variant="ghost" size="sm" className="flex-1 text-muted-foreground" onClick={() => setAdding(column.id)}><Plus />{t('work.addSession')}</Button>}
            <Button variant="ghost" size="sm" className="ml-auto text-muted-foreground" disabled={op.isPending} onClick={() => addColumn(column.id, 'right')} title={t('work.addColumnRight')}>{t('work.addColumnRight')}<ChevronsRight /></Button>
          </div>
        </section>)}
      </div>}
    <Modal open={adding !== null} onClose={() => setAdding(null)} title={t('attach.title')} description={t('attach.description')}>
      {adding && <NewWorklet id={id} column={adding} onCreated={() => setAdding(null)} />}
    </Modal>
  </div>;
}

const DESCRIBED = ['bash', 'codex', 'claude', 'kimi', 'https'];

/** 弹层里的新建工作单元:像浏览器的新标签页——上面一条能输入的地址栏(块即 URI),下面几块应用。点应用只是把 URI 填进地址栏
 *  (终端类带上默认工作目录,网页是 https://),改不改都行,回车或点「打开」才建。 */
function NewWorklet({ id, column, onCreated }: { id: string; column: string; onCreated: (worklet: Worklet) => void }) {
  const t = useT();
  const servers = useServers();
  const system = useSystem();
  const input = useRef<HTMLInputElement>(null);
  const [uri, setUri] = useState('');
  const mutation = useMutation({ mutationFn: (raw: string) => api<Worklet>(`/works/${encodeURIComponent(id)}/worklets`, { method: 'POST', body: { uri: raw, column } }),
    onSuccess: async worklet => {
      queryClient.setQueryData(['live', id, worklet.id], worklet);
      await Promise.all(['worklets', 'canvas', 'events'].map(key => queryClient.invalidateQueries({ queryKey: [key, id] })));
      onCreated(worklet); setUri(''); toast.success(t('attach.added'));
    } });
  const valid = /^[a-z][a-z0-9+.-]*:\/\//i.test(uri.trim());
  const open = (raw: string) => { if (!mutation.isPending) mutation.mutate(raw.trim()); };
  const workspace = system.data?.workspace || '';
  const protocols = [...new Set(servers.data?.flatMap(s => s.protocols) || [])].filter(p => p !== 'http');
  const apps = (protocols.length ? protocols : ['bash', 'codex', 'claude', 'kimi', 'https']).map(scheme => ({ scheme, web: scheme === 'https', icon: scheme === 'bash' ? Terminal : scheme === 'https' ? Globe : scheme === 'claude' ? Sparkles : Bot }));
  const fill = (value: string) => { setUri(value); requestAnimationFrame(() => { const el = input.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }); };
  return <div className="flex flex-col gap-4">
    <form className="flex items-center gap-2" onSubmit={e => { e.preventDefault(); if (valid) open(uri); }}>
      <Input ref={input} autoFocus value={uri} onChange={e => setUri(e.target.value)} placeholder={t('attach.urlPlaceholder')} aria-label={t('attach.url')} className="h-10 font-mono text-sm" spellCheck={false} />
      <Button type="submit" className="h-10 shrink-0" disabled={!valid || mutation.isPending}>{mutation.isPending ? <LoaderCircle className="animate-spin" /> : <ArrowRight />}{t('attach.open')}</Button>
    </form>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {apps.map(({ scheme, web, icon: Icon }) => <button key={scheme} type="button" disabled={mutation.isPending} className="flex flex-col items-start gap-1.5 rounded-lg border p-3 text-left transition-colors hover:bg-accent disabled:opacity-50"
        onClick={() => fill(web ? 'https://' : `${scheme}://${workspace}`)}>
        <span className="flex items-center gap-2 text-sm font-medium"><Icon className="size-4" />{workletLabel(t, scheme)}</span>
        <span className="text-xs text-muted-foreground">{DESCRIBED.includes(scheme) ? t(`app.${scheme}` as 'app.bash') : t('app.other', { scheme })}</span>
      </button>)}
      <button type="button" className="flex flex-col items-start gap-1.5 rounded-lg border border-dashed p-3 text-left transition-colors hover:bg-accent" onClick={() => fill('')}>
        <span className="flex items-center gap-2 text-sm font-medium"><Wand2 className="size-4" />{t('attach.custom')}</span><span className="text-xs text-muted-foreground">{t('app.custom')}</span>
      </button>
    </div>
    {mutation.isError && <ErrorState error={mutation.error} />}
  </div>;
}
