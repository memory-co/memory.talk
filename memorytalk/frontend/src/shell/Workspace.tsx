import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, BookOpen, Bot, ChevronDown, ChevronRight, ChevronsLeft, ChevronsRight, Columns3, ExternalLink, GitBranch, Globe, LoaderCircle, Plus, Sparkles, Terminal, Wand2, X } from 'lucide-react';
import { toast } from 'sonner';
import { ApiError, api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useServers, useSystem, useWork } from '@/lib/queries';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { workletLabel, statusLabel, workStatuses, type Canvas, type Column, type Worklet, type Work, type WorkStatus } from '@/lib/types';
import { Empty, ErrorState, Loading, Modal } from '@/components/Shared';
import { NewSubwork } from './Home';
import { PanelView } from './PanelView';

/** 画布 = 几列,每列从上到下摆工作单元(docs/structure/v5/work.md#canvas)。没画布 / 没提到的工作单元补到第一列;已不存在的工作单元丢掉。 */
function layout(canvas: Canvas | undefined, worklets: Worklet[]): Column[] {
  const ids = new Set(worklets.map(s => s.id));
  const columns: Column[] = (canvas?.columns.length ? canvas.columns : [{ id: 'c1', panels: [], collapsed: false }]).map(c => ({ id: c.id, collapsed: !!c.collapsed, panels: c.panels.filter(p => ids.has(p.worklet)) }));
  const placed = new Set(columns.flatMap(c => c.panels.map(p => p.worklet)));
  for (const s of worklets) if (!placed.has(s.id)) columns[0].panels.push({ worklet: s.id, collapsed: false });
  return columns;
}

export function Workspace({ id, onMeta }: { id: string; onMeta: () => void }) {
  const t = useT();
  const work = useWork(id);
  const base = `/works/${encodeURIComponent(id)}`;
  const worklets = useQuery({ queryKey: ['worklets', id], queryFn: ({ signal }) => api<Worklet[]>(`${base}/worklets`, { signal }), refetchInterval: 8_000 });
  const canvas = useQuery({ queryKey: ['canvas', id], queryFn: ({ signal }) => api<Canvas>(`${base}/canvas`, { signal }) });
  const [adding, setAdding] = useState<string | null>(null);          // 往哪一列加工作单元
  const [subwork, setSubwork] = useState(false);
  const columns = useMemo(() => layout(canvas.data, worklets.data || []), [canvas.data, worklets.data]);
  const byId = useMemo(() => new Map((worklets.data || []).map(s => [s.id, s])), [worklets.data]);
  const update = useMutation({ mutationFn: (status: WorkStatus) => api<Work>(base, { method: 'PATCH', body: { status } }),
    onSuccess: () => { for (const key of [['work', id], ['works'], ['worklets', id]]) void queryClient.invalidateQueries({ queryKey: key }); },
    onError: (error: Error) => toast.error(error.message),
  });
  // 布局改动:整份 PUT,带 version;被别处改过就重新载入
  const save = useMutation({ mutationFn: (next: Column[]) => api<Canvas>(`${base}/canvas`, { method: 'PUT', body: { version: canvas.data?.version ?? 0, columns: next } }),
    onSuccess: data => queryClient.setQueryData(['canvas', id], data),
    onError: (error: Error) => { if (error instanceof ApiError && error.status === 409) { toast.message(t('work.layoutConflict')); void queryClient.invalidateQueries({ queryKey: ['canvas', id] }); } else toast.error(error.message); },
  });
  const edit = (fn: (cols: Column[]) => Column[]) => save.mutate(fn(columns.map(c => ({ id: c.id, collapsed: c.collapsed, panels: c.panels.map(p => ({ ...p })) }))));
  const find = (cols: Column[], worklet: string) => { for (let ci = 0; ci < cols.length; ci++) { const pi = cols[ci].panels.findIndex(p => p.worklet === worklet); if (pi >= 0) return [ci, pi] as const; } return null; };
  const toggle = (worklet: string) => edit(cols => { const at = find(cols, worklet); if (at) cols[at[0]].panels[at[1]].collapsed = !cols[at[0]].panels[at[1]].collapsed; return cols; });
  const move = (worklet: string, dir: 'left' | 'right' | 'up' | 'down') => edit(cols => {
    const at = find(cols, worklet); if (!at) return cols;
    const [ci, pi] = at; const [panel] = cols[ci].panels.splice(pi, 1);
    if (dir === 'left' || dir === 'right') cols[Math.max(0, Math.min(cols.length - 1, ci + (dir === 'left' ? -1 : 1)))].panels.push(panel);
    else cols[ci].panels.splice(Math.max(0, Math.min(cols[ci].panels.length, pi + (dir === 'up' ? -1 : 1))), 0, panel);
    return cols;
  });
  const addColumn = () => edit(cols => { let n = cols.length + 1; while (cols.some(c => c.id === `c${n}`)) n++; return [...cols, { id: `c${n}`, panels: [], collapsed: false }]; });
  const removeColumn = (colId: string) => edit(cols => cols.length > 1 ? cols.filter(c => c.id !== colId || c.panels.length > 0) : cols);   // 只有空列能删
  const toggleColumn = (colId: string) => edit(cols => cols.map(c => (c.id === colId ? { ...c, collapsed: !c.collapsed } : c)));
  const placeNew = (worklet: Worklet, colId: string) => { if (columns[0]?.id !== colId) edit(cols => { const at = find(cols, worklet.id); const panel = at ? cols[at[0]].panels.splice(at[1], 1)[0] : { worklet: worklet.id, collapsed: false }; (cols.find(c => c.id === colId) || cols[0]).panels.push(panel); return cols; }); };
  if (work.isPending) return <Loading />;
  if (work.isError) return <div className="p-4"><ErrorState error={work.error} retry={() => { void work.refetch(); }} /></div>;
  const ended = ['done', 'abandoned'].includes(work.data.status);
  const total = worklets.data?.length ?? 0;
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold" title={work.data.goal}>{work.data.goal}</h1>
      <Select value={work.data.status} disabled={update.isPending} onValueChange={value => update.mutate(value as WorkStatus)}><SelectTrigger aria-label={t('work.statusLabel')} className="h-8 w-32"><SelectValue /></SelectTrigger><SelectContent>{workStatuses.map(value => <SelectItem key={value} value={value}>{statusLabel(t, value)}</SelectItem>)}</SelectContent></Select>
      <Button variant="outline" size="sm" onClick={() => setSubwork(true)} disabled={ended}><GitBranch />{t('work.split')}</Button>
      <Button variant="outline" size="sm" onClick={addColumn} disabled={save.isPending}><Columns3 />{t('work.addColumn')}</Button>
    </div>
    {worklets.isPending || canvas.isPending ? <Loading /> : worklets.isError ? <div className="p-4"><ErrorState error={worklets.error} retry={() => { void worklets.refetch(); }} /></div>
      : total === 0 && columns.length === 1 ? <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={ended ? t('work.endedTitle') : t('work.readyTitle')}>
        <p>{ended ? t('work.endedText') : t('work.readyText')}</p>
        <div className="flex flex-wrap justify-center gap-2">{!ended && <Button onClick={() => setAdding(columns[0].id)}><Plus />{t('work.addSession')}</Button>}<Button variant="outline" onClick={onMeta}><BookOpen />{t('work.viewMeta')}</Button></div>
      </Empty></div>
      : <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 md:flex-row md:items-start md:overflow-x-auto md:overflow-y-hidden" aria-label={t('work.worklets')}>
        {columns.map((column, ci) => column.collapsed
          ? <button key={column.id} type="button" className="flex shrink-0 items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground hover:bg-accent md:h-full md:w-10 md:flex-col md:justify-start md:px-0 md:py-3" aria-label={t('work.expandColumn')} title={t('work.expandColumn')} aria-expanded={false} onClick={() => toggleColumn(column.id)}>
            <ChevronsRight className="size-4" /><span className="md:[writing-mode:vertical-rl]">{t('work.column', { n: ci + 1 })} · {column.panels.length}</span>
          </button>
          : <section key={column.id} className={cn('flex min-w-0 flex-col gap-3 md:h-full md:min-w-[28rem] md:flex-1 md:overflow-y-auto md:pr-1', columns.length > 1 && 'md:basis-0')} aria-label={t('work.column', { n: ci + 1 })}>
          {columns.length > 1 && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Columns3 className="size-3.5" />{t('work.column', { n: ci + 1 })}<span>{column.panels.length}</span>
            <div className="ml-auto flex items-center">
              {column.panels.length === 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.removeColumn')} title={t('work.removeColumn')} onClick={() => removeColumn(column.id)}><X className="size-3.5" /></Button>}
              <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.collapseColumn')} title={t('work.collapseColumn')} aria-expanded onClick={() => toggleColumn(column.id)}><ChevronsLeft className="size-3.5" /></Button>
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
          {!ended && <Button variant="ghost" size="sm" className="justify-start text-muted-foreground" onClick={() => setAdding(column.id)}><Plus />{t('work.addSession')}</Button>}
        </section>)}
      </div>}
    <Modal open={adding !== null} onClose={() => setAdding(null)} title={t('attach.title')} description={t('attach.description')}>
      {adding && <NewWorklet id={id} onCreated={worklet => { placeNew(worklet, adding); setAdding(null); }} />}
    </Modal>
    <NewSubwork parent={id} open={subwork} onClose={() => setSubwork(false)} />
  </div>;
}

const DESCRIBED = ['bash', 'codex', 'claude', 'kimi', 'https'];

/** 弹层里的新建工作单元:像浏览器的新标签页——上面一条能输入的地址栏(块即 URI),下面几块应用。点应用只是把 URI 填进地址栏
 *  (终端类带上默认工作目录,网页是 https://),改不改都行,回车或点「打开」才建。 */
function NewWorklet({ id, onCreated }: { id: string; onCreated: (worklet: Worklet) => void }) {
  const t = useT();
  const servers = useServers();
  const system = useSystem();
  const input = useRef<HTMLInputElement>(null);
  const [uri, setUri] = useState('');
  const mutation = useMutation({ mutationFn: (raw: string) => api<Worklet>(`/works/${encodeURIComponent(id)}/worklets`, { method: 'POST', body: { uri: raw } }),
    onSuccess: async worklet => {
      queryClient.setQueryData(['live', id, worklet.id], worklet);
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['worklets', id] }), queryClient.invalidateQueries({ queryKey: ['canvas', id] })]);
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
