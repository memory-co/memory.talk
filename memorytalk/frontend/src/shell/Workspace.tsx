import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BookOpen, ChevronDown, ExternalLink, GitBranch, LoaderCircle, Plus, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useServers, useWork } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { sessionLabels, statusLabels, type Session, type Work, type WorkStatus } from '@/lib/types';
import { Empty, ErrorState, Loading, Modal } from '@/components/Shared';
import { NewSubwork } from './Home';
import { PanelView } from './PanelView';

export function Workspace({ id, onLibrary }: { id: string; onLibrary: () => void }) {
  const work = useWork(id);
  const sessions = useQuery({ queryKey: ['sessions', id], queryFn: ({ signal }) => api<Session[]>(`/works/${encodeURIComponent(id)}/sessions`, { signal }), refetchInterval: 8_000 });
  const selectedId = usePreferences(s => s.sessions[id]);
  const selectSession = usePreferences(s => s.selectSession);
  const [adding, setAdding] = useState(false);
  const [subwork, setSubwork] = useState(false);
  const selected = sessions.data?.find(s => s.id === selectedId) || sessions.data?.[0];
  const update = useMutation({ mutationFn: (status: WorkStatus) => api<Work>(`/works/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status } }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['work', id] }); void queryClient.invalidateQueries({ queryKey: ['works'] }); void queryClient.invalidateQueries({ queryKey: ['sessions', id] }); },
    onError: (error: Error) => toast.error(error.message),
  });
  if (work.isPending) return <Loading />;
  if (work.isError) return <ErrorState error={work.error} retry={() => { void work.refetch(); }} />;
  const ended = ['done', 'abandoned'].includes(work.data.status);
  return <div className="workspace">
    <div className="work-heading"><div className="work-title"><span className="eyebrow">WORKSPACE</span><h1>{work.data.goal}</h1></div>
      <div className="work-controls"><label className={`status-select ${work.data.status}`}><span className="sr-only">工作状态</span><i /><select aria-label="工作状态" value={work.data.status} disabled={update.isPending} onChange={e => update.mutate(e.target.value as WorkStatus)}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><ChevronDown size={12} /></label>
        <button className="button secondary small" onClick={() => setSubwork(true)} disabled={ended}><GitBranch size={14} />拆分工作</button></div>
    </div>
    <div className="session-tabs" aria-label="工作会话">
      <div className="session-tab-list" role="tablist" aria-label="会话切换">{sessions.data?.map((session, index) => <button key={session.id} role="tab" aria-selected={session.id === selected?.id} className={`session-tab ${session.id === selected?.id ? 'active' : ''}`} onClick={() => selectSession(id, session.id)}>
        {['http', 'https'].includes(session.scheme) ? <ExternalLink size={14} /> : <Terminal size={14} />}
        {sessionLabels[session.scheme] || session.scheme}<span className="session-number">{index + 1}</span><span className={`session-dot ${session.alive ? 'alive' : ''}`} title={session.alive ? '运行中' : '未运行'} />
      </button>)}</div>
      <button className="icon-button" onClick={() => setAdding(true)} disabled={ended} aria-label="添加会话" title="添加会话"><Plus size={17} /></button>
    </div>
    {sessions.isPending ? <Loading /> : sessions.isError ? <ErrorState error={sessions.error} retry={() => { void sessions.refetch(); }} /> : selected
      ? <PanelView key={selected.id} work={work.data} session={selected} />
      : <Empty icon={<Terminal size={28} />} title={ended ? '这项工作已结束' : '准备好，开始这项工作'}>
        <p>{ended ? '你仍可以查阅相关认知，或重新开启工作。' : '添加一个 agent、终端或网页，让思路开始落地。'}</p>
        <div className="empty-actions">{!ended && <button className="button primary" onClick={() => setAdding(true)}><Plus size={16} />添加会话</button>}<button className="button secondary" onClick={onLibrary}><BookOpen size={16} />查看认知库</button></div>
      </Empty>}
    <AttachDialog id={id} open={adding} onClose={() => setAdding(false)} />
    <NewSubwork parent={id} open={subwork} onClose={() => setSubwork(false)} />
  </div>;
}

function AttachDialog({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const servers = useServers();
  const [scheme, setScheme] = useState('bash');
  const [path, setPath] = useState('');
  const [custom, setCustom] = useState('');
  const selectSession = usePreferences(s => s.selectSession);
  const mutation = useMutation({ mutationFn: () => {
    const raw = scheme === 'custom' ? custom.trim() : ['http', 'https'].includes(scheme)
      ? path.trim() : `${scheme}://${path.trim() ? encodeURI(path.trim()) : ''}`;
    return api<Session>(`/works/${encodeURIComponent(id)}/sessions`, { method: 'POST', body: { uri: raw } });
  }, onSuccess: session => {
    queryClient.setQueryData(['live', id, session.id], session);
    selectSession(id, session.id); void queryClient.invalidateQueries({ queryKey: ['sessions', id] }); onClose(); setPath(''); setCustom(''); toast.success('会话已添加');
  } });
  const protocols = [...new Set(servers.data?.flatMap(s => s.protocols) || [])].filter(p => p !== 'http');
  const isWeb = scheme === 'https' || scheme === 'http';
  const valid = scheme === 'custom' ? /^[a-z][a-z0-9+.-]*:\/\//i.test(custom.trim()) : isWeb ? /^https?:\/\//.test(path.trim()) : !path.trim() || path.trim().startsWith('/');
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title="添加一个会话" description="同一个工作可以容纳多个现场，切换页面不会结束会话。">
    <form className="form-stack" onSubmit={e => { e.preventDefault(); if (valid) mutation.mutate(); }}>
      <label>会话类型<select value={scheme} onChange={e => { setScheme(e.target.value); setPath(''); mutation.reset(); }}>
        {(protocols.length ? protocols : ['bash', 'codex', 'claude', 'kimi', 'https']).map(p => <option value={p} key={p}>{sessionLabels[p] || p}</option>)}<option value="custom">自定义 URI</option>
      </select></label>
      {scheme === 'custom' ? <label>URI<input autoFocus placeholder="vim:///home/me/notes.md" value={custom} onChange={e => setCustom(e.target.value)} /></label>
        : <label>{isWeb ? '网页地址' : '工作目录（可选）'}<input placeholder={isWeb ? 'https://example.com' : '留空使用默认工作目录'} value={path} onChange={e => setPath(e.target.value)} /></label>}
      {!valid && <p className="field-hint">{isWeb ? '请输入以 http:// 或 https:// 开头的地址。' : scheme === 'custom' ? '请输入带协议的完整 URI。' : '工作目录需要使用以 / 开头的绝对路径。'}</p>}
      {mutation.isError && <ErrorState error={mutation.error} />}
      <div className="form-actions"><button className="button primary" type="submit" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}{mutation.isPending ? '正在建立会话…' : '打开会话'}</button></div>
    </form>
  </Modal>;
}
