import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, BookOpen, Check, Clock3, FileText, Folder, Layers, LoaderCircle, MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, pathPart } from '@/lib/api';
import { objectView } from '@/lib/collections';
import { instantiate, joinFile, kindOf, normalize, splitFile, toRegExp, type FileKind, type Protocol } from '@/lib/protocol';
import { useLayers } from '@/lib/queries';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { dateLabel, layerLabel, type CollectionObject, type RecentPage, type Revision, type TreeView } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown } from '@/components/Shared';
import { FieldsForm } from './FieldsForm';

/** filter = 左边列表在看哪层(all | 某层),只由 Tab 改;layer + path = 右边打开的对象,由点列表项决定。两者互不影响。 */
type Selection = { filter: string; layer?: string; path?: string };
const ALL = 'all';
function LayerIcon({ layer, className }: { layer: string; className?: string }) {
  return layer === 'card' ? <BookOpen className={className} /> : layer === 'issue' ? <MessageSquare className={className} /> : layer === ALL ? <Layers className={className} /> : <FileText className={className} />;
}

export function Library({ filter = ALL, layer, path, onSelect, compact = false, work }: Selection & {
  onSelect: (selection: Selection) => void; compact?: boolean; work?: string;
}) {
  const open = layer && path ? { layer, path } : null;
  const select = (obj: { layer: string; path: string } | null) => onSelect(obj ? { filter, ...obj } : { filter });
  const t = useT();
  const layers = useLayers();
  const [creating, setCreating] = useState<string | null>(null);        // 正在新建哪一层的对象(右边就是同一个页面,编辑态)
  const [view, setView] = useState<'recent' | 'tree'>('recent');
  const [dir, setDir] = useState('');
  useEffect(() => { setDir(''); setCreating(null); }, [filter]);
  const definition = layers.data?.find(l => l.name === filter);
  const creatable = (layers.data || []).filter(l => l.protocol.object);
  const newLabel = (l: { name: string; protocol: Protocol }) => t('library.new', { layer: l.protocol.object?.name || layerLabel(t, l.name) });
  const list = <div className="flex min-h-0 flex-1 flex-col">
    <div className="space-y-2 p-3">
      <Tabs value={filter} onValueChange={value => onSelect({ filter: value, ...(open || {}) })}><TabsList className="h-8 w-full justify-start overflow-x-auto overscroll-x-contain" aria-label={t('library.layers')}><TabsTrigger value={ALL} className="gap-1.5 text-xs"><Layers className="size-3.5" />{t('layer.all')}</TabsTrigger>{(layers.data || []).map(item => <TabsTrigger key={item.name} value={item.name} className="gap-1.5 text-xs"><LayerIcon layer={item.name} className="size-3.5" />{layerLabel(t, item.name)}</TabsTrigger>)}</TabsList></Tabs>
      <div className="flex items-center gap-2">
        <Tabs value={view} onValueChange={v => setView(v as 'recent' | 'tree')} className="min-w-0 flex-1"><TabsList className="h-8 w-full" aria-label={t('library.view')}><TabsTrigger value="recent" className="flex-1 gap-1.5 text-xs"><Clock3 className="size-3.5" />{t('library.viewRecent')}</TabsTrigger><TabsTrigger value="tree" className="flex-1 gap-1.5 text-xs"><Folder className="size-3.5" />{t('library.viewTree')}</TabsTrigger></TabsList></Tabs>
        {definition?.protocol.object ? <Button variant="outline" size="sm" className="h-8 shrink-0" onClick={() => setCreating(definition.name)}><Plus />{newLabel(definition)}</Button>
          : filter === ALL && creatable.length > 0 && <Select value="" onValueChange={value => setCreating(value)}><SelectTrigger className="h-8 w-auto shrink-0 gap-1" aria-label={t('library.newObject')}><Plus className="size-3.5" /><SelectValue placeholder={t('library.newObject')} /></SelectTrigger><SelectContent align="end">{creatable.map(l => <SelectItem key={l.name} value={l.name}>{newLabel(l)}</SelectItem>)}</SelectContent></Select>}
      </div>
      {layers.isError && <ErrorState error={layers.error} retry={() => { void layers.refetch(); }} />}
    </div>
    {view === 'recent' ? <RecentList filter={filter} selected={open?.path} onOpen={select} onCreate={definition?.protocol.object ? () => setCreating(definition.name) : undefined} />
      : <TreeList filter={filter} dir={dir} setDir={setDir} selected={open?.path} onOpen={select} />}
    {definition && !compact && <p className="flex items-start gap-1.5 border-t px-3 py-2 text-xs text-muted-foreground"><Layers className="mt-0.5 size-3.5 shrink-0" />{definition.description}</p>}
  </div>;
  const page = creating ? <ObjectPage key={`new/${creating}`} layer={creating} creating work={work} onOpen={o => { setCreating(null); select(o); }} onClose={() => setCreating(null)} />
    : open && <ObjectPage key={`${open.layer}/${open.path}`} layer={open.layer} path={open.path} work={work} onOpen={select} onClose={() => select(null)} />;
  return <div className={cn('flex min-h-0 flex-1', compact ? 'flex-col' : 'flex-col md:flex-row')}>
    {compact ? (page || list) : <>
      <div className={cn('flex min-h-0 flex-col md:w-80 md:shrink-0 md:border-r', page ? 'hidden md:flex' : 'flex-1 md:flex-none')}>{list}</div>
      <div className={cn('min-h-0 flex-1 flex-col', page ? 'flex' : 'hidden md:flex')}>{page || <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">{t('library.subtitle')}</div>}</div>
    </>}
  </div>;
}

function RecentList({ filter, selected, onOpen, onCreate }: { filter: string; selected?: string; onOpen: (o: { layer: string; path: string }) => void; onCreate?: () => void }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const [pages, setPages] = useState<RecentPage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  useEffect(() => { setPages([]); setCursor(null); }, [filter]);
  const page = useQuery({ queryKey: ['recent', filter, cursor], queryFn: ({ signal }) => api<RecentPage>(`/collections/recent?${new URLSearchParams({ ...(filter === ALL ? {} : { layer: filter }), limit: '30', ...(cursor ? { before: cursor } : {}) })}`, { signal }) });
  useEffect(() => { if (page.data) setPages(prev => (cursor ? [...prev.filter(p => p !== page.data), page.data] : [page.data])); }, [page.data, cursor]);
  const items = pages.flatMap(p => p.items);
  const last = pages[pages.length - 1];
  return <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
    <div className="flex items-center justify-between px-1 pb-1 text-xs text-muted-foreground"><span>{t('library.viewRecent')}</span><span>{items.length}</span></div>
    {page.isPending && !items.length ? <div className="space-y-2 p-1">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12" />)}</div>
      : page.isError ? <ErrorState error={page.error} retry={() => { void page.refetch(); }} />
      : items.length ? <div className="flex flex-col gap-0.5">
        {items.map(item => <button type="button" key={`${item.layer}:${item.path}`} aria-current={selected === item.path ? 'true' : undefined} className={cn('flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground', selected === item.path && 'bg-accent text-accent-foreground')} onClick={() => onOpen({ layer: item.layer, path: item.path })}>
          <LayerIcon layer={item.layer} className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1"><span className="block truncate font-medium">{item.title}</span><span className="block truncate text-xs text-muted-foreground">{item.path.includes('/') ? item.path.slice(0, item.path.lastIndexOf('/')) : t('library.root')} · {item.author} · {dateLabel(item.date, locale)}</span><span className="block truncate text-xs text-muted-foreground">{item.subject}</span></span>
        </button>)}
        {last?.next && <Button variant="ghost" size="sm" className="w-full" disabled={page.isFetching} onClick={() => setCursor(last.next)}>{page.isFetching ? <LoaderCircle className="animate-spin" /> : null}{t('library.loadMore')}</Button>}
      </div>
      : <Empty className="m-1" icon={<Clock3 className="size-5" />} title={t('library.empty', { layer: layerLabel(t, filter) })}><p>{t('library.emptyText')}</p>{onCreate && <Button variant="outline" size="sm" onClick={onCreate}>{t('library.createFirst')}</Button>}</Empty>}
  </div>;
}

/** 文件目录:/collections/tree 一层一层走,只留这一层的对象(目录保留)。 */
function TreeList({ filter, dir, setDir, selected, onOpen }: { filter: string; dir: string; setDir: (d: string) => void; selected?: string; onOpen: (o: { layer: string; path: string }) => void }) {
  const t = useT();
  const tree = useQuery({ queryKey: ['tree', filter, dir], queryFn: ({ signal }) => api<TreeView>(`/collections/tree?${new URLSearchParams({ path: dir, ...(filter === ALL ? {} : { layer: filter }) })}`, { signal }) });
  const items = tree.data?.items || [];
  const crumbs = dir ? dir.split('/') : [];
  return <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
    <div className="flex flex-wrap items-center gap-1 px-1 pb-1 font-mono text-xs text-muted-foreground">
      <button type="button" className="hover:text-foreground" onClick={() => setDir('')}>/</button>
      {crumbs.map((seg, i) => <span key={i} className="flex items-center gap-1"><span>/</span><button type="button" className="hover:text-foreground" onClick={() => setDir(crumbs.slice(0, i + 1).join('/'))}>{seg}</button></span>)}
    </div>
    {tree.isPending ? <div className="space-y-2 p-1">{[1, 2, 3].map(i => <Skeleton key={i} className="h-9" />)}</div>
      : tree.isError ? <ErrorState error={tree.error} retry={() => { void tree.refetch(); }} />
      : <div className="flex flex-col gap-0.5">
        {dir && <button type="button" className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent" onClick={() => setDir(dir.includes('/') ? dir.slice(0, dir.lastIndexOf('/')) : '')}><ArrowLeft className="size-4" />{t('library.up')}</button>}
        {items.map(item => item.kind === 'dir'
          ? <button type="button" key={item.path} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent" onClick={() => setDir(item.path)}><Folder className="size-4 text-muted-foreground" /><span className="truncate">{item.name}</span></button>
          : <button type="button" key={item.path} aria-current={selected === item.path ? 'true' : undefined} className={cn('flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent', selected === item.path && 'bg-accent')} onClick={() => onOpen({ layer: item.layer || 'origin', path: item.path })}><LayerIcon layer={item.layer || filter} className="size-4 text-muted-foreground" /><span className="truncate">{item.kind === 'object' ? item.path.split('/').pop() : item.name}</span></button>)}
        {!items.length && <p className="px-2 py-3 text-xs text-muted-foreground">{t('library.emptyDir')}</p>}
      </div>}
  </div>;
}

function text(value: unknown) { return typeof value === 'string' ? value : ''; }
function asObject(value: unknown): Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }

/** 只读渲染:按层特化的只是「怎么看」,不产生写入。 */
function FieldsTable({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields).filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length));
  if (!entries.length) return null;
  return <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-md border bg-muted/40 px-3 py-2 text-xs">{entries.map(([k, v]) => <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 break-all font-mono">{typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? String(v) : JSON.stringify(v)}</dd></div>)}</dl>;
}

type Draft = { fields: Record<string, unknown>; body: string; kind?: FileKind };
function parseAll(files: Record<string, string>, protocol: Protocol): Record<string, Draft> {
  const out: Record<string, Draft> = {};
  for (const [rel, textValue] of Object.entries(files)) {
    let parsed = { fields: {} as Record<string, unknown>, body: textValue };
    try { parsed = splitFile(textValue); } catch { /* 原样进正文 */ }
    out[rel] = { ...parsed, kind: kindOf(protocol, rel) };
  }
  return out;
}
function serialize(drafts: Record<string, Draft>, deleted: Set<string>): Record<string, string | null> {
  const files: Record<string, string | null> = {};
  for (const [rel, d] of Object.entries(drafts)) {
    const specs = d.kind?.format.fields;
    const fields: Record<string, unknown> = {};
    if (specs) for (const [k, spec] of Object.entries(specs)) { const v = normalize(spec, d.fields[k]); if (v !== undefined) fields[k] = v; }
    files[rel] = joinFile(fields, d.body);
  }
  for (const rel of deleted) files[rel] = null;
  return files;
}

/** 一个对象一页:浏览、修改、新建都在这里,没有弹层。creating = 新建这一层的对象(编辑态、带路径输入);否则打开 path,点「编辑」就地改。 */
export function ObjectPage({ layer, path, creating = false, onClose, onOpen, work }: {
  layer: string; path?: string; creating?: boolean; work?: string; onClose: () => void; onOpen: (o: { layer: string; path: string }) => void;
}) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const layers = useLayers();
  const protocol = layers.data?.find(l => l.name === layer)?.protocol;
  const raw = !!protocol && !protocol.object;
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(creating);
  const object = useQuery({ queryKey: ['object', layer, path, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(path || '')}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }), enabled: !!path });
  const history = useQuery({ queryKey: ['history', layer, path], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(path || '')}`, { signal }), enabled: !!path && tab === 'history' });
  const view = objectView(object.data);
  // ---- 编辑态 ----
  const [objectPath, setObjectPath] = useState(path || '');
  const [content, setContent] = useState('');
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const [subject, setSubject] = useState('');
  const [reason, setReason] = useState('');
  const beginEdit = () => {
    if (!protocol) return;
    setObjectPath(path || ''); setSubject(''); setReason(''); setDeleted(new Set());
    if (raw) setContent(object.data?.content || '');
    else if (object.data) setDrafts(parseAll(object.data.files, protocol));
    else { const fresh: Record<string, Draft> = {}; for (const kind of protocol.files) if (kind.required && kind.fixed) fresh[kind.example] = { fields: {}, body: kind.template, kind }; setDrafts(fresh); }
    setEditing(true);
  };
  useEffect(() => { if (creating && protocol && !Object.keys(drafts).length) beginEdit(); }, [creating, protocol]);   // eslint-disable-line react-hooks/exhaustive-deps
  const payload = useMemo(() => (raw ? { content } : { files: serialize(drafts, deleted) }), [raw, content, drafts, deleted]);
  const validPath = !!objectPath.trim() && !objectPath.split('/').some(p => !p.trim() || p === '..');
  const target = `/collections/${encodeURIComponent(layer)}/${pathPart(objectPath.trim())}`;
  const method = path ? 'PUT' : 'POST';
  const [check, setCheck] = useState<{ ok: boolean; reason?: string | null } | 'pending' | null>(null);
  useEffect(() => {
    if (!editing || !validPath) { setCheck(null); return; }
    setCheck('pending');
    const timer = setTimeout(() => { api<{ ok: boolean; reason?: string | null }>(`${target}?dry_run=1`, { method, body: payload, work }).then(setCheck).catch((e: Error) => setCheck({ ok: false, reason: e.message })); }, 400);
    return () => clearTimeout(timer);
  }, [editing, validPath, target, method, payload, work]);
  const save = useMutation({ mutationFn: () => api<CollectionObject>(target, { method, body: { ...payload, subject: subject || undefined, reason }, work }),
    onSuccess: saved => { for (const key of ['tree', 'recent', 'object', 'history', 'search']) void queryClient.invalidateQueries({ queryKey: [key] }); toast.success(path ? t('library.saved') : t('library.created')); setEditing(false); if (!path) onOpen({ layer, path: saved.path }); } });
  const ready = validPath && check !== 'pending' && check?.ok === true && !save.isPending;
  const cancel = () => { if (creating) onClose(); else setEditing(false); };
  const linkButton = (label: string, hint: string | undefined, onClick: () => void, key?: string | number) =>
    <Button key={key} variant="outline" className="h-auto w-full justify-start gap-2 whitespace-normal px-3 py-2 text-left font-normal" onClick={onClick}><MessageSquare className="size-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 break-all">{label}</span>{hint && <Badge variant="secondary" className="shrink-0">{hint}</Badge>}<ArrowUpRight className="size-4 shrink-0 text-muted-foreground" /></Button>;
  const issueLinks = (links: unknown) => Array.isArray(links) ? <div className="space-y-2">{links.map((value, i) => { const link = asObject(value); return linkButton(text(link.target), text(link.type), () => onOpen({ layer: 'issue', path: text(link.target).split('#')[0] }), i); })}</div> : null;
  const title = creating ? t('library.newTitle', { layer: protocol?.object?.name || layerLabel(t, layer) }) : object.data?.title || path?.split('/').pop();
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      <Button variant="ghost" size="icon" className="size-8" onClick={editing ? cancel : onClose} aria-label={editing ? t('common.cancel') : t('library.back')}>{editing ? <X /> : <ArrowLeft />}</Button>
      <Badge variant="secondary">{layerLabel(t, layer)}</Badge>
      {editing ? <>
        <span className={cn('ml-auto flex items-center gap-1.5 text-xs', check && check !== 'pending' && !check.ok ? 'text-destructive' : 'text-muted-foreground')}>{check === 'pending' ? <><LoaderCircle className="size-3.5 animate-spin" />{t('editor.checking')}</> : check?.ok ? <><Check className="size-3.5" />{t('editor.valid')}</> : check ? <span className="max-w-[40vw] truncate" title={check.reason || ''}>{check.reason}</span> : null}</span>
        <Button variant="outline" size="sm" className="h-8" onClick={cancel} disabled={save.isPending}>{t('common.cancel')}</Button>
        <Button size="sm" className="h-8" disabled={!ready} onClick={() => save.mutate()}>{save.isPending && <LoaderCircle className="animate-spin" />}{t('common.save')}</Button>
      </> : <>
        <Tabs value={tab} onValueChange={value => setTab(value as 'content' | 'history')} className="ml-auto"><TabsList className="h-8" aria-label={t('library.objectView')}><TabsTrigger value="content" className="text-xs">{t('library.tabContent')}</TabsTrigger><TabsTrigger value="history" className="gap-1 text-xs"><Clock3 className="size-3.5" />{t('library.tabHistory')}</TabsTrigger></TabsList></Tabs>
        {!revision && object.data && protocol && <Button variant="outline" size="sm" className="h-8" onClick={beginEdit}><Pencil />{t('editor.edit')}</Button>}
      </>}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">{editing && protocol ? <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      {creating && <div className="grid gap-2"><Label htmlFor="object-path">{raw ? t('library.pathLabel') : t('editor.pathFor', { name: protocol.object?.name || '' })}</Label><Input id="object-path" autoFocus value={objectPath} onChange={e => setObjectPath(e.target.value)} placeholder={t('library.pathPlaceholder')} required /></div>}
      {raw ? <div className="grid gap-2"><Label htmlFor="object-content">{t('editor.origin')}</Label><Textarea id="object-content" className="min-h-60 resize-y font-mono text-sm" value={content} onChange={e => setContent(e.target.value)} placeholder={t('library.markdown')} /></div>
        : <ProtocolFiles protocol={protocol} objectPath={objectPath} drafts={drafts} deleted={deleted} onDrafts={setDrafts} onDeleted={setDeleted} />}
      <div className="grid gap-2 sm:grid-cols-2"><div className="grid gap-2"><Label htmlFor="object-subject">{t('editor.subject')}</Label><Input id="object-subject" value={subject} onChange={e => setSubject(e.target.value)} placeholder={t('editor.subjectPlaceholder')} /></div><div className="grid gap-2"><Label htmlFor="object-reason">{t('library.reason')}</Label><Input id="object-reason" value={reason} onChange={e => setReason(e.target.value)} placeholder={t('library.reasonPlaceholder')} /></div></div>
      {check && check !== 'pending' && !check.ok && <ErrorState error={new Error(check.reason || '')} />}
      {save.isError && <ErrorState error={save.error} />}
    </div>
    : !path ? null : object.isPending ? <Loading /> : object.isError ? <div className="p-4"><ErrorState error={object.error} retry={() => { void object.refetch(); }} /></div> : <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <div><p className="truncate font-mono text-xs text-muted-foreground">{path}</p><h2 className="mt-1 text-xl font-semibold tracking-tight">{title}</h2></div>
      {!!view.invalid && <ErrorState error={new Error(t('library.invalidMeta'))} />}
      {revision && <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs"><Clock3 className="size-3.5" /><span>{t('library.revision', { rev: revision.slice(0, 7) })}</span><Button variant="link" size="sm" className="ml-auto h-auto p-0 text-xs" onClick={() => setRevision('')}>{t('library.backToCurrent')}</Button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <ol className="ml-1.5 space-y-4 border-l pl-5">{history.data?.map(item => <li key={item.sha} className="relative"><span className="absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-background bg-muted-foreground" /><button type="button" className="block w-full text-left" onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="block text-sm font-medium break-all">{item.subject}</span><span className="mt-1 block text-xs text-muted-foreground">{item.author} · {dateLabel(item.date, locale)} · <span className="font-mono">{item.sha.slice(0, 7)}</span></span></button></li>)}</ol>
        : layer === 'origin' ? <Markdown text={object.data.content || ''} />
        : layer === 'card' ? <>
          {text(view.fields.context) && <p className="text-sm text-muted-foreground">{text(view.fields.context)}</p>}
          <Markdown text={view.body} />
          {text(view.fields.issue) && linkButton(t('library.viewDiscussion'), undefined, () => onOpen({ layer: 'issue', path: text(view.fields.issue) }))}
          {Array.isArray(view.fields.links) && view.fields.links.length > 0 && <div className="space-y-2"><Separator /><h4 className="text-xs font-medium text-muted-foreground">{t('library.relatedCards')}</h4>{view.fields.links.filter(link => typeof link === 'string').map(link => <Button variant="link" key={String(link)} className="h-auto justify-start gap-1.5 p-0 text-sm font-normal" onClick={() => onOpen({ layer: 'card', path: String(link) })}><BookOpen className="size-3.5" />{String(link)}</Button>)}</div>}
        </> : layer === 'issue' ? <>
          <Markdown text={view.body} />
          {text(view.fields.summary) && <Card className="bg-muted/40"><CardHeader className="p-4 pb-1"><CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('library.summary')}</CardTitle></CardHeader><CardContent className="p-4 pt-0"><Markdown text={text(view.fields.summary)} /></CardContent></Card>}
          <h3 className="mt-2 text-sm font-medium">{t('library.positions')} <span className="text-muted-foreground">{view.positions.length}</span></h3>
          {view.positions.map(p => <Card key={p.rel}><CardHeader className="p-4 pb-2"><CardTitle className="flex flex-wrap items-baseline gap-2 text-sm font-medium"><Badge variant={p.rank === null ? 'outline' : 'default'} className="font-mono">{p.rank === null ? t('library.unranked') : `#${p.rank}`}</Badge>{p.claim}</CardTitle>{text(p.fields.verdict) && <p className="text-xs text-muted-foreground">{text(p.fields.verdict)}</p>}</CardHeader><CardContent className="space-y-3 p-4 pt-0"><Markdown text={p.body} />{issueLinks(p.fields.links)}</CardContent></Card>)}
          {issueLinks(view.fields.links)}
        </> : <div className="space-y-5">{Object.entries(object.data.files).map(([name, value]) => { let parsed = { fields: {} as Record<string, unknown>, body: value }; try { parsed = splitFile(value); } catch { /* 原样 */ } return <section key={name} className="space-y-2"><h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><FileText className="size-3.5" />{name}</h3><FieldsTable fields={parsed.fields} />{kindOf(protocol, name)?.format.body === 'text' ? <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted p-3 font-mono text-xs">{parsed.body}</pre> : <Markdown text={parsed.body} />}</section>; })}</div>}
    </div>}</div>
  </div>;
}

function ProtocolFiles({ protocol, objectPath, drafts, deleted, onDrafts, onDeleted }: {
  protocol: Protocol; objectPath: string; drafts: Record<string, Draft>; deleted: Set<string>;
  onDrafts: (d: Record<string, Draft>) => void; onDeleted: (d: Set<string>) => void;
}) {
  const t = useT();
  const [naming, setNaming] = useState<Record<string, string>>({});
  const [nameCheck, setNameCheck] = useState<Record<string, { can: boolean; reason?: string } | 'pending'>>({});
  const objDir = objectPath.trim() ? `${objectPath.trim()}${protocol.object ? '.' + protocol.layer : ''}` : '';
  const files = (kind: FileKind) => Object.keys(drafts).filter(rel => !deleted.has(rel) && toRegExp(kind.pattern).test(rel));
  const update = (rel: string, patch: Partial<Draft>) => onDrafts({ ...drafts, [rel]: { ...drafts[rel], ...patch } });
  const remove = (rel: string) => { const next = { ...drafts }; delete next[rel]; onDrafts(next); onDeleted(new Set([...deleted, rel])); };
  const add = async (kind: FileKind) => {
    const name = (naming[kind.pattern] || '').trim(); if (!name) return;
    const rel = instantiate(kind, name);
    setNameCheck(c => ({ ...c, [kind.pattern]: 'pending' }));
    try {
      const view = await api<TreeView>(`/collections/tree?${new URLSearchParams({ path: objDir, candidate: rel })}`);
      const c = view.candidate;
      if (c && !c.can && !(c.reason === '已存在' && !(rel in drafts))) { setNameCheck(x => ({ ...x, [kind.pattern]: { can: false, reason: c.reason } })); return; }
    } catch { /* 名字合法性最终由保存时的校验说了算 */ }
    if (rel in drafts || deleted.has(rel)) { onDeleted(new Set([...deleted].filter(d => d !== rel))); }
    onDrafts({ ...drafts, [rel]: drafts[rel] || { fields: {}, body: kind.template, kind } });
    setNaming(n => ({ ...n, [kind.pattern]: '' })); setNameCheck(x => ({ ...x, [kind.pattern]: { can: true } }));
  };
  return <div className="grid gap-4">
    {protocol.files.map(kind => <section key={kind.pattern} className="grid gap-2">
      <div className="flex items-center justify-between"><h4 className="text-sm font-medium">{kind.label}{kind.required && <span className="text-destructive"> *</span>}</h4><span className="font-mono text-xs text-muted-foreground">{kind.example}</span></div>
      {files(kind).map(rel => { const d = drafts[rel]; return <Card key={rel} className="shadow-none"><CardHeader className="flex-row items-center justify-between space-y-0 p-3 pb-2"><CardTitle className="font-mono text-xs font-normal">{rel}</CardTitle>{!(kind.required && kind.fixed) && <Button type="button" variant="ghost" size="icon" className="size-7 text-muted-foreground hover:text-destructive" aria-label={t('editor.deleteFile')} onClick={() => remove(rel)}><Trash2 className="size-3.5" /></Button>}</CardHeader>
        <CardContent className="grid gap-3 p-3 pt-0">
          {kind.format.fields && <div className="grid gap-2"><p className="text-xs font-medium text-muted-foreground">{t('editor.fields')}</p><FieldsForm fields={kind.format.fields} value={d.fields} onChange={fields => update(rel, { fields })} idPrefix={rel} /></div>}
          <div className="grid gap-1.5"><Label htmlFor={`${rel}-body`} className="text-xs text-muted-foreground">{t('editor.body')}</Label><Textarea id={`${rel}-body`} className="min-h-28 max-h-80 resize-y font-mono text-sm" value={d.body} onChange={e => update(rel, { body: e.target.value })} placeholder={kind.format.body === 'markdown' ? t('library.markdown') : ''} /></div>
        </CardContent></Card>; })}
      {(!kind.fixed || files(kind).length === 0) && <div className="flex items-start gap-2">
        {kind.fixed ? <Button type="button" variant="outline" size="sm" onClick={() => { onDeleted(new Set([...deleted].filter(d => d !== kind.example))); onDrafts({ ...drafts, [kind.example]: { fields: {}, body: kind.template, kind } }); }}><Plus />{t('editor.addFile', { label: kind.label })}</Button>
          : <><Input className="h-8 max-w-xs text-sm" placeholder={kind.name} aria-label={kind.name} value={naming[kind.pattern] || ''} onChange={e => setNaming(n => ({ ...n, [kind.pattern]: e.target.value }))} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void add(kind); } }} />
            <Button type="button" variant="outline" size="sm" disabled={!(naming[kind.pattern] || '').trim() || nameCheck[kind.pattern] === 'pending'} onClick={() => { void add(kind); }}>{nameCheck[kind.pattern] === 'pending' ? <LoaderCircle className="animate-spin" /> : <Plus />}{t('editor.addFile', { label: kind.label })}</Button></>}
        {nameCheck[kind.pattern] && nameCheck[kind.pattern] !== 'pending' && !(nameCheck[kind.pattern] as { can: boolean }).can && <span className="self-center text-xs text-destructive">{(nameCheck[kind.pattern] as { reason?: string }).reason}</span>}
      </div>}
    </section>)}
  </div>;
}
