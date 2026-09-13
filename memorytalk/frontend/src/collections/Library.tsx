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
import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, BookOpen, Clock3, FileText, Folder, Layers, LoaderCircle, MessageSquare, Pencil, Plus, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, pathPart } from '@/lib/api';
import { cardFiles, objectView } from '@/lib/collections';
import { useLayers } from '@/lib/queries';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { dateLabel, flattenCatalog, layerLabel, type Catalog, type CollectionObject, type Revision, type SearchHit } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, Modal } from '@/components/Shared';

type Selection = { layer: string; path?: string };
const CREATABLE = ['card', 'issue', 'origin'];
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
      <Tabs value={layer} onValueChange={value => { onSelect({ layer: value }); setSearch(''); }}><TabsList className="h-8 w-full justify-start overflow-x-auto" aria-label={t('library.layers')}>{(layers.data || []).map(item => <TabsTrigger key={item.name} value={item.name} className="gap-1.5 text-xs"><LayerIcon layer={item.name} className="size-3.5" />{layerLabel(t, item.name)}</TabsTrigger>)}</TabsList></Tabs>
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1"><Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" /><Input className="h-8 pl-8 pr-8 text-xs" aria-label={t('library.searchLabel')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('library.searchPlaceholder', { layer: label })} />{search && <Button variant="ghost" size="icon" className="absolute right-0.5 top-1/2 size-7 -translate-y-1/2" onClick={() => setSearch('')} aria-label={t('library.clearSearch')}><X className="size-3.5" /></Button>}</div>
        {CREATABLE.includes(layer) && <Button variant="outline" size="icon" className="size-8 shrink-0" onClick={() => setCreate(true)} aria-label={t('library.new', { layer: label })} title={t('library.new', { layer: label })}><Plus /></Button>}
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
        : <Empty className="m-1" icon={term ? <Search className="size-5" /> : <Folder className="size-5" />} title={term ? t('library.noResults') : t('library.empty', { layer: CREATABLE.includes(layer) ? label : t('library.content') })}><p>{term ? t('library.noResultsText') : t('library.emptyText')}</p>{!term && CREATABLE.includes(layer) && <Button variant="outline" size="sm" onClick={() => setCreate(true)}>{t('library.createFirst')}</Button>}</Empty>}
    </div>
    {definition && !compact && <p className="flex items-start gap-1.5 border-t px-3 py-2 text-xs text-muted-foreground"><Layers className="mt-0.5 size-3.5 shrink-0" />{definition.description}</p>}
  </div>;
  const detail = path && <ObjectDetail key={`${layer}/${path}`} layer={layer} path={path} work={work} onSelect={onSelect} onClose={() => onSelect({ layer })} />;
  return <div className={cn('flex min-h-0 flex-1', compact ? 'flex-col' : 'flex-col md:flex-row')}>
    {compact ? (path ? detail : list) : <>
      <div className={cn('flex min-h-0 flex-col md:w-80 md:shrink-0 md:border-r', path ? 'hidden md:flex' : 'flex-1 md:flex-none')}>{list}</div>
      <div className={cn('min-h-0 flex-1 flex-col', path ? 'flex' : 'hidden md:flex')}>{detail || <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">{t('library.subtitle')}</div>}</div>
    </>}
    <ObjectEditor layer={layer} open={create} onClose={() => setCreate(false)} work={work} onSaved={objectPath => { setCreate(false); onSelect({ layer, path: objectPath }); }} />
  </div>;
}

function asObject(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function text(value: unknown) { return typeof value === 'string' ? value : ''; }

export function ObjectDetail({ layer, path, onClose, onSelect, work }: {
  layer: string; path: string; work?: string; onClose: () => void; onSelect: (s: Selection) => void;
}) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(false);
  const object = useQuery({ queryKey: ['object', layer, path, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(path)}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }) });
  const history = useQuery({ queryKey: ['history', layer, path], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(path)}`, { signal }), enabled: tab === 'history' });
  const body = objectView(object.data);
  const linkButton = (label: string, hint: string | undefined, onClick: () => void, key?: string | number) =>
    <Button key={key} variant="outline" className="h-auto w-full justify-start gap-2 whitespace-normal px-3 py-2 text-left font-normal" onClick={onClick}><MessageSquare className="size-4 shrink-0 text-muted-foreground" /><span className="min-w-0 flex-1 break-all">{label}</span>{hint && <Badge variant="secondary" className="shrink-0">{hint}</Badge>}<ArrowUpRight className="size-4 shrink-0 text-muted-foreground" /></Button>;
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex items-center gap-2 border-b px-3 py-2">
      <Button variant="ghost" size="icon" className="size-8" onClick={onClose} aria-label={t('library.back')}><ArrowLeft /></Button>
      <Badge variant="secondary">{layerLabel(t, layer)}</Badge>
      <Tabs value={tab} onValueChange={value => setTab(value as 'content' | 'history')} className="ml-auto"><TabsList className="h-8" aria-label={t('library.objectView')}><TabsTrigger value="content" className="text-xs">{t('library.tabContent')}</TabsTrigger><TabsTrigger value="history" className="gap-1 text-xs"><Clock3 className="size-3.5" />{t('library.tabHistory')}</TabsTrigger></TabsList></Tabs>
      {layer === 'card' && !revision && object.data && <Button variant="ghost" size="icon" className="size-8" onClick={() => setEditing(true)} aria-label={t('library.editCard')}><Pencil /></Button>}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">{object.isPending ? <Loading /> : object.isError ? <div className="p-4"><ErrorState error={object.error} retry={() => { void object.refetch(); }} /></div> : <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <div><p className="truncate font-mono text-xs text-muted-foreground">{path}</p><h2 className="mt-1 text-xl font-semibold tracking-tight">{object.data.title || path.split('/').pop()}</h2></div>
      {!!body.invalidMeta && <ErrorState error={new Error(t('library.invalidMeta'))} />}
      {revision && <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs"><Clock3 className="size-3.5" /><span>{t('library.revision', { rev: revision.slice(0, 7) })}</span><Button variant="link" size="sm" className="ml-auto h-auto p-0 text-xs" onClick={() => setRevision('')}>{t('library.backToCurrent')}</Button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <ol className="ml-1.5 space-y-4 border-l pl-5">{history.data?.map(item => <li key={item.sha} className="relative"><span className="absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-background bg-muted-foreground" /><button type="button" className="block w-full text-left" onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="block text-sm font-medium break-all">{item.subject}</span><span className="mt-1 block text-xs text-muted-foreground">{item.author} · {dateLabel(item.date, locale)} · <span className="font-mono">{item.sha.slice(0, 7)}</span></span></button></li>)}</ol>
        : layer === 'card' ? <>
          {text(body.context) && <p className="text-sm text-muted-foreground">{text(body.context)}</p>}
          <Markdown text={text(body.body)} />
          {text(body.issue) && linkButton(t('library.viewDiscussion'), undefined, () => onSelect({ layer: 'issue', path: text(body.issue) }))}
          {Array.isArray(body.links) && body.links.length > 0 && <div className="space-y-2"><Separator /><h4 className="text-xs font-medium text-muted-foreground">{t('library.relatedCards')}</h4>{body.links.filter(link => typeof link === 'string').map(link => <Button variant="link" key={String(link)} className="h-auto justify-start gap-1.5 p-0 text-sm font-normal" onClick={() => onSelect({ layer: 'card', path: String(link) })}><BookOpen className="size-3.5" />{String(link)}</Button>)}</div>}
        </> : layer === 'issue' ? <>
          <Markdown text={text(body.readme)} />
          {text(body.summary) && <Card className="bg-muted/40"><CardHeader className="p-4 pb-1"><CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('library.summary')}</CardTitle></CardHeader><CardContent className="p-4 pt-0"><Markdown text={text(body.summary)} /></CardContent></Card>}
          <h3 className="mt-2 text-sm font-medium">{t('library.positions')} <span className="text-muted-foreground">{Array.isArray(body.positions) ? body.positions.length : 0}</span></h3>
          {Array.isArray(body.positions) && body.positions.map((value, i) => { const position = asObject(value); return <Card key={i}><CardHeader className="p-4 pb-2"><CardTitle className="flex items-baseline gap-2 text-sm font-medium"><span className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, '0')}</span>{text(position.claim)}</CardTitle>{text(position.note) && <p className="text-xs text-muted-foreground">{text(position.note)}</p>}</CardHeader><CardContent className="p-4 pt-0"><Markdown text={text(position.body)} /></CardContent></Card>; })}
          {Array.isArray(body.links) && body.links.length > 0 && <div className="space-y-2">{body.links.map((value, i) => { const link = asObject(value); return linkButton(text(link.target), text(link.type), () => onSelect({ layer: 'issue', path: text(link.target).split('#')[0] }), i); })}</div>}
        </> : layer === 'origin' ? <Markdown text={object.data.content || ''} />
        : <div className="space-y-4">{Object.entries(object.data.files).map(([name, value]) => <section key={name}><h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><FileText className="size-3.5" />{name}</h3>{name.endsWith('.md') ? <Markdown text={value} /> : <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted p-3 font-mono text-xs">{value}</pre>}</section>)}</div>}
    </div>}</div>
    <ObjectEditor layer={layer} path={path} initial={object.data} open={editing} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} work={work} />
  </div>;
}

function ObjectEditor({ layer, path, initial, open, onClose, onSaved, work }: {
  layer: string; path?: string; initial?: CollectionObject; open: boolean; onClose: () => void; onSaved: (path: string) => void; work?: string;
}) {
  const t = useT();
  const [objectPath, setObjectPath] = useState(path || '');
  const [content, setContent] = useState('');
  const [context, setContext] = useState('');
  const [reason, setReason] = useState('');
  useEffect(() => { if (open) { const view = objectView(initial); setObjectPath(path || ''); setContent(initial?.files['readme.md'] || ''); setContext(text(view.context)); setReason(''); } }, [open, path]);
  const mutation = useMutation({ mutationFn: () => {
    const payload = layer === 'origin' ? { content } : layer === 'issue' ? { files: { 'readme.md': content } } : { files: cardFiles(content, context, initial?.files) };
    return api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(objectPath.trim())}`, { method: path ? 'PUT' : 'POST', body: { ...payload, reason }, work });
  }, onSuccess: () => { for (const key of ['catalog', 'object', 'history', 'search']) void queryClient.invalidateQueries({ queryKey: [key] }); toast.success(path ? t('library.saved') : t('library.created')); onSaved(objectPath.trim()); } });
  const valid = !!objectPath.trim() && !objectPath.split('/').some(p => !p.trim() || p === '..');
  const label = layerLabel(t, layer);
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={path ? t('library.editTitle', { layer: label }) : t('library.newTitle', { layer: label })} description={t('library.editorText')}>
    <form className="grid gap-4" onSubmit={e => { e.preventDefault(); if (valid) mutation.mutate(); }}>
      {!path && <div className="grid gap-2"><Label htmlFor="object-path">{layer === 'origin' ? t('library.pathLabel') : t('library.pathLabelTitled')}</Label><Input id="object-path" autoFocus value={objectPath} onChange={e => setObjectPath(e.target.value)} placeholder={t('library.pathPlaceholder')} required /></div>}
      {layer === 'card' && <div className="grid gap-2"><Label htmlFor="object-context">{t('library.context')}</Label><Input id="object-context" value={context} onChange={e => setContext(e.target.value)} placeholder={t('library.contextPlaceholder')} /></div>}
      <div className="grid gap-2"><Label htmlFor="object-content">{layer === 'issue' ? t('library.issueBody') : t('library.body')}</Label><Textarea id="object-content" className="min-h-40 max-h-96 resize-y font-mono text-sm" value={content} onChange={e => setContent(e.target.value)} placeholder={t('library.markdown')} /></div>
      <div className="grid gap-2"><Label htmlFor="object-reason">{t('library.reason')}</Label><Input id="object-reason" value={reason} onChange={e => setReason(e.target.value)} placeholder={t('library.reasonPlaceholder')} /></div>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <DialogFooter><Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>{t('common.cancel')}</Button><Button type="submit" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('common.save')}</Button></DialogFooter>
    </form>
  </Modal>;
}
