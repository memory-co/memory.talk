import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, BookOpen, ChevronRight, Clock3, FileText, Folder, Layers, LoaderCircle, MessageSquare, Pencil, Plus, Search, X } from 'lucide-react';
import { toast } from 'sonner';
import { api, pathPart } from '@/lib/api';
import { cardFiles, objectView } from '@/lib/collections';
import { useLayers } from '@/lib/queries';
import { queryClient } from '@/lib/query';
import { dateLabel, flattenCatalog, layerLabels, type Catalog, type CollectionObject, type Revision, type SearchHit } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, Modal } from '@/components/Shared';

type Selection = { layer: string; path?: string };
export function Library({ layer = 'card', path, onSelect, compact = false, work }: Selection & {
  onSelect: (selection: Selection) => void; compact?: boolean; work?: string;
}) {
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
  return <Tabs value={layer} onValueChange={value => { onSelect({ layer: value }); setSearch(''); }} className={`library ${compact ? 'compact-library' : ''}`}>
    {!compact && <div className="page-heading"><div><span className="eyebrow">COLLECTIONS</span><h1>认知库</h1><p>工作中的原文、问题与结论，在这里逐渐连接。</p></div><div className="library-mark"><Layers size={25} /></div></div>}
    {(!compact || !path) && <>
      <div className="library-controls"><div className="min-w-0 overflow-x-auto"><TabsList aria-label="认知层" className="h-auto bg-transparent p-0">{(layers.data || []).map(item => <TabsTrigger key={item.name} value={item.name} className="gap-2 py-3">
        {item.name === 'card' ? <BookOpen size={15} /> : item.name === 'issue' ? <MessageSquare size={15} /> : <FileText size={15} />}{layerLabels[item.name] || item.name}
      </TabsTrigger>)}</TabsList></div>{['card', 'issue', 'origin'].includes(layer) && <Button variant="ghost" size="icon" onClick={() => setCreate(true)} aria-label={`新建${layerLabels[layer]}`} title={`新建${layerLabels[layer]}`}><Plus size={17} /></Button>}</div>
      {layers.isError && <ErrorState error={layers.error} retry={() => { void layers.refetch(); }} />}
      <div className="relative my-4 flex items-center gap-2"><Search size={16} /><Input aria-label="搜索认知库" value={search} onChange={e => setSearch(e.target.value)} placeholder={`搜索${layerLabels[layer] || layer}内容…`} />{search && <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => setSearch('')} aria-label="清空搜索"><X size={13} /></Button>}</div>
    </>}
    <TabsContent value={layer} className={`mt-0 library-body ${path ? 'has-detail' : ''}`}>
      {(!compact || !path) && <div className="catalog-pane"><div className="catalog-caption"><span>{term ? '搜索结果' : '全部内容'}</span><span>{objects.length}</span></div>
        {query.isPending ? <Loading /> : query.isError ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} /> : objects.length ? <div className="catalog-list">
          {objects.map(object => <Button variant="ghost" key={object.path} className={`catalog-item h-auto whitespace-normal ${path === object.path ? 'selected' : ''}`} onClick={() => onSelect({ layer, path: object.path })}>
            <span className={`object-icon ${layer}`}>{layer === 'card' ? <BookOpen size={17} /> : layer === 'issue' ? <MessageSquare size={17} /> : <FileText size={17} />}</span>
            <span className="catalog-item-text"><strong>{object.title || object.path.split('/').pop()}</strong><span>{object.path.includes('/') ? object.path.slice(0, object.path.lastIndexOf('/')) : '根目录'}</span></span><ChevronRight size={15} />
          </Button>)}
        </div> : <Empty icon={term ? <Search size={24} /> : <Folder size={24} />} title={term ? '没有找到相关内容' : `还没有${layerLabels[layer] || '内容'}`}><p>{term ? '试试更短的关键词，或切换其他层。' : '从一份原文、一个问题或一条结论开始。'}</p>{!term && ['card', 'issue', 'origin'].includes(layer) && <Button variant="outline" size="sm" onClick={() => setCreate(true)}>创建第一条内容</Button>}</Empty>}
        {definition && !compact && <div className="layer-description"><Layers size={14} /><span>{definition.description}</span></div>}
      </div>}
      {path && <div className="object-pane"><ObjectDetail key={`${layer}/${path}`} layer={layer} path={path} work={work} onSelect={onSelect} onClose={() => onSelect({ layer })} /></div>}
    </TabsContent>
    <ObjectEditor layer={layer} open={create} onClose={() => setCreate(false)} work={work} onSaved={objectPath => { setCreate(false); onSelect({ layer, path: objectPath }); }} />
  </Tabs>;
}

function asObject(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function text(value: unknown) { return typeof value === 'string' ? value : ''; }

export function ObjectDetail({ layer, path, onClose, onSelect, work }: {
  layer: string; path: string; work?: string; onClose: () => void; onSelect: (s: Selection) => void;
}) {
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(false);
  const object = useQuery({ queryKey: ['object', layer, path, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(path)}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }) });
  const history = useQuery({ queryKey: ['history', layer, path], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(path)}`, { signal }), enabled: tab === 'history' });
  const body = objectView(object.data);
  return <Tabs value={tab} onValueChange={value => setTab(value as 'content' | 'history')} className="flex min-h-0 flex-1 flex-col">
    <div className="object-toolbar"><Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={onClose} aria-label="返回目录"><ArrowLeft size={16} /></Button><Badge variant="secondary">{layerLabels[layer] || layer}</Badge>
      <div className="ml-auto"><TabsList aria-label="对象视图"><TabsTrigger value="content">内容</TabsTrigger><TabsTrigger value="history" className="gap-1"><Clock3 size={13} />历史</TabsTrigger></TabsList></div>
      {layer === 'card' && !revision && object.data && <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => setEditing(true)} aria-label="编辑卡片"><Pencil size={15} /></Button>}
    </div>
    <TabsContent value={tab} className="mt-0 flex min-h-0 flex-1 flex-col">{object.isPending ? <Loading /> : object.isError ? <ErrorState error={object.error} retry={() => { void object.refetch(); }} /> : <div className="object-scroll">
      <div className="object-heading"><p className="object-path">{path}</p><h2>{object.data.title || path.split('/').pop()}</h2></div>
      {!!body.invalidMeta && <ErrorState error={new Error('元数据无法解析，当前显示原始正文。')} />}
      {revision && <div className="revision-banner"><Clock3 size={14} /><span>历史版本 {revision.slice(0, 7)}</span><Button variant="link" size="sm" onClick={() => setRevision('')}>回到当前版本</Button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <div className="history-list">{history.data?.map(item => <Button variant="ghost" className="block h-auto whitespace-normal px-0 hover:bg-transparent" key={item.sha} onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="history-point" /><strong>{item.subject}</strong><span>{item.author} · {dateLabel(item.date)} · {item.sha.slice(0, 7)}</span></Button>)}</div>
        : layer === 'card' ? <>
          {text(body.context) && <p className="card-context">{text(body.context)}</p>}
          <Markdown text={text(body.body)} />
          {text(body.issue) && <Button variant="ghost" className="related-link h-auto whitespace-normal" onClick={() => onSelect({ layer: 'issue', path: text(body.issue) })}><MessageSquare size={16} /><span>查看这张卡片的讨论</span><ArrowUpRight size={15} /></Button>}
          {Array.isArray(body.links) && body.links.length > 0 && <div className="related-links"><h4>相关卡片</h4>{body.links.filter(link => typeof link === 'string').map(link => <Button variant="ghost" key={String(link)} onClick={() => onSelect({ layer: 'card', path: String(link) })}><BookOpen size={14} />{String(link)}</Button>)}</div>}
        </> : layer === 'issue' ? <>
          <Markdown text={text(body.readme)} />
          {text(body.summary) && <div className="issue-summary"><span className="eyebrow">当前判断</span><Markdown text={text(body.summary)} /></div>}
          <h3 className="content-section-title">立场与论证 <span>{Array.isArray(body.positions) ? body.positions.length : 0}</span></h3>
          {Array.isArray(body.positions) && body.positions.map((value, i) => { const position = asObject(value); return <Card className="mb-3 p-4 shadow-none" key={i}><div className="position-heading"><span>{String(i + 1).padStart(2, '0')}</span><h4>{text(position.claim)}</h4></div>{text(position.note) && <p className="position-note">{text(position.note)}</p>}<Markdown text={text(position.body)} /></Card>; })}
          {Array.isArray(body.links) && body.links.map((value, i) => { const link = asObject(value); return <Button variant="ghost" className="related-link h-auto whitespace-normal" key={i} onClick={() => onSelect({ layer: 'issue', path: text(link.target).split('#')[0] })}><MessageSquare size={15} /><span>{text(link.target)}</span><small>{text(link.type)}</small></Button>; })}
        </> : layer === 'origin' ? <Markdown text={object.data.content || ''} /> : <div className="generic-files">{Object.entries(object.data.files).map(([name, value]) => <section key={name}><h3><FileText size={14} />{name}</h3>{name.endsWith('.md') ? <Markdown text={value} /> : <pre>{value}</pre>}</section>)}</div>}
    </div>}
    </TabsContent>
    <ObjectEditor layer={layer} path={path} initial={object.data} open={editing} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} work={work} />
  </Tabs>;
}

function ObjectEditor({ layer, path, initial, open, onClose, onSaved, work }: {
  layer: string; path?: string; initial?: CollectionObject; open: boolean; onClose: () => void; onSaved: (path: string) => void; work?: string;
}) {
  const [objectPath, setObjectPath] = useState(path || '');
  const [content, setContent] = useState('');
  const [context, setContext] = useState('');
  const [reason, setReason] = useState('');
  useEffect(() => { if (open) { const view = objectView(initial); setObjectPath(path || ''); setContent(initial?.files['readme.md'] || ''); setContext(text(view.context)); setReason(''); } }, [open, path]);
  const mutation = useMutation({ mutationFn: () => {
    const payload = layer === 'origin' ? { content } : layer === 'issue' ? { files: { 'readme.md': content } } : { files: cardFiles(content, context, initial?.files) };
    return api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(objectPath.trim())}`, { method: path ? 'PUT' : 'POST', body: { ...payload, reason }, work });
  }, onSuccess: () => { for (const key of ['catalog', 'object', 'history', 'search']) void queryClient.invalidateQueries({ queryKey: [key] }); toast.success(path ? '内容已保存' : '内容已创建'); onSaved(objectPath.trim()); } });
  const valid = !!objectPath.trim() && !objectPath.split('/').some(p => !p.trim() || p === '..');
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={`${path ? '编辑' : '新建'}${layerLabels[layer] || layer}`} description="每次保存都会留下可追溯的版本历史。">
    <form className="form-stack" onSubmit={e => { e.preventDefault(); if (valid) mutation.mutate(); }}>
      {!path && <Label>{layer === 'origin' ? '保存路径' : '保存路径（最后一段为标题）'}<Input autoFocus value={objectPath} onChange={e => setObjectPath(e.target.value)} placeholder="项目/主题/名称" required /></Label>}
      {layer === 'card' && <Label>适用语境<Input value={context} onChange={e => setContext(e.target.value)} placeholder="关于哪个项目、场景或约定" /></Label>}
      <Label>{layer === 'issue' ? '问题描述' : '正文'}<Textarea aria-label={layer === 'issue' ? '问题描述' : '正文'} className="editor-textarea" value={content} onChange={e => setContent(e.target.value)} placeholder="支持 Markdown" /></Label>
      <Label>修改说明（可选）<Input value={reason} onChange={e => setReason(e.target.value)} placeholder="为什么记录或修改这条内容" /></Label>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <div className="form-actions"><Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>取消</Button><Button variant="default" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}保存</Button></div>
    </form>
  </Modal>;
}
