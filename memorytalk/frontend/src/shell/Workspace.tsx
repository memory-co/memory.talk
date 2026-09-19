import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DialogFooter } from '@/components/ui/dialog';
import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, BookOpen, ChevronDown, ChevronRight, Columns3, ExternalLink, GitBranch, LoaderCircle, Plus, Terminal, X } from 'lucide-react';
import { toast } from 'sonner';
import { ApiError, api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useServers, useWork } from '@/lib/queries';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { sessionLabel, statusLabel, workStatuses, type Canvas, type Column, type Session, type Work, type WorkStatus } from '@/lib/types';
import { Empty, ErrorState, Loading, Modal } from '@/components/Shared';
import { NewSubwork } from './Home';
import { PanelView } from './PanelView';

/** 画布 = 几列,每列从上到下摆会话(docs/structure/v5/work.md#canvas)。没画布 / 没提到的会话补到第一列;已不存在的会话丢掉。 */
function layout(canvas: Canvas | undefined, sessions: Session[]): Column[] {
  const ids = new Set(sessions.map(s => s.id));
  const columns: Column[] = (canvas?.columns.length ? canvas.columns : [{ id: 'c1', panels: [] }]).map(c => ({ id: c.id, panels: c.panels.filter(p => ids.has(p.session)) }));
  const placed = new Set(columns.flatMap(c => c.panels.map(p => p.session)));
  for (const s of sessions) if (!placed.has(s.id)) columns[0].panels.push({ session: s.id, collapsed: false });
  return columns;
}

export function Workspace({ id, onLibrary }: { id: string; onLibrary: () => void }) {
  const t = useT();
  const work = useWork(id);
  const base = `/works/${encodeURIComponent(id)}`;
  const sessions = useQuery({ queryKey: ['sessions', id], queryFn: ({ signal }) => api<Session[]>(`${base}/sessions`, { signal }), refetchInterval: 8_000 });
  const canvas = useQuery({ queryKey: ['canvas', id], queryFn: ({ signal }) => api<Canvas>(`${base}/canvas`, { signal }) });
  const [adding, setAdding] = useState<string | null>(null);          // 往哪一列加会话
  const [subwork, setSubwork] = useState(false);
  const columns = useMemo(() => layout(canvas.data, sessions.data || []), [canvas.data, sessions.data]);
  const byId = useMemo(() => new Map((sessions.data || []).map(s => [s.id, s])), [sessions.data]);
  const update = useMutation({ mutationFn: (status: WorkStatus) => api<Work>(base, { method: 'PATCH', body: { status } }),
    onSuccess: () => { for (const key of [['work', id], ['works'], ['sessions', id]]) void queryClient.invalidateQueries({ queryKey: key }); },
    onError: (error: Error) => toast.error(error.message),
  });
  // 布局改动:整份 PUT,带 version;被别处改过就重新载入
  const save = useMutation({ mutationFn: (next: Column[]) => api<Canvas>(`${base}/canvas`, { method: 'PUT', body: { version: canvas.data?.version ?? 0, columns: next } }),
    onSuccess: data => queryClient.setQueryData(['canvas', id], data),
    onError: (error: Error) => { if (error instanceof ApiError && error.status === 409) { toast.message(t('work.layoutConflict')); void queryClient.invalidateQueries({ queryKey: ['canvas', id] }); } else toast.error(error.message); },
  });
  const edit = (fn: (cols: Column[]) => Column[]) => save.mutate(fn(columns.map(c => ({ id: c.id, panels: c.panels.map(p => ({ ...p })) }))));
  const find = (cols: Column[], session: string) => { for (let ci = 0; ci < cols.length; ci++) { const pi = cols[ci].panels.findIndex(p => p.session === session); if (pi >= 0) return [ci, pi] as const; } return null; };
  const toggle = (session: string) => edit(cols => { const at = find(cols, session); if (at) cols[at[0]].panels[at[1]].collapsed = !cols[at[0]].panels[at[1]].collapsed; return cols; });
  const move = (session: string, dir: 'left' | 'right' | 'up' | 'down') => edit(cols => {
    const at = find(cols, session); if (!at) return cols;
    const [ci, pi] = at; const [panel] = cols[ci].panels.splice(pi, 1);
    if (dir === 'left' || dir === 'right') cols[Math.max(0, Math.min(cols.length - 1, ci + (dir === 'left' ? -1 : 1)))].panels.push(panel);
    else cols[ci].panels.splice(Math.max(0, Math.min(cols[ci].panels.length, pi + (dir === 'up' ? -1 : 1))), 0, panel);
    return cols;
  });
  const addColumn = () => edit(cols => { let n = cols.length + 1; while (cols.some(c => c.id === `c${n}`)) n++; return [...cols, { id: `c${n}`, panels: [] }]; });
  const removeColumn = (colId: string) => edit(cols => { const i = cols.findIndex(c => c.id === colId); if (i < 0 || cols.length === 1) return cols; const [gone] = cols.splice(i, 1); cols[Math.max(0, i - 1)].panels.push(...gone.panels); return cols; });
  const placeNew = (session: Session, colId: string) => { if (columns[0]?.id !== colId) edit(cols => { const at = find(cols, session.id); const panel = at ? cols[at[0]].panels.splice(at[1], 1)[0] : { session: session.id, collapsed: false }; (cols.find(c => c.id === colId) || cols[0]).panels.push(panel); return cols; }); };
  if (work.isPending) return <Loading />;
  if (work.isError) return <div className="p-4"><ErrorState error={work.error} retry={() => { void work.refetch(); }} /></div>;
  const ended = ['done', 'abandoned'].includes(work.data.status);
  const total = sessions.data?.length ?? 0;
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold" title={work.data.goal}>{work.data.goal}</h1>
      <Select value={work.data.status} disabled={update.isPending} onValueChange={value => update.mutate(value as WorkStatus)}><SelectTrigger aria-label={t('work.statusLabel')} className="h-8 w-32"><SelectValue /></SelectTrigger><SelectContent>{workStatuses.map(value => <SelectItem key={value} value={value}>{statusLabel(t, value)}</SelectItem>)}</SelectContent></Select>
      <Button variant="outline" size="sm" onClick={() => setSubwork(true)} disabled={ended}><GitBranch />{t('work.split')}</Button>
      <Button variant="outline" size="sm" onClick={addColumn} disabled={save.isPending}><Columns3 />{t('work.addColumn')}</Button>
    </div>
    {sessions.isPending || canvas.isPending ? <Loading /> : sessions.isError ? <div className="p-4"><ErrorState error={sessions.error} retry={() => { void sessions.refetch(); }} /></div>
      : total === 0 && columns.length === 1 ? <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={ended ? t('work.endedTitle') : t('work.readyTitle')}>
        <p>{ended ? t('work.endedText') : t('work.readyText')}</p>
        <div className="flex flex-wrap justify-center gap-2">{!ended && <Button onClick={() => setAdding(columns[0].id)}><Plus />{t('work.addSession')}</Button>}<Button variant="outline" onClick={onLibrary}><BookOpen />{t('work.viewLibrary')}</Button></div>
      </Empty></div>
      : <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 md:flex-row md:items-start md:overflow-x-auto md:overflow-y-hidden" aria-label={t('work.sessions')}>
        {columns.map((column, ci) => <section key={column.id} className={cn('flex min-w-0 flex-col gap-3 md:h-full md:min-w-[28rem] md:flex-1 md:overflow-y-auto md:pr-1', columns.length > 1 && 'md:basis-0')} aria-label={t('work.column', { n: ci + 1 })}>
          {columns.length > 1 && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Columns3 className="size-3.5" />{t('work.column', { n: ci + 1 })}<span>{column.panels.length}</span><Button variant="ghost" size="icon" className="ml-auto size-7" aria-label={t('work.removeColumn')} title={t('work.removeColumn')} onClick={() => removeColumn(column.id)}><X className="size-3.5" /></Button></div>}
          {column.panels.map((panel, pi) => { const session = byId.get(panel.session); if (!session) return null; const index = (sessions.data || []).findIndex(s => s.id === session.id) + 1; return <div key={session.id} className="flex shrink-0 flex-col overflow-hidden rounded-lg border bg-card">
            <div className="flex items-center gap-1 border-b bg-muted/40 px-2 py-1">
              <Button variant="ghost" size="icon" className="size-7" aria-label={panel.collapsed ? t('work.expand') : t('work.collapse')} aria-expanded={!panel.collapsed} onClick={() => toggle(session.id)}>{panel.collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}</Button>
              {['http', 'https'].includes(session.scheme) ? <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" /> : <Terminal className="size-3.5 shrink-0 text-muted-foreground" />}
              <span className="text-sm font-medium">{sessionLabel(t, session.scheme)}</span><span className="text-xs text-muted-foreground">{index}</span>
              <span className={cn('size-1.5 shrink-0 rounded-full', session.alive ? 'bg-emerald-500' : 'bg-muted-foreground/40')} title={session.alive ? t('session.alive') : t('session.dead')} />
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={session.uri}>{session.cwd || session.uri}</span>
              <div className="flex items-center">
                {ci > 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveLeft')} title={t('work.moveLeft')} onClick={() => move(session.id, 'left')}><ArrowLeft className="size-3.5" /></Button>}
                {ci < columns.length - 1 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveRight')} title={t('work.moveRight')} onClick={() => move(session.id, 'right')}><ArrowRight className="size-3.5" /></Button>}
                {pi > 0 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveUp')} title={t('work.moveUp')} onClick={() => move(session.id, 'up')}><ArrowUp className="size-3.5" /></Button>}
                {pi < column.panels.length - 1 && <Button variant="ghost" size="icon" className="size-7" aria-label={t('work.moveDown')} title={t('work.moveDown')} onClick={() => move(session.id, 'down')}><ArrowDown className="size-3.5" /></Button>}
              </div>
            </div>
            {!panel.collapsed && <div className="flex h-[60vh] min-h-64 resize-y flex-col overflow-hidden"><PanelView work={work.data} session={session} /></div>}
          </div>; })}
          {!column.panels.length && <p className="rounded-lg border border-dashed px-3 py-6 text-center text-xs text-muted-foreground">{t('work.emptyColumn')}</p>}
          {!ended && <Button variant="ghost" size="sm" className="justify-start text-muted-foreground" onClick={() => setAdding(column.id)}><Plus />{t('work.addSession')}</Button>}
        </section>)}
      </div>}
    <AttachDialog id={id} open={adding !== null} onClose={() => setAdding(null)} onCreated={session => { if (adding) placeNew(session, adding); }} />
    <NewSubwork parent={id} open={subwork} onClose={() => setSubwork(false)} />
  </div>;
}

function AttachDialog({ id, open, onClose, onCreated }: { id: string; open: boolean; onClose: () => void; onCreated: (session: Session) => void }) {
  const t = useT();
  const servers = useServers();
  const [scheme, setScheme] = useState('bash');
  const [path, setPath] = useState('');
  const [custom, setCustom] = useState('');
  const mutation = useMutation({ mutationFn: () => {
    const raw = scheme === 'custom' ? custom.trim() : ['http', 'https'].includes(scheme)
      ? path.trim() : `${scheme}://${path.trim() ? encodeURI(path.trim()) : ''}`;
    return api<Session>(`/works/${encodeURIComponent(id)}/sessions`, { method: 'POST', body: { uri: raw } });
  }, onSuccess: async session => {
    queryClient.setQueryData(['live', id, session.id], session);
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['sessions', id] }), queryClient.invalidateQueries({ queryKey: ['canvas', id] })]);
    onCreated(session); onClose(); setPath(''); setCustom(''); toast.success(t('attach.added'));
  } });
  const protocols = [...new Set(servers.data?.flatMap(s => s.protocols) || [])].filter(p => p !== 'http');
  const isWeb = scheme === 'https' || scheme === 'http';
  const valid = scheme === 'custom' ? /^[a-z][a-z0-9+.-]*:\/\//i.test(custom.trim()) : isWeb ? /^https?:\/\//.test(path.trim()) : !path.trim() || path.trim().startsWith('/');
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={t('attach.title')} description={t('attach.description')}>
    <form className="grid gap-4" onSubmit={e => { e.preventDefault(); if (valid) mutation.mutate(); }}>
      <div className="grid gap-2"><Label htmlFor="session-scheme">{t('attach.type')}</Label><Select value={scheme} onValueChange={value => { setScheme(value); setPath(''); mutation.reset(); }}><SelectTrigger id="session-scheme"><SelectValue /></SelectTrigger><SelectContent>
        {(protocols.length ? protocols : ['bash', 'codex', 'claude', 'kimi', 'https']).map(p => <SelectItem value={p} key={p}>{sessionLabel(t, p)}</SelectItem>)}<SelectItem value="custom">{t('attach.custom')}</SelectItem>
      </SelectContent></Select></div>
      {scheme === 'custom' ? <div className="grid gap-2"><Label htmlFor="session-uri">URI</Label><Input id="session-uri" autoFocus placeholder="vim:///home/me/notes.md" value={custom} onChange={e => setCustom(e.target.value)} /></div>
        : <div className="grid gap-2"><Label htmlFor="session-path">{isWeb ? t('attach.webUrl') : t('attach.cwd')}</Label><Input id="session-path" placeholder={isWeb ? 'https://example.com' : t('attach.cwdPlaceholder')} value={path} onChange={e => setPath(e.target.value)} /></div>}
      {!valid && <p className="text-xs text-muted-foreground">{isWeb ? t('attach.hintWeb') : scheme === 'custom' ? t('attach.hintCustom') : t('attach.hintCwd')}</p>}
      {mutation.isError && <ErrorState error={mutation.error} />}
      <DialogFooter><Button type="submit" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{mutation.isPending ? t('attach.opening') : t('attach.open')}</Button></DialogFooter>
    </form>
  </Modal>;
}
