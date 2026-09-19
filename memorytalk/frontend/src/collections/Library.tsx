import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, BookOpen, Check, Clock3, FileText, Folder, FolderOpen, Layers, LoaderCircle, MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, pathPart } from '@/lib/api';
import { instantiate, joinFile, kindOf, normalize, splitFile, toRegExp, type FileKind, type Protocol } from '@/lib/protocol';
import { useLayers } from '@/lib/queries';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { dateLabel, layerLabel, type CollectionObject, type RecentPage, type Revision, type TreeView } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown } from '@/components/Shared';
import { FieldsForm } from './FieldsForm';
const MarkdownEditor = lazy(() => import('@/components/MarkdownEditor'));

/** filter = 左边列表在看哪层(all | 某层),只由 Tab 改;layer + path (+ file) = 右边打开的文件,由点列表项决定。两者互不影响。
 *  单位是文件:origin 一个文件就是 path;有对象的层,path 是对象、file 是目录里的相对路径(readme.md / positions/x.md)。 */
type Selection = { filter: string; layer?: string; path?: string; file?: string };
type FileRef = { layer: string; path: string; file?: string };
/** 要在哪里建什么:object 为空 = 在 dir 下建一个新对象(或 origin 文件);否则在这个对象里建一个 kind 文件。 */
type NewFile = { layer: string; dir: string; object?: string; kind?: FileKind };
const ALL = 'all';
function LayerIcon({ layer, className }: { layer: string; className?: string }) {
  return layer === 'card' ? <BookOpen className={className} /> : layer === 'issue' ? <MessageSquare className={className} /> : layer === ALL ? <Layers className={className} /> : <FileText className={className} />;
}
const parent = (p: string) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
const base = (p: string) => p.split('/').pop() || '';
/** 一个对象的「主文件」:第一种 required 且固定的文件(readme.md)。 */
const mainFile = (protocol?: Protocol) => protocol?.files.find(k => k.required && k.fixed)?.example;

export function Library({ filter = ALL, layer, path, file, onSelect, compact = false, work }: Selection & {
  onSelect: (selection: Selection) => void; compact?: boolean; work?: string;
}) {
  const open: FileRef | null = layer && path ? { layer, path, file } : null;
  const select = (ref: FileRef | null) => onSelect(ref ? { filter, ...ref } : { filter });
  const t = useT();
  const layers = useLayers();
  const [creating, setCreating] = useState<NewFile | null>(null);
  const [view, setView] = useState<'recent' | 'tree'>('recent');
  const [dir, setDir] = useState('');
  useEffect(() => { setDir(''); setCreating(null); }, [filter]);
  const definition = layers.data?.find(l => l.name === filter);
  const here = view === 'tree' ? dir : open ? parent(fullPath(open)) : '';   // 「这里」= 文件目录视图的当前目录;最近修改视图里就是打开的文件所在目录
  const tree = useQuery({ queryKey: ['tree', filter, here], queryFn: ({ signal }) => api<TreeView>(`/collections/tree?${new URLSearchParams({ path: here, ...(filter === ALL ? {} : { layer: filter }) })}`, { signal }) });
  // 这里能建什么:tree.can_create 说了算;filter 只是过滤掉别的层
  const options = useMemo(() => {
    const cc = tree.data?.can_create; if (!cc || !layers.data) return [] as { key: string; label: string; value: NewFile }[];
    const out: { key: string; label: string; value: NewFile }[] = [];
    const inObject = tree.data?.layer;
    for (const f of cc.files) {
      if (!f.can || !f.layer || (filter !== ALL && f.layer !== filter)) continue;
      const protocol = layers.data.find(l => l.name === f.layer)?.protocol;
      if (inObject && f.pattern) { const kind = protocol?.files.find(k => k.pattern === f.pattern); if (kind) out.push({ key: `file:${f.pattern}`, label: t('library.new', { layer: kind.label }), value: { layer: f.layer, dir: here, object: objectOf(here, f.layer), kind } }); }
      else if (!inObject) out.push({ key: 'origin', label: t('library.newFile', { layer: layerLabel(t, f.layer) }), value: { layer: f.layer, dir: here } });
    }
    for (const o of cc.objects) {
      if (!o.can || (filter !== ALL && o.layer !== filter)) continue;
      const protocol = layers.data.find(l => l.name === o.layer)?.protocol;
      out.push({ key: `object:${o.layer}`, label: t('library.new', { layer: o.name }), value: { layer: o.layer, dir: here, kind: protocol?.files.find(k => k.required && k.fixed) } });
    }
    return out;
  }, [tree.data, layers.data, filter, here, t]);
  const list = <div className="flex min-h-0 flex-1 flex-col">
    <div className="space-y-2 p-3">
      <Tabs value={filter} onValueChange={value => onSelect({ filter: value, ...(open || {}) })}><TabsList className="h-8 w-full justify-start overflow-x-auto overscroll-x-contain" aria-label={t('library.layers')}><TabsTrigger value={ALL} className="gap-1.5 text-xs"><Layers className="size-3.5" />{t('layer.all')}</TabsTrigger>{(layers.data || []).map(item => <TabsTrigger key={item.name} value={item.name} className="gap-1.5 text-xs"><LayerIcon layer={item.name} className="size-3.5" />{layerLabel(t, item.name)}</TabsTrigger>)}</TabsList></Tabs>
      <div className="flex items-center gap-2">
        <Tabs value={view} onValueChange={v => setView(v as 'recent' | 'tree')} className="min-w-0 flex-1"><TabsList className="h-8 w-full" aria-label={t('library.view')}><TabsTrigger value="recent" className="flex-1 gap-1.5 text-xs"><Clock3 className="size-3.5" />{t('library.viewRecent')}</TabsTrigger><TabsTrigger value="tree" className="flex-1 gap-1.5 text-xs"><Folder className="size-3.5" />{t('library.viewTree')}</TabsTrigger></TabsList></Tabs>
        <Select value="" onValueChange={key => { const o = options.find(x => x.key === key); if (o) setCreating(o.value); }} disabled={!options.length}><SelectTrigger className="h-8 w-auto shrink-0 gap-1" aria-label={t('library.newObject')}><Plus className="size-3.5" /><SelectValue placeholder={t('library.newObject')} /></SelectTrigger><SelectContent align="end">{options.map(o => <SelectItem key={o.key} value={o.key}>{o.label}</SelectItem>)}</SelectContent></Select>
      </div>
      {layers.isError && <ErrorState error={layers.error} retry={() => { void layers.refetch(); }} />}
    </div>
    {view === 'recent' ? <RecentList filter={filter} selected={open} onOpen={select} />
      : <TreeList dir={dir} setDir={setDir} tree={tree} selected={open} onOpen={select} />}
    {definition && !compact && <p className="flex items-start gap-1.5 border-t px-3 py-2 text-xs text-muted-foreground"><Layers className="mt-0.5 size-3.5 shrink-0" />{definition.description}</p>}
  </div>;
  const page = creating ? <FilePage key={`new/${creating.layer}/${creating.dir}/${creating.kind?.pattern || ''}`} layer={creating.layer} creating={creating} work={work} onOpen={ref => { setCreating(null); select(ref); }} onClose={() => setCreating(null)} onDir={d => { setView('tree'); setDir(d); }} />
    : open && <FilePage key={`${open.layer}/${open.path}/${open.file || ''}`} layer={open.layer} path={open.path} file={open.file} work={work} onOpen={select} onClose={() => select(null)} onDir={d => { setView('tree'); setDir(d); }} />;
  return <div className={cn('flex min-h-0 flex-1', compact ? 'flex-col' : 'flex-col md:flex-row')}>
    {compact ? (page || list) : <>
      <div className={cn('flex min-h-0 flex-col md:w-80 md:shrink-0 md:border-r', page ? 'hidden md:flex' : 'flex-1 md:flex-none')}>{list}</div>
      <div className={cn('min-h-0 flex-1 flex-col', page ? 'flex' : 'hidden md:flex')}>{page || <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground">{t('library.subtitle')}</div>}</div>
    </>}
  </div>;
}

/** 目录 a/b.issue/positions → 对象 path a/b(去掉后缀、去掉里面的子目录)。 */
function objectOf(dirPath: string, layer: string): string {
  const segs = dirPath.split('/');
  const i = segs.findIndex(s => s.endsWith(`.${layer}`));
  return i < 0 ? dirPath : segs.slice(0, i + 1).join('/').slice(0, -(layer.length + 1));
}
const same = (a: FileRef | null | undefined, b: FileRef) => !!a && a.layer === b.layer && a.path === b.path && (a.file || '') === (b.file || '');

function RecentList({ filter, selected, onOpen }: { filter: string; selected: FileRef | null; onOpen: (ref: FileRef) => void }) {
  const t = useT();
  const layers = useLayers();
  const title = (ref: FileRef) => fileTitle(ref, kindOf(layers.data?.find(l => l.name === ref.layer)?.protocol, ref.file || ''));
  const locale = usePreferences(s => s.locale);
  const [pages, setPages] = useState<RecentPage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  useEffect(() => { setPages([]); setCursor(null); }, [filter]);
  const page = useQuery({ queryKey: ['recent', filter, cursor], queryFn: ({ signal }) => api<RecentPage>(`/collections/recent?${new URLSearchParams({ ...(filter === ALL ? {} : { layer: filter }), limit: '30', ...(cursor ? { before: cursor } : {}) })}`, { signal }) });
  useEffect(() => { if (page.data) setPages(prev => (cursor ? [...prev.filter(p => p !== page.data), page.data] : [page.data])); }, [page.data, cursor]);
  // 一行一个文件:对象层按这次提交碰到的文件展开
  const rows = pages.flatMap(p => p.items).flatMap(item => (item.files.length ? item.files : [undefined]).map(file => ({ item, ref: { layer: item.layer, path: item.path, file } as FileRef })));
  const last = pages[pages.length - 1];
  return <div className="min-h-0 flex-1 overflow-auto px-2 pb-2">
    <div className="flex items-center justify-between px-1 pb-1 text-xs text-muted-foreground"><span>{t('library.viewRecent')}</span><span>{rows.length}</span></div>
    {page.isPending && !rows.length ? <div className="space-y-2 p-1">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12" />)}</div>
      : page.isError ? <ErrorState error={page.error} retry={() => { void page.refetch(); }} />
      : rows.length ? <div className="flex flex-col gap-0.5">
        {rows.map(({ item, ref }) => <button type="button" key={`${ref.layer}:${ref.path}:${ref.file || ''}`} aria-current={same(selected, ref) ? 'true' : undefined} className={cn('flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground', same(selected, ref) && 'bg-accent text-accent-foreground')} onClick={() => onOpen(ref)}>
          <LayerIcon layer={item.layer} className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1"><span className="block truncate font-medium">{title(ref)}</span><span className="block truncate font-mono text-xs text-muted-foreground">{fullPath(ref)}</span><span className="block truncate text-xs text-muted-foreground">{item.author} · {dateLabel(item.date, locale)} · {item.subject}</span></span>
        </button>)}
        {last?.next && <Button variant="ghost" size="sm" className="w-full" disabled={page.isFetching} onClick={() => setCursor(last.next)}>{page.isFetching ? <LoaderCircle className="animate-spin" /> : null}{t('library.loadMore')}</Button>}
      </div>
      : <Empty className="m-1" icon={<Clock3 className="size-5" />} title={t('library.empty', { layer: layerLabel(t, filter) })}><p>{t('library.emptyText')}</p></Empty>}
  </div>;
}

/** 页面标题:主文件用对象名,其他文件用正则里 name 那段(没有就文件名),origin 用文件名。 */
function fileTitle(ref: FileRef, kind?: FileKind): string {
  if (!ref.file) return base(ref.path);
  if (kind?.fixed && kind.required) return base(ref.path);
  if (kind) { const m = ref.file.match(toRegExp(kind.pattern)); if (m?.groups?.name) return m.groups.name; }
  return base(ref.file);
}
/** 仓库里的真实路径:a/b.issue/positions/x.md。 */
function fullPath(ref: FileRef): string { return ref.file ? `${ref.path}.${ref.layer}/${ref.file}` : ref.path; }

/** 文件目录:就是一个文件系统,.issue/ 目录也照常进去看。 */
function TreeList({ dir, setDir, tree, selected, onOpen }: { dir: string; setDir: (d: string) => void; tree: ReturnType<typeof useQuery<TreeView>>; selected: FileRef | null; onOpen: (ref: FileRef) => void }) {
  const t = useT();
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
        {dir && <button type="button" className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent" onClick={() => setDir(parent(dir))}><ArrowLeft className="size-4" />{t('library.up')}</button>}
        {items.map(item => {
          if (item.kind === 'dir') return <button type="button" key={item.path} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent" onClick={() => setDir(item.path)}><Folder className="size-4 text-muted-foreground" /><span className="truncate">{item.name}</span></button>;
          if (item.kind === 'object') return <button type="button" key={item.path} className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent" onClick={() => setDir(`${item.path}.${item.layer}`)}><FolderOpen className="size-4 text-muted-foreground" /><span className="truncate">{item.name}</span><Badge variant="secondary" className="ml-auto shrink-0 font-normal">{layerLabel(t, item.layer || '')}</Badge></button>;
          const ref: FileRef = item.object ? { layer: item.layer || ALL, path: item.object, file: item.rel || item.name } : { layer: item.layer || 'origin', path: item.path };
          return <button type="button" key={item.path} aria-current={same(selected, ref) ? 'true' : undefined} className={cn('flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent', same(selected, ref) && 'bg-accent')} onClick={() => onOpen(ref)}><FileText className="size-4 text-muted-foreground" /><span className="truncate">{item.name}</span></button>;
        })}
        {!items.length && <p className="px-2 py-3 text-xs text-muted-foreground">{t('library.emptyDir')}</p>}
      </div>}
  </div>;
}

function text(value: unknown) { return typeof value === 'string' ? value : ''; }
/** 只读的属性行:Notion 那种「属性名 | 值」。 */
function Properties({ fields, protocol, onOpen }: { fields: Record<string, unknown>; protocol?: Protocol; onOpen: (ref: FileRef) => void }) {
  const entries = Object.entries(fields).filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length));
  if (!entries.length) return null;
  const refTo = (layer: string, target: string) => { const m = protocol && layer ? { layer, path: target.split('#')[0] } : null; return m ? <Button variant="link" className="h-auto p-0 font-mono text-xs" onClick={() => onOpen({ layer, path: m.path, file: undefined })}>{target}</Button> : <span className="font-mono">{target}</span>; };
  const render = (v: unknown, spec?: { type?: string; layer?: string; item?: { type?: string; layer?: string; fields?: Record<string, { type?: string; layer?: string }> } }): React.ReactNode => {
    if (spec?.type === 'ref' && typeof v === 'string') return refTo(spec.layer || '', v);
    if (Array.isArray(v)) return <ul className="space-y-1">{v.map((x, i) => <li key={i}>{spec?.item?.type === 'object' && x && typeof x === 'object'
      ? <span className="flex flex-wrap gap-x-2">{Object.entries(x as Record<string, unknown>).map(([k, val]) => <span key={k}><span className="text-muted-foreground">{k}</span> {render(val, spec.item?.fields?.[k])}</span>)}</span>
      : render(x, spec?.item)}</li>)}</ul>;
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return <span className={spec?.type === 'text' ? 'whitespace-pre-wrap' : ''}>{String(v)}</span>;
    return <span className="font-mono">{JSON.stringify(v)}</span>;
  };
  return <dl className="grid grid-cols-[minmax(6rem,auto)_1fr] gap-x-4 gap-y-2 border-y py-3 text-sm">{entries.map(([k, v]) => <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 break-words">{render(v, undefined)}</dd></div>)}</dl>;
}

/** 一个文件一页(像 Notion 的一页):标题、属性、正文。浏览、修改、新建都在这一页上,没有弹层。
 *  creating:在 dir 下新建(对象 / origin 文件),或在 object 里新建一个 kind 文件;否则打开 path(+file),点「编辑」就地改。 */
export function FilePage({ layer, path, file, creating, onClose, onOpen, onDir, work }: {
  layer: string; path?: string; file?: string; creating?: NewFile; work?: string; onClose: () => void; onOpen: (ref: FileRef) => void; onDir: (dir: string) => void;
}) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const layers = useLayers();
  const protocol = layers.data?.find(l => l.name === layer)?.protocol;
  const raw = !!protocol && !protocol.object;
  const objectPath = creating ? (creating.object || '') : (path || '');
  const rel = creating ? undefined : raw ? undefined : (file || mainFile(protocol));
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(!!creating);
  const object = useQuery({ queryKey: ['object', layer, objectPath, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(objectPath)}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }), enabled: !!objectPath });
  const history = useQuery({ queryKey: ['history', layer, objectPath], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(objectPath)}`, { signal }), enabled: !!objectPath && tab === 'history' });
  const kind = creating?.kind || (rel ? kindOf(protocol, rel) : undefined);
  const source = raw ? object.data?.content ?? '' : rel ? object.data?.files[rel] : undefined;
  const parsed = useMemo(() => { if (source === undefined) return null; if (raw) return { fields: {}, body: source, invalid: false }; try { return { ...splitFile(source), invalid: false }; } catch { return { fields: {}, body: source, invalid: true }; } }, [source, raw]);
  // ---- 编辑态:名字(新建时)、属性、正文、提交说明 ----
  const [name, setName] = useState('');
  const [fields, setFields] = useState<Record<string, unknown>>({});
  const [body, setBody] = useState(() => creating?.kind?.template || '');
  const [session, setSession] = useState(0);                                  // 每次进入编辑态 +1:正文编辑器非受控,靠 key 重新挂载拿到新内容
  const [subject, setSubject] = useState('');
  const [reason, setReason] = useState('');
  const beginEdit = () => { setFields(parsed?.fields || {}); setBody(creating ? kind?.template || '' : parsed?.body || ''); setSubject(''); setReason(''); setSession(n => n + 1); setEditing(true); };
  useEffect(() => { if (creating && protocol) beginEdit(); }, [creating, protocol]);   // eslint-disable-line react-hooks/exhaustive-deps
  // 新建时目标是什么:对象 = dir/name;对象里的文件 = instantiate(kind, name)(固定文件不用起名)
  const needName = !!creating && !(creating.object && kind?.fixed);
  const trimmed = name.trim();
  const validName = !needName || (!!trimmed && !trimmed.includes('/') && trimmed !== '..');
  const targetPath = creating ? (creating.object || [creating.dir, trimmed].filter(Boolean).join('/')) : objectPath;
  const targetRel = creating ? (creating.object ? (kind ? (kind.fixed ? kind.example : instantiate(kind, trimmed)) : '') : kind?.example) : rel;
  const content = useMemo(() => { const specs = kind?.format.fields; const out: Record<string, unknown> = {}; if (specs) for (const [k, spec] of Object.entries(specs)) { const v = normalize(spec, fields[k]); if (v !== undefined) out[k] = v; } return raw ? body : joinFile(out, body); }, [kind, fields, body, raw]);
  const payload = useMemo(() => (raw ? { content } : { files: { [targetRel || '']: content } }), [raw, content, targetRel]);
  const target = `/collections/${encodeURIComponent(layer)}/${pathPart(targetPath)}`;
  const method = creating && !creating.object ? 'POST' : 'PUT';
  const [check, setCheck] = useState<{ ok: boolean; reason?: string | null } | 'pending' | null>(null);
  useEffect(() => {
    if (!editing || !validName || !targetPath) { setCheck(null); return; }
    setCheck('pending');
    const timer = setTimeout(() => { api<{ ok: boolean; reason?: string | null }>(`${target}?dry_run=1`, { method, body: payload, work }).then(setCheck).catch((e: Error) => setCheck({ ok: false, reason: e.message })); }, 400);
    return () => clearTimeout(timer);
  }, [editing, validName, targetPath, target, method, payload, work]);
  const refresh = () => { for (const key of ['tree', 'recent', 'object', 'history', 'search']) void queryClient.invalidateQueries({ queryKey: [key] }); };
  const save = useMutation({ mutationFn: () => api<CollectionObject>(target, { method, body: { ...payload, subject: subject || undefined, reason }, work }),
    onSuccess: () => { refresh(); toast.success(creating ? t('library.created') : t('library.saved')); setEditing(false); if (creating) onOpen({ layer, path: targetPath, file: raw ? undefined : targetRel }); } });
  const remove = useMutation({ mutationFn: () => (raw || (kind?.fixed && kind.required)) ? api(`${target}?${new URLSearchParams({ reason: '' })}`, { method: 'DELETE', work }) : api(target, { method: 'PUT', body: { files: { [rel || '']: null }, reason: '' }, work }),
    onSuccess: () => { refresh(); toast.success(t('library.deleted')); onClose(); } });
  const ready = validName && check !== 'pending' && check?.ok === true && !save.isPending;
  const cancel = () => { if (creating) onClose(); else setEditing(false); };
  const ref: FileRef = { layer, path: objectPath, file: rel };
  const title = creating ? (trimmed || t('library.untitled')) : fileTitle(ref, kind);
  // 新建时预览会落到哪个路径:对象里的文件 = 对象目录/实例化的文件名;新对象 = dir/名字.layer/主文件;origin = dir/名字
  const shown = !creating ? fullPath(ref)
    : creating.object ? `${creating.object}.${layer}/${kind ? (kind.fixed ? kind.example : instantiate(kind, trimmed || '…')) : ''}`
    : `${[creating.dir, trimmed || '…'].filter(Boolean).join('/')}${protocol?.object ? `.${layer}/${targetRel || ''}` : ''}`;
  const siblings = !creating && object.data && !raw ? Object.keys(object.data.files).filter(f => f !== rel).sort() : [];
  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
      <Button variant="ghost" size="icon" className="size-8" onClick={editing ? cancel : onClose} aria-label={editing ? t('common.cancel') : t('library.back')}>{editing ? <X /> : <ArrowLeft />}</Button>
      <Badge variant="secondary">{layerLabel(t, layer)}</Badge>
      {kind && <span className="text-xs text-muted-foreground">{kind.label}</span>}
      {editing ? <>
        <span className={cn('ml-auto flex items-center gap-1.5 text-xs', check && check !== 'pending' && !check.ok ? 'text-destructive' : 'text-muted-foreground')}>{check === 'pending' ? <><LoaderCircle className="size-3.5 animate-spin" />{t('editor.checking')}</> : check?.ok ? <><Check className="size-3.5" />{t('editor.valid')}</> : check ? <span className="max-w-[40vw] truncate" title={check.reason || ''}>{check.reason}</span> : null}</span>
        <Button variant="outline" size="sm" className="h-8" onClick={cancel} disabled={save.isPending}>{t('common.cancel')}</Button>
        <Button size="sm" className="h-8" disabled={!ready} onClick={() => save.mutate()}>{save.isPending && <LoaderCircle className="animate-spin" />}{t('common.save')}</Button>
      </> : <>
        <Tabs value={tab} onValueChange={value => setTab(value as 'content' | 'history')} className="ml-auto"><TabsList className="h-8" aria-label={t('library.objectView')}><TabsTrigger value="content" className="text-xs">{t('library.tabContent')}</TabsTrigger><TabsTrigger value="history" className="gap-1 text-xs"><Clock3 className="size-3.5" />{t('library.tabHistory')}</TabsTrigger></TabsList></Tabs>
        {!revision && parsed && protocol && <Button variant="outline" size="sm" className="h-8" onClick={beginEdit}><Pencil />{t('editor.edit')}</Button>}
        {!revision && parsed && protocol && <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-destructive" aria-label={t('editor.deleteFile')} disabled={remove.isPending} onClick={() => { if (window.confirm(t('library.confirmDelete', { path: fullPath(ref) }))) remove.mutate(); }}><Trash2 /></Button>}
      </>}
    </div>
    <div className="min-h-0 flex-1 overflow-auto">{editing && protocol ? <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4 md:p-6">
      <div className="space-y-1">
        <p className="truncate font-mono text-xs text-muted-foreground">{shown}</p>
        {needName ? <Input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder={creating?.object ? kind?.name || t('library.untitled') : protocol.object ? protocol.object.name : t('library.fileName')} aria-label={t('library.fileName')} className="h-auto border-0 px-0 text-2xl font-semibold tracking-tight shadow-none focus-visible:ring-0 md:text-2xl" />
          : <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>}
      </div>
      {kind?.format.fields && <div className="border-y py-3"><FieldsForm fields={kind.format.fields} value={fields} onChange={setFields} idPrefix="file" /></div>}
      {(kind?.format.body ?? 'markdown') === 'markdown'
        ? <Suspense fallback={<Skeleton className="h-64" />}><MarkdownEditor key={session} value={body} onChange={setBody} placeholder={t('library.markdown')} className="min-h-64 rounded-md border px-3 py-1" /></Suspense>
        : <div className="grid gap-1.5"><Label htmlFor="file-body" className="sr-only">{t('editor.body')}</Label><Textarea id="file-body" className="min-h-60 resize-y font-mono text-sm" value={body} onChange={e => setBody(e.target.value)} /></div>}
      <div className="grid gap-2 sm:grid-cols-2"><div className="grid gap-2"><Label htmlFor="file-subject">{t('editor.subject')}</Label><Input id="file-subject" value={subject} onChange={e => setSubject(e.target.value)} placeholder={t('editor.subjectPlaceholder')} /></div><div className="grid gap-2"><Label htmlFor="file-reason">{t('library.reason')}</Label><Input id="file-reason" value={reason} onChange={e => setReason(e.target.value)} placeholder={t('library.reasonPlaceholder')} /></div></div>
      {check && check !== 'pending' && !check.ok && <ErrorState error={new Error(check.reason || '')} />}
      {save.isError && <ErrorState error={save.error} />}
    </div>
    : !objectPath ? null : object.isPending ? <Loading /> : object.isError ? <div className="p-4"><ErrorState error={object.error} retry={() => { void object.refetch(); }} /></div> : <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4 md:p-6">
      <div className="space-y-1"><button type="button" className="block max-w-full truncate font-mono text-xs text-muted-foreground hover:text-foreground" onClick={() => onDir(parent(fullPath(ref)))}>{fullPath(ref)}</button><h2 className="text-2xl font-semibold tracking-tight">{title}</h2></div>
      {revision && <div className="flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-xs"><Clock3 className="size-3.5" /><span>{t('library.revision', { rev: revision.slice(0, 7) })}</span><Button variant="link" size="sm" className="ml-auto h-auto p-0 text-xs" onClick={() => setRevision('')}>{t('library.backToCurrent')}</Button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <ol className="ml-1.5 space-y-4 border-l pl-5">{history.data?.map(item => <li key={item.sha} className="relative"><span className="absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-background bg-muted-foreground" /><button type="button" className="block w-full text-left" onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="block text-sm font-medium break-all">{item.subject}</span><span className="mt-1 block text-xs text-muted-foreground">{item.author} · {dateLabel(item.date, locale)} · <span className="font-mono">{item.sha.slice(0, 7)}</span></span></button></li>)}</ol>
        : parsed === null ? <Empty icon={<FileText className="size-5" />} title={t('library.noSuchFile')} />
        : <>
          {parsed.invalid && <ErrorState error={new Error(t('library.invalidMeta'))} />}
          <Properties fields={parsed.fields} protocol={protocol} onOpen={onOpen} />
          {kind?.format.body === 'text' ? <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted p-3 font-mono text-xs">{parsed.body}</pre> : <Markdown text={parsed.body} />}
          {siblings.length > 0 && <div className="space-y-1 border-t pt-4"><h4 className="text-xs font-medium text-muted-foreground">{t('library.siblings')}</h4>{siblings.map(f => <Button key={f} variant="ghost" size="sm" className="h-8 w-full justify-start gap-2 font-normal" onClick={() => onOpen({ layer, path: objectPath, file: f })}><FileText className="size-3.5 text-muted-foreground" /><span className="truncate">{fileTitle({ layer, path: objectPath, file: f }, kindOf(protocol, f))}</span><span className="ml-auto truncate font-mono text-xs text-muted-foreground">{f}</span></Button>)}</div>}
        </>}
    </div>}</div>
  </div>;
}
