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
  return <div className={`library ${compact ? 'compact-library' : ''}`}>
    {!compact && <div className="page-heading"><div><span className="eyebrow">COLLECTIONS</span><h1>认知库</h1><p>工作中的原文、问题与结论，在这里逐渐连接。</p></div><div className="library-mark"><Layers size={25} /></div></div>}
    {(!compact || !path) && <>
      <div className="library-controls"><div className="layer-tabs" aria-label="认知层">{(layers.data || []).map(item => <button key={item.name} className={item.name === layer ? 'active' : ''} onClick={() => { onSelect({ layer: item.name }); setSearch(''); }}>
        {item.name === 'card' ? <BookOpen size={15} /> : item.name === 'issue' ? <MessageSquare size={15} /> : <FileText size={15} />}{layerLabels[item.name] || item.name}
      </button>)}</div>{['card', 'issue', 'origin'].includes(layer) && <button className="icon-button" onClick={() => setCreate(true)} aria-label={`新建${layerLabels[layer]}`} title={`新建${layerLabels[layer]}`}><Plus size={17} /></button>}</div>
      {layers.isError && <ErrorState error={layers.error} retry={() => { void layers.refetch(); }} />}
      <div className="library-search"><Search size={16} /><input aria-label="搜索认知库" value={search} onChange={e => setSearch(e.target.value)} placeholder={`搜索${layerLabels[layer] || layer}内容…`} />{search && <button className="icon-button small" onClick={() => setSearch('')} aria-label="清空搜索"><X size={13} /></button>}</div>
    </>}
    <div className={`library-body ${path ? 'has-detail' : ''}`}>
      {(!compact || !path) && <div className="catalog-pane"><div className="catalog-caption"><span>{term ? '搜索结果' : '全部内容'}</span><span>{objects.length}</span></div>
        {query.isPending ? <Loading /> : query.isError ? <ErrorState error={query.error} retry={() => { void query.refetch(); }} /> : objects.length ? <div className="catalog-list">
          {objects.map(object => <button key={object.path} className={`catalog-item ${path === object.path ? 'selected' : ''}`} onClick={() => onSelect({ layer, path: object.path })}>
            <span className={`object-icon ${layer}`}>{layer === 'card' ? <BookOpen size={17} /> : layer === 'issue' ? <MessageSquare size={17} /> : <FileText size={17} />}</span>
            <span className="catalog-item-text"><strong>{object.title || object.path.split('/').pop()}</strong><span>{object.path.includes('/') ? object.path.slice(0, object.path.lastIndexOf('/')) : '根目录'}</span></span><ChevronRight size={15} />
          </button>)}
        </div> : <Empty icon={term ? <Search size={24} /> : <Folder size={24} />} title={term ? '没有找到相关内容' : `还没有${layerLabels[layer] || '内容'}`}><p>{term ? '试试更短的关键词，或切换其他层。' : '从一份原文、一个问题或一条结论开始。'}</p>{!term && ['card', 'issue', 'origin'].includes(layer) && <button className="button secondary small" onClick={() => setCreate(true)}>创建第一条内容</button>}</Empty>}
        {definition && !compact && <div className="layer-description"><Layers size={14} /><span>{definition.description}</span></div>}
      </div>}
      {path && <div className="object-pane"><ObjectDetail key={`${layer}/${path}`} layer={layer} path={path} work={work} onSelect={onSelect} onClose={() => onSelect({ layer })} /></div>}
    </div>
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
  const [tab, setTab] = useState<'content' | 'history'>('content');
  const [revision, setRevision] = useState('');
  const [editing, setEditing] = useState(false);
  const object = useQuery({ queryKey: ['object', layer, path, revision], queryFn: ({ signal }) => api<CollectionObject>(`/collections/${encodeURIComponent(layer)}/${pathPart(path)}${revision ? `?rev=${encodeURIComponent(revision)}` : ''}`, { signal }) });
  const history = useQuery({ queryKey: ['history', layer, path], queryFn: ({ signal }) => api<Revision[]>(`/collections/history/${encodeURIComponent(layer)}/${pathPart(path)}`, { signal }), enabled: tab === 'history' });
  const body = objectView(object.data);
  return <>
    <div className="object-toolbar"><button className="icon-button small" onClick={onClose} aria-label="返回目录"><ArrowLeft size={16} /></button><span className="layer-label">{layerLabels[layer] || layer}</span>
      <div className="object-tabs"><button className={tab === 'content' ? 'active' : ''} onClick={() => setTab('content')}>内容</button><button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}><Clock3 size={13} />历史</button></div>
      {layer === 'card' && !revision && object.data && <button className="icon-button small" onClick={() => setEditing(true)} aria-label="编辑卡片"><Pencil size={15} /></button>}
    </div>
    {object.isPending ? <Loading /> : object.isError ? <ErrorState error={object.error} retry={() => { void object.refetch(); }} /> : <div className="object-scroll">
      <div className="object-heading"><p className="object-path">{path}</p><h2>{object.data.title || path.split('/').pop()}</h2></div>
      {!!body.invalidMeta && <ErrorState error={new Error('元数据无法解析，当前显示原始正文。')} />}
      {revision && <div className="revision-banner"><Clock3 size={14} /><span>历史版本 {revision.slice(0, 7)}</span><button className="text-button" onClick={() => setRevision('')}>回到当前版本</button></div>}
      {tab === 'history' ? history.isPending ? <Loading /> : history.isError ? <ErrorState error={history.error} /> : <div className="history-list">{history.data?.map(item => <button key={item.sha} onClick={() => { setRevision(item.sha); setTab('content'); }}><span className="history-point" /><strong>{item.subject}</strong><span>{item.author} · {dateLabel(item.date)} · {item.sha.slice(0, 7)}</span></button>)}</div>
        : layer === 'card' ? <>
          {text(body.context) && <p className="card-context">{text(body.context)}</p>}
          <Markdown text={text(body.body)} />
          {text(body.issue) && <button className="related-link" onClick={() => onSelect({ layer: 'issue', path: text(body.issue) })}><MessageSquare size={16} /><span>查看这张卡片的讨论</span><ArrowUpRight size={15} /></button>}
          {Array.isArray(body.links) && body.links.length > 0 && <div className="related-links"><h4>相关卡片</h4>{body.links.filter(link => typeof link === 'string').map(link => <button key={String(link)} onClick={() => onSelect({ layer: 'card', path: String(link) })}><BookOpen size={14} />{String(link)}</button>)}</div>}
        </> : layer === 'issue' ? <>
          <Markdown text={text(body.readme)} />
          {text(body.summary) && <div className="issue-summary"><span className="eyebrow">当前判断</span><Markdown text={text(body.summary)} /></div>}
          <h3 className="content-section-title">立场与论证 <span>{Array.isArray(body.positions) ? body.positions.length : 0}</span></h3>
          {Array.isArray(body.positions) && body.positions.map((value, i) => { const position = asObject(value); return <article className="position-card" key={i}><div className="position-heading"><span>{String(i + 1).padStart(2, '0')}</span><h4>{text(position.claim)}</h4></div>{text(position.note) && <p className="position-note">{text(position.note)}</p>}<Markdown text={text(position.body)} /></article>; })}
          {Array.isArray(body.links) && body.links.map((value, i) => { const link = asObject(value); return <button className="related-link" key={i} onClick={() => onSelect({ layer: 'issue', path: text(link.target).split('#')[0] })}><MessageSquare size={15} /><span>{text(link.target)}</span><small>{text(link.type)}</small></button>; })}
        </> : layer === 'origin' ? <Markdown text={object.data.content || ''} /> : <div className="generic-files">{Object.entries(object.data.files).map(([name, value]) => <section key={name}><h3><FileText size={14} />{name}</h3>{name.endsWith('.md') ? <Markdown text={value} /> : <pre>{value}</pre>}</section>)}</div>}
    </div>}
    <ObjectEditor layer={layer} path={path} initial={object.data} open={editing} onClose={() => setEditing(false)} onSaved={() => setEditing(false)} work={work} />
  </>;
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
      {!path && <label>{layer === 'origin' ? '保存路径' : '保存路径（最后一段为标题）'}<input autoFocus value={objectPath} onChange={e => setObjectPath(e.target.value)} placeholder="项目/主题/名称" required /></label>}
      {layer === 'card' && <label>适用语境<input value={context} onChange={e => setContext(e.target.value)} placeholder="关于哪个项目、场景或约定" /></label>}
      <label>{layer === 'issue' ? '问题描述' : '正文'}<textarea className="editor-textarea" value={content} onChange={e => setContent(e.target.value)} placeholder="支持 Markdown" /></label>
      <label>修改说明（可选）<input value={reason} onChange={e => setReason(e.target.value)} placeholder="为什么记录或修改这条内容" /></label>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <div className="form-actions"><button type="button" className="button secondary" onClick={onClose} disabled={mutation.isPending}>取消</button><button className="button primary" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}保存</button></div>
    </form>
  </Modal>;
}
