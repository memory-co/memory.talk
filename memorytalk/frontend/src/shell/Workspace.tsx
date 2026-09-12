import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BookOpen, ExternalLink, GitBranch, LoaderCircle, Plus, Terminal } from 'lucide-react';
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
      <div className="work-controls"><Select value={work.data.status} disabled={update.isPending} onValueChange={value => update.mutate(value as WorkStatus)}><SelectTrigger aria-label="工作状态" className="w-28"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(statusLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select>
        <Button variant="outline" size="sm" onClick={() => setSubwork(true)} disabled={ended}><GitBranch size={14} />拆分工作</Button></div>
    </div>
    <Tabs value={selected?.id || ""} onValueChange={value => selectSession(id, value)} className="flex min-h-0 flex-1 flex-col"><div className="session-tabs" aria-label="工作会话">
      <TabsList className="h-auto min-w-0 justify-start overflow-x-auto bg-transparent p-0" aria-label="会话切换">{sessions.data?.map((session, index) => <TabsTrigger key={session.id} value={session.id} className="gap-2 px-3 py-3">
        {['http', 'https'].includes(session.scheme) ? <ExternalLink size={14} /> : <Terminal size={14} />}
        {sessionLabels[session.scheme] || session.scheme}<span className="session-number">{index + 1}</span><span className={`session-dot ${session.alive ? 'alive' : ''}`} title={session.alive ? '运行中' : '未运行'} />
      </TabsTrigger>)}</TabsList>
      <Button variant="ghost" size="icon" onClick={() => setAdding(true)} disabled={ended} aria-label="添加会话" title="添加会话"><Plus size={17} /></Button>
    </div>
    {sessions.isPending ? <Loading /> : sessions.isError ? <ErrorState error={sessions.error} retry={() => { void sessions.refetch(); }} /> : selected
      ? <TabsContent key={selected.id} value={selected.id} className="mt-0 flex min-h-0 flex-1 flex-col"><PanelView work={work.data} session={selected} /></TabsContent>
      : <Empty icon={<Terminal size={28} />} title={ended ? '这项工作已结束' : '准备好，开始这项工作'}>
        <p>{ended ? '你仍可以查阅相关认知，或重新开启工作。' : '添加一个 agent、终端或网页，让思路开始落地。'}</p>
        <div className="empty-actions">{!ended && <Button variant="default" onClick={() => setAdding(true)}><Plus size={16} />添加会话</Button>}<Button variant="outline" onClick={onLibrary}><BookOpen size={16} />查看认知库</Button></div>
      </Empty>}
    </Tabs>
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
      <div className="space-y-2"><Label htmlFor="session-scheme">会话类型</Label><Select value={scheme} onValueChange={value => { setScheme(value); setPath(''); mutation.reset(); }}><SelectTrigger id="session-scheme"><SelectValue /></SelectTrigger><SelectContent>
        {(protocols.length ? protocols : ['bash', 'codex', 'claude', 'kimi', 'https']).map(p => <SelectItem value={p} key={p}>{sessionLabels[p] || p}</SelectItem>)}<SelectItem value="custom">自定义 URI</SelectItem>
      </SelectContent></Select></div>
      {scheme === 'custom' ? <Label>URI<Input autoFocus placeholder="vim:///home/me/notes.md" value={custom} onChange={e => setCustom(e.target.value)} /></Label>
        : <Label>{isWeb ? '网页地址' : '工作目录（可选）'}<Input placeholder={isWeb ? 'https://example.com' : '留空使用默认工作目录'} value={path} onChange={e => setPath(e.target.value)} /></Label>}
      {!valid && <p className="field-hint">{isWeb ? '请输入以 http:// 或 https:// 开头的地址。' : scheme === 'custom' ? '请输入带协议的完整 URI。' : '工作目录需要使用以 / 开头的绝对路径。'}</p>}
      {mutation.isError && <ErrorState error={mutation.error} />}
      <div className="form-actions"><Button variant="default" type="submit" disabled={!valid || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}{mutation.isPending ? '正在建立会话…' : '打开会话'}</Button></div>
    </form>
  </Modal>;
}
