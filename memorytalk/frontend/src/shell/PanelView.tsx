import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, Copy, ExternalLink, FileText, LoaderCircle, Play, RefreshCw, Terminal, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem } from '@/lib/queries';
import { navigate } from '@/lib/router';
import type { Round, Session, Work } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, Modal, safeWindowUrl } from '@/components/Shared';

export function PanelView({ work, session }: { work: Work; session: Session }) {
  const [mode, setMode] = useState<'terminal' | 'rounds'>('terminal');
  const [confirm, setConfirm] = useState(false);
  const [copied, setCopied] = useState(false);
  const system = useSystem();
  const base = `/works/${encodeURIComponent(work.id)}/sessions/${encodeURIComponent(session.id)}`;
  const ended = ['done', 'abandoned'].includes(work.status);
  const web = ['http', 'https'].includes(session.scheme);
  const agent = ['codex', 'claude', 'kimi'].includes(session.scheme);
  const live = useQuery<Session>({ queryKey: ['live', work.id, session.id], enabled: false });
  const connect = useMutation({ mutationFn: () => api<Session>(`${base}/attach`, { method: 'POST' }),
    onSuccess: data => { queryClient.setQueryData(['live', work.id, session.id], data); void queryClient.invalidateQueries({ queryKey: ['sessions', work.id] }); },
    onError: (error: Error) => toast.error(error.message),
  });
  const ttyd = system.data?.ttyd_url;
  const terminalUrl = live.data?.window?.embed || session.window?.embed || (ttyd ? `${ttyd.replace(/\/$/, '')}/?arg=${encodeURIComponent(session.id)}` : null);
  const url = safeWindowUrl(web ? session.uri : terminalUrl);
  const capture = useQuery({ queryKey: ['capture', work.id, session.id], queryFn: ({ signal }) => api<string>(`${base}/capture`, { signal }),
    enabled: !web && !ended && session.alive && mode === 'terminal' && !url, refetchInterval: 4_000,
  });
  const rounds = useQuery({ queryKey: ['rounds', work.id, session.id], queryFn: ({ signal }) => api<Round[]>(`${base}/rounds`, { signal }),
    enabled: agent && (mode === 'rounds' || ended), refetchInterval: ended ? false : 4_000,
  });
  const remove = useMutation({ mutationFn: () => api(`${base}`, { method: 'DELETE' }), onSuccess: () => {
    for (const key of ['live', 'capture', 'rounds']) queryClient.removeQueries({ queryKey: [key, work.id, session.id] });
    void queryClient.invalidateQueries({ queryKey: ['sessions', work.id] }); setConfirm(false); toast.success('会话已关闭');
  }, onError: (error: Error) => toast.error(error.message) });
  const copy = async () => {
    try { await navigator.clipboard.writeText(session.uri); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { toast.error('无法访问剪贴板，请手动复制会话地址。'); }
  };
  return <div className="session-view" role="tabpanel" aria-label="当前会话">
    <div className="session-toolbar"><span className="session-address" title={session.uri}>{web ? <ExternalLink size={13} /> : <Terminal size={13} />}{session.cwd || session.uri}</span>
      <div className="session-toolbar-actions">{agent && !ended && <div className="segmented"><button className={mode === 'terminal' ? 'active' : ''} onClick={() => setMode('terminal')}>终端</button><button className={mode === 'rounds' ? 'active' : ''} onClick={() => setMode('rounds')}>对话记录</button></div>}
        <button className="icon-button small" onClick={() => { void copy(); }} aria-label="复制会话地址">{copied ? <Check size={14} /> : <Copy size={14} />}</button>
        {url && !ended && <a className="icon-button small" href={url} target="_blank" rel="noopener noreferrer" aria-label="在新窗口打开"><ExternalLink size={14} /></a>}
        {!ended && <button className="icon-button small danger-hover" onClick={() => setConfirm(true)} aria-label="结束并移除会话"><Trash2 size={14} /></button>}
      </div>
    </div>
    {(mode === 'rounds' || ended) && agent ? <div className="transcript-scroll">
      <div className="transcript-note"><FileText size={14} />{ended ? '工作已结束 · 会话记录' : '会话记录自动更新 · 请在终端中与 agent 交互'}</div>
      {rounds.isPending ? <Loading /> : rounds.isError ? <ErrorState error={rounds.error} retry={() => { void rounds.refetch(); }} /> : rounds.data?.length ? <div className="transcript">
        {rounds.data.map(round => <article key={round.id} className={`message ${round.role === 'human' ? 'human' : round.role === 'tool' ? 'tool' : 'assistant'}`}>
          <div className="message-meta"><strong>{round.role === 'human' ? '你' : round.role === 'tool' ? '工具' : session.scheme}</strong>{round.timestamp && <time>{new Date(round.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time>}</div>
          {round.role === 'tool' ? <details><summary>查看工具输出</summary><pre>{round.text}</pre></details> : <Markdown text={round.text} />}
        </article>)}
      </div> : <Empty icon={<FileText size={26} />} title="还没有对话记录"><p>在终端中开始对话后，记录会显示在这里。</p></Empty>}
    </div> : ended ? <Empty icon={<Check size={26} />} title="现场已结束"><p>工作已归档，终端不再运行。</p></Empty>
      : !session.alive && !web ? <Empty icon={<Terminal size={28} />} title="这个会话暂未运行"><p>重新连接，继续当前工作。</p><button className="button primary" disabled={connect.isPending} onClick={() => connect.mutate()}>{connect.isPending ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />}重新连接</button></Empty>
      : url ? <div className="embedded-view">{web && <div className="embed-note">若网页不允许嵌入，可在右上角的新窗口中打开。</div>}<iframe title={`${session.scheme} 会话`} src={url} referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write" /></div>
      : <div className="snapshot-view"><div className="snapshot-label"><span><span className="live-dot" /> 终端快照 · 只读</span><button className="icon-button small" aria-label="刷新终端快照" onClick={() => { void capture.refetch(); }}><RefreshCw size={14} /></button></div>
        {capture.isPending ? <Loading /> : capture.isError ? <ErrorState error={capture.error} retry={() => { void capture.refetch(); }} /> : <pre className="terminal-output">{capture.data || '终端正在运行，等待输出…'}</pre>}
        <div className="terminal-notice"><Terminal size={17} /><div><strong>连接浏览器终端，直接在这里操作</strong><p>当前可以查看输出。配置 ttyd 后，即可在页面中输入和操作。</p></div><button className="button secondary small" onClick={() => navigate({ page: 'settings' })}>查看接入方式</button></div>
      </div>}
    <Modal open={confirm} onClose={() => { if (!remove.isPending) setConfirm(false); }} title="结束这个会话？" description="这会停止会话进程并移除登记。只想切换工作时，直接选择其他工作即可，无需关闭会话。">
      <div className="form-actions"><button className="button secondary" onClick={() => setConfirm(false)}>保留会话</button><button className="button destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>{remove.isPending ? '正在结束…' : '结束会话'}</button></div>
    </Modal>
  </div>;
}
