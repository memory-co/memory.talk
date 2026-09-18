import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { DialogFooter } from '@/components/ui/dialog';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, BookOpen, Check, Clock3, FileText, Folder, Layers, LoaderCircle, MessageSquare, Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, pathPart } from '@/lib/api';
import { objectView } from '@/lib/collections';
import { instantiate, joinFile, kindOf, normalize, splitFile, toRegExp, type FileKind, type Protocol } from '@/lib/protocol';
import { useLayers } from '@/lib/queries';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { dateLabel, flattenCatalog, layerLabel, type Catalog, type CollectionObject, type Revision, type SearchHit, type TreeView } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, Modal } from '@/components/Shared';
import { FieldsForm } from './FieldsForm';

type Selection = { layer: string; path?: string };
function LayerIcon({ layer, className }: { layer: string; className?: string }) {
  return layer === 'card' ? <BookOpen className={className} /> : layer === 'issue' ? <MessageSquare className={className} /> : <FileText className={className} />;
}

export function Library({ layer = 'card', path, onSelect, compact = false, work }: Selection & {
  onSelect: (selection: Selection) => void; compact?: boolean; work?: string;
}) {
  const t = useT();
  const layers = useLayers();
  const [search, setSearch] = useState('');
  const [term, setTerm] = useState('');
  const [create, setCreate] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setTerm(search.trim()), 300); return () => clearTimeout(timer); }, [search]);
  const catalog = useQuery({ queryKey: ['catalog', layer], queryFn: ({ signal }) => api<Catalog>(`/collections/${encodeURIComponent(layer)}`, { signal }) });
  const results = useQuery({ queryKey: ['search', layer, term], queryFn: ({ signal }) => api<SearchHit[]>(`/collections/search?${new URLSearchParams({ q: term, layer })}`, { signal }), enabled: !!term });
  const objects = term ? [...new Map((results.data || []).map(hit => [hit.path, { path: hit.path, title: hit.path.split('/').pop() || hit.path }])).values()] : catalog.data ? flattenCatalog(catalog.data) : [];
  const query = term ? results : catalog;
  const definition = layers.data?.find(l => l.name === layer);
  const label = layerLabel(t, layer);
  const list = <div className="flex min-h-0 flex-1 flex-col">
    <div className="space-y-2 p-3">
      <Tabs value={layer} onValueChange={value => { onSelect({ layer: value }); setSearch(''); }}><TabsList className="h-8 w-full justify-start overflow-x-auto overscroll-x-contain" aria-label={t('library.layers')}>{(layers.data || []).map(item => <TabsTrigger key={item.name} value={item.name} className="gap-1.5 text-xs"><LayerIcon layer={item.name} className="size-3.5" />{layerLabel(t, item.name)}</TabsTrigger>)}</TabsList></Tabs>
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1"><Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" /><Input className="h-8 pl-8 pr-8 text-xs" aria-label={t('library.searchLabel')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('library.searchPlaceholder', { layer: label })} />{search && <Button variant="ghost" size="icon" className="absolute right-0.5 top-1/2 size-7 -translate-y-1/2" onClick={() => setSearch('')} aria-label={t('library.clearSearch')}><X className="size-3.5" /></Button>}</div>
        {definition && <Button variant="outline" size="icon" className="size-8 shrink-0" onClick={() => setCreate(true)} aria-label={t('library.new', { layer: label })} title={t('library.new', { layer: label })}><Plus /></Button>}
      </div>
      {layers.isError && <ErrorState error={layers.error} retry={() => { void layers.refetch(); }} />}
    </div>
    <div className="flex items-center justify-between px-3 pb-1 text-xs text-muted-foreground"><span>{term ? t('library.results') : t('library.all')}</span><span>{objects.length}</span></div>
    <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
      {query.isPending ? <div className="space-y-2 p-1">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-11" />)}</div>
        : query.isError ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} />
        : objects.length ? <div className="flex flex-col gap-0.5">
          {objects.map(object => <button type="button" key={object.path} aria-current={path === object.path ? 'true' : undefined} className={cn('flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground', path === object.path && 'bg-accent text-accent-foreground')} onClick={() => onSelect({ layer, path: object.path })}>
            <LayerIcon layer={layer} className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1"><span className="block truncate font-medium">{object.title || object.path.split('/').pop()}</span><span className="block truncate text-xs text-muted-foreground">{object.path.includes('/') ? object.path.slice(0, object.path.lastIndexOf('/')) : t('library.root')}</span></span>
          </button>)}
        </div>
        : <Empty className="m-1" icon={term ? <Search className="size-5" /> : <Folder className="size-5" />} title={term ? t('library.noResults') : t('library.empty', { layer: label })}><p>{term ? t('library.noResultsText') : t('library.emptyText')}</p>{!term && definition && <Button variant="outline" size="sm" onClick={() => setCreate(true)}>{t('library.createFirst')}</Button>}</Empty>}
    </div>
    {definition && !compact && <p className="flex items-start gap-1.5 border-t px-3 py-2 text-xs text-muted-foreground"><Layers className="mt-0.5 size-3.5 shrink-0" />{definition.description}</p>}
  </div>;
  const detail = path && <ObjectDetail key={`${layer}/${path}`} layer={layer} path={path} work={work} onSelect={onSelect} onClose={() => onSelect({ layer })} />;
  return <div className={cn('flex min-h-0 flex-1', compact ? 'flex-col' : 'flex-col md:flex-row')}>
    {compact ? (path ? detail : list) : <>
      <div className={cn('flex min-h-0 flex-col md:w-80 md:shrink-0 md:border-r', path ? 'hidden md:flex' : 'flex-1 md:flex-none')}>{list}</div>
      <div className={cn('min-h-0 flex-1 flex-col', path ? 'flex' : 'hidden md:flex')}>{detail || <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">{t('library.subtitle')}</div>}</div>
    </>}
    {definition && <ObjectEditor layer={layer} protocol={definition.protocol} open={create} onClose={() => setCreate(false)} work={work} onSaved={objectPath => { setCreate(false); onSelect({ layer, path: objectPath }); }} />}
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

export function ObjectDetail({ layer, path, onClose, onSelect, work }: {
  layer: string; path: string; work?: string; onClose: () => void; onSelect: (s: Selection) => void;
}) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const layers = useLayers();
  const protocol = layers.data?.find(l => l.name === layer)?.protocol;
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(false);
  const object = useQuery({ queryKey: ['object', layer, path, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(path)}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }) });
  const history = useQuery({ queryKey: ['history', layer, path], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(path)}`, { signal }), enabled: tab === 'history' });
  const view = objectView(object.data);
  const linkButton = (label: string, hint: string | undefined, onClick: () => void, key?: string | number) =>
    <Button key={key} variant="outline" className="h-auto w-full justify-start gap-2 whitespace-normal px-3 py-2 text-left font-normal" onClick={onClick}><MessageSquare className="size-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 break-all">{label}</span>{hint && <Badge variant="secondary" className="shrink-0">{hint}</Badge>}<ArrowUpRight className="size-4 shrink-0 text-muted-foreground" /></Button>;
  const issueLinks = (links: unknown) => Array.isArray(links) ? <div className="space-y-2">{links.map((value, i) => { const link = asObject(value); return linkButton(text(link.target), text(link.type), () => onSelect({ layer: 'issue', path: text(link.target).split('#')[0] }), i); })}</div> : null;
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex items-center gap-2 border-b px-3 py-2">
      <Button variant="ghost" size="icon" className="size-8" onClick={onClose} aria-label={t('library.back')}><ArrowLeft /></Button>
      <Badge variant="secondary">{layerLabel(t, layer)}</Badge>
      <Tabs value={tab} onValueChange={value => setTab(value as 'content' | 'history')} className="ml-auto"><TabsList className="h-8" aria-label={t('library.objectView')}><TabsTrigger value="content" className="text-xs">{t('library.tabContent')}</TabsTrigger><TabsTrigger value="history" className="gap-1 text-xs"><Clock3 className="size-3.5" />{t('library.tabHistory')}</TabsTrigger></TabsList></Tabs>
      {!revision && object.data && <Button variant="ghost" size="icon" className="size-8" onClick={() => setEditing(true)} aria-label={t('library.editCard')}><Pencil /></Button>}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">{object.isPending ? <Loading /> : object.isError ? <div className="p-4"><ErrorState error={object.error} retry={() => { void object.refetch(); }} /></div> : <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <div><p className="truncate font-mono text-xs text-muted-foreground">{path}</p><h2 className="mt-1 text-xl font-semibold tracking-tight">{object.data.title || path.split('/').pop()}</h2></div>
      {!!view.invalid && <ErrorState error={new Error(t('library.invalidMeta'))} />}
      {revision && <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs"><Clock3 className="size-3.5" /><span>{t('library.revision', { rev: revision.slice(0, 7) })}</span><Button variant="link" size="sm" className="ml-auto h-auto p-0 text-xs" onClick={() => setRevision('')}>{t('library.backToCurrent')}</Button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <ol className="ml-1.5 space-y-4 border-l pl-5">{history.data?.map(item => <li key={item.sha} className="relative"><span className="absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-background bg-muted-foreground" /><button type="button" className="block w-full text-left" onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="block text-sm font-medium break-all">{item.subject}</span><span className="mt-1 block text-xs text-muted-foreground">{item.author} · {dateLabel(item.date, locale)} · <span className="font-mono">{item.sha.slice(0, 7)}</span></span></button></li>)}</ol>
        : layer === 'origin' ? <Markdown text={object.data.content || ''} />
        : layer === 'card' ? <>
          {text(view.fields.context) && <p className="text-sm text-muted-foreground">{text(view.fields.context)}</p>}
          <Markdown text={view.body} />
          {text(view.fields.issue) && linkButton(t('library.viewDiscussion'), undefined, () => onSelect({ layer: 'issue', path: text(view.fields.issue) }))}
          {Array.isArray(view.fields.links) && view.fields.links.length > 0 && <div className="space-y-2"><Separator /><h4 className="text-xs font-medium text-muted-foreground">{t('library.relatedCards')}</h4>{view.fields.links.filter(link => typeof link === 'string').map(link => <Button variant="link" key={String(link)} className="h-auto justify-start gap-1.5 p-0 text-sm font-normal" onClick={() => onSelect({ layer: 'card', path: String(link) })}><BookOpen className="size-3.5" />{String(link)}</Button>)}</div>}
        </> : layer === 'issue' ? <>
          <Markdown text={view.body} />
          {text(view.fields.summary) && <Card className="bg-muted/40"><CardHeader className="p-4 pb-1"><CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('library.summary')}</CardTitle></CardHeader><CardContent className="p-4 pt-0"><Markdown text={text(view.fields.summary)} /></CardContent></Card>}
          <h3 className="mt-2 text-sm font-medium">{t('library.positions')} <span className="text-muted-foreground">{view.positions.length}</span></h3>
          {view.positions.map(p => <Card key={p.rel}><CardHeader className="p-4 pb-2"><CardTitle className="flex flex-wrap items-baseline gap-2 text-sm font-medium"><Badge variant={p.rank === null ? 'outline' : 'default'} className="font-mono">{p.rank === null ? t('library.unranked') : `#${p.rank}`}</Badge>{p.claim}</CardTitle>{text(p.fields.verdict) && <p className="text-xs text-muted-foreground">{text(p.fields.verdict)}</p>}</CardHeader><CardContent className="space-y-3 p-4 pt-0"><Markdown text={p.body} />{issueLinks(p.fields.links)}</CardContent></Card>)}
          {issueLinks(view.fields.links)}
        </> : <div className="space-y-5">{Object.entries(object.data.files).map(([name, value]) => { let parsed = { fields: {} as Record<string, unknown>, body: value }; try { parsed = splitFile(value); } catch { /* 原样 */ } return <section key={name} className="space-y-2"><h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><FileText className="size-3.5" />{name}</h3><FieldsTable fields={parsed.fields} />{kindOf(protocol, name)?.format.body === 'text' ? <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted p-3 font-mono text-xs">{parsed.body}</pre> : <Markdown text={parsed.body} />}</section>; })}</div>}
    </div>}</div>
    {protocol && <ObjectEditor layer={layer} protocol={protocol} path={path} initial={object.data} open={editing} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} work={work} />}
  </div>;
}

/* ------------------------------------------------------------------ 编辑器:完全由协议驱动 ------------------------------------------------------------------ */

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

function ObjectEditor({ layer, protocol, path, initial, open, onClose, onSaved, work }: {
  layer: string; protocol: Protocol; path?: string; initial?: CollectionObject; open: boolean; onClose: () => void; onSaved: (path: string) => void; work?: string;
}) {
  const t = useT();
  const raw = !protocol.object;                                                       // origin:一个文件,原文
  const [objectPath, setObjectPath] = useState(path || '');
  const [content, setContent] = useState('');
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [deleted, setDeleted] = useState<Set<string>>(new Set());
  const [subject, setSubject] = useState('');
  const [reason, setReason] = useState('');
  useEffect(() => {
    if (!open) return;
    setObjectPath(path || ''); setSubject(''); setReason(''); setDeleted(new Set());
    if (raw) { setContent(initial?.content || ''); return; }
    if (initial) { setDrafts(parseAll(initial.files, protocol)); return; }
    const fresh: Record<string, Draft> = {};
    for (const kind of protocol.files) if (kind.required && kind.fixed) fresh[kind.example] = { fields: {}, body: kind.template, kind };
    setDrafts(fresh);
  }, [open, path, initial, protocol, raw]);
  const payload = useMemo(() => (raw ? { content } : { files: serialize(drafts, deleted) }), [raw, content, drafts, deleted]);
  const validPath = !!objectPath.trim() && !objectPath.split('/').some(p => !p.trim() || p === '..');
  const target = `/collections/${encodeURIComponent(layer)}/${pathPart(objectPath.trim())}`;
  const method = path ? 'PUT' : 'POST';
  // 保存前 dry-run:协议不过的理由显示在表单里,而不是保存失败后的 toast
  const [check, setCheck] = useState<{ ok: boolean; reason?: string | null } | 'pending' | null>(null);
  useEffect(() => {
    if (!open || !validPath) { setCheck(null); return; }
    setCheck('pending');
    const timer = setTimeout(() => { api<{ ok: boolean; reason?: string | null }>(`${target}?dry_run=1`, { method, body: payload, work }).then(setCheck).catch((e: Error) => setCheck({ ok: false, reason: e.message })); }, 400);
    return () => clearTimeout(timer);
  }, [open, validPath, target, method, payload, work]);
  const mutation = useMutation({ mutationFn: () => api<CollectionObject>(target, { method, body: { ...payload, subject: subject || undefined, reason }, work }),
    onSuccess: () => { for (const key of ['catalog', 'object', 'history', 'search']) void queryClient.invalidateQueries({ queryKey: [key] }); toast.success(path ? t('library.saved') : t('library.created')); onSaved(objectPath.trim()); } });
  const ready = validPath && check !== 'pending' && check?.ok === true && !mutation.isPending;
  const label = layerLabel(t, layer);
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={path ? t('library.editTitle', { layer: label }) : t('library.newTitle', { layer: label })} description={t('library.editorText')}>
    <form className="grid gap-4" onSubmit={e => { e.preventDefault(); if (ready) mutation.mutate(); }}>
      {!path && <div className="grid gap-2"><Label htmlFor="object-path">{raw ? t('library.pathLabel') : t('editor.pathFor', { name: protocol.object?.name || '' })}</Label><Input id="object-path" autoFocus value={objectPath} onChange={e => setObjectPath(e.target.value)} placeholder={t('library.pathPlaceholder')} required /></div>}
      {raw ? <div className="grid gap-2"><Label htmlFor="object-content">{t('editor.origin')}</Label><Textarea id="object-content" className="min-h-40 max-h-96 resize-y font-mono text-sm" value={content} onChange={e => setContent(e.target.value)} placeholder={t('library.markdown')} /></div>
        : <ProtocolFiles protocol={protocol} objectPath={objectPath} drafts={drafts} deleted={deleted} onDrafts={setDrafts} onDeleted={setDeleted} />}
      <div className="grid gap-2 sm:grid-cols-2"><div className="grid gap-2"><Label htmlFor="object-subject">{t('editor.subject')}</Label><Input id="object-subject" value={subject} onChange={e => setSubject(e.target.value)} placeholder={t('editor.subjectPlaceholder')} /></div><div className="grid gap-2"><Label htmlFor="object-reason">{t('library.reason')}</Label><Input id="object-reason" value={reason} onChange={e => setReason(e.target.value)} placeholder={t('library.reasonPlaceholder')} /></div></div>
      <p className={cn('flex items-center gap-1.5 text-xs', check && check !== 'pending' && !check.ok ? 'text-destructive' : 'text-muted-foreground')}>{check === 'pending' ? <><LoaderCircle className="size-3.5 animate-spin" />{t('editor.checking')}</> : check?.ok ? <><Check className="size-3.5" />{t('editor.valid')}</> : check ? check.reason : null}</p>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <DialogFooter><Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>{t('common.cancel')}</Button><Button type="submit" disabled={!ready}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('common.save')}</Button></DialogFooter>
    </form>
  </Modal>;
}

/** 对象 = 一页;文件 = 属性 + 正文;带 name 的种类有「新建 <label>」。 */
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
