import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, Copy, ExternalLink, FileText, LoaderCircle, Play, RefreshCw, Terminal, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem } from '@/lib/queries';
import { navigate } from '@/lib/router';
import { usePreferences } from '@/lib/store';
import { localeTag, useT } from '@/lib/i18n';
import type { Round, Session, Work } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, safeWindowUrl } from '@/components/Shared';

export function PanelView({ work, session }: { work: Work; session: Session }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const focus = useDialogFocus();
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
    void queryClient.invalidateQueries({ queryKey: ['sessions', work.id] }); setConfirm(false); toast.success(t('session.closed'));
  }, onError: (error: Error) => toast.error(error.message) });
  const copy = async () => {
    try { await navigator.clipboard.writeText(session.uri); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { toast.error(t('session.clipboardFailed')); }
  };
  return <Tabs value={ended && agent ? "rounds" : mode} onValueChange={value => setMode(value as 'terminal' | 'rounds')} className="session-view" aria-label={t('session.current')}>
    <div className="session-toolbar"><span className="session-address" title={session.uri}>{web ? <ExternalLink size={13} /> : <Terminal size={13} />}{session.cwd || session.uri}</span>
      <div className="session-toolbar-actions">{agent && !ended && <TabsList aria-label={t('session.view')}><TabsTrigger value="terminal">{t('session.terminal')}</TabsTrigger><TabsTrigger value="rounds">{t('session.transcript')}</TabsTrigger></TabsList>}
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" onClick={() => { void copy(); }} aria-label={t('session.copy')}>{copied ? <Check size={14} /> : <Copy size={14} />}</Button>
        {url && !ended && <Button asChild variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground"><a href={url} target="_blank" rel="noopener noreferrer" aria-label={t('session.openWindow')}><ExternalLink size={14} /></a></Button>}
        {!ended && <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => setConfirm(true)} aria-label={t('session.remove')}><Trash2 size={14} /></Button>}
      </div>
    </div>
    <TabsContent value={ended && agent ? 'rounds' : mode} className="mt-0 flex min-h-0 flex-1 flex-col">{(mode === 'rounds' || ended) && agent ? <div className="transcript-scroll">
      <div className="transcript-note"><FileText size={14} />{ended ? t('session.transcriptEnded') : t('session.transcriptLive')}</div>
      {rounds.isPending ? <Loading /> : rounds.isError ? <ErrorState error={rounds.error} retry={() => { void rounds.refetch(); }} /> : rounds.data?.length ? <div className="transcript">
        {rounds.data.map(round => <article key={round.id} className={`message ${round.role === 'human' ? 'human' : round.role === 'tool' ? 'tool' : 'assistant'}`}>
          <div className="message-meta"><strong>{round.role === 'human' ? t('session.you') : round.role === 'tool' ? t('session.tool') : session.scheme}</strong>{round.timestamp && <time>{new Date(round.timestamp).toLocaleTimeString(localeTag(locale), { hour: '2-digit', minute: '2-digit' })}</time>}</div>
          {round.role === 'tool' ? <details><summary>{t('session.toolOutput')}</summary><pre>{round.text}</pre></details> : <Markdown text={round.text} />}
        </article>)}
      </div> : <Empty icon={<FileText size={26} />} title={t('session.noTranscript')}><p>{t('session.noTranscriptText')}</p></Empty>}
    </div> : ended ? <Empty icon={<Check size={26} />} title={t('session.endedTitle')}><p>{t('session.endedText')}</p></Empty>
      : !session.alive && !web ? <Empty icon={<Terminal size={28} />} title={t('session.notRunning')}><p>{t('session.reconnectText')}</p><Button variant="default" disabled={connect.isPending} onClick={() => connect.mutate()}>{connect.isPending ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />}{t('session.reconnect')}</Button></Empty>
      : url ? <div className="embedded-view">{web && <div className="embed-note">{t('session.embedNote')}</div>}<iframe title={t('session.iframeTitle', { scheme: session.scheme })} src={url} referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write" /></div>
      : <div className="snapshot-view"><div className="snapshot-label"><span><span className="live-dot" /> {t('session.snapshot')}</span><Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground" aria-label={t('session.refreshSnapshot')} onClick={() => { void capture.refetch(); }}><RefreshCw size={14} /></Button></div>
        {capture.isPending ? <Loading /> : capture.isError ? <ErrorState error={capture.error} retry={() => { void capture.refetch(); }} /> : <pre className="terminal-output">{capture.data || t('session.waiting')}</pre>}
        <div className="terminal-notice"><Terminal size={17} /><div><strong>{t('session.ttydTitle')}</strong><p>{t('session.ttydText')}</p></div><Button variant="outline" size="sm" onClick={() => navigate({ page: 'settings' })}>{t('session.ttydHow')}</Button></div>
      </div>}
    </TabsContent>
    <AlertDialog open={confirm} onOpenChange={value => { if (!remove.isPending) setConfirm(value); }}><AlertDialogContent {...focus}>
      <AlertDialogHeader><AlertDialogTitle>{t('session.confirmTitle')}</AlertDialogTitle><AlertDialogDescription>{t('session.confirmText')}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>{t('session.keep')}</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" disabled={remove.isPending} onClick={event => { event.preventDefault(); remove.mutate(); }}>{remove.isPending ? t('session.ending') : t('session.end')}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </Tabs>;
}
