import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
  const showRounds = (mode === 'rounds' || ended) && agent;
  return <Tabs value={ended && agent ? 'rounds' : mode} onValueChange={value => setMode(value as 'terminal' | 'rounds')} className="flex min-h-0 flex-1 flex-col" aria-label={t('session.current')}>
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
      <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate font-mono text-xs text-muted-foreground" title={session.uri}>{web ? <ExternalLink className="size-3.5" /> : <Terminal className="size-3.5" />}{session.cwd || session.uri}</span>
      <div className="flex items-center gap-1">
        {agent && !ended && <TabsList className="h-8" aria-label={t('session.view')}><TabsTrigger value="terminal" className="text-xs">{t('session.terminal')}</TabsTrigger><TabsTrigger value="rounds" className="text-xs">{t('session.transcript')}</TabsTrigger></TabsList>}
        <Button variant="ghost" size="icon" className="size-8" onClick={() => { void copy(); }} aria-label={t('session.copy')}>{copied ? <Check /> : <Copy />}</Button>
        {url && !ended && <Button asChild variant="ghost" size="icon" className="size-8"><a href={url} target="_blank" rel="noopener noreferrer" aria-label={t('session.openWindow')}><ExternalLink /></a></Button>}
        {!ended && <Button variant="ghost" size="icon" className="size-8 hover:text-destructive" onClick={() => setConfirm(true)} aria-label={t('session.remove')}><Trash2 /></Button>}
      </div>
    </div>
    <TabsContent value={ended && agent ? 'rounds' : mode} className="mt-0 flex min-h-0 flex-1 flex-col">
      {showRounds ? <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
          <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground"><FileText className="size-3.5" />{ended ? t('session.transcriptEnded') : t('session.transcriptLive')}</p>
          {rounds.isPending ? <Loading /> : rounds.isError ? <ErrorState error={rounds.error} retry={() => { void rounds.refetch(); }} /> : rounds.data?.length ? rounds.data.map(round =>
            <article key={round.id} className={`rounded-lg text-sm ${round.role === 'human' ? 'ml-8 border bg-muted/50 p-4 sm:ml-16' : round.role === 'tool' ? 'border border-dashed p-3' : 'mr-8 p-4 sm:mr-16'}`}>
              <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><span className="font-medium text-foreground">{round.role === 'human' ? t('session.you') : round.role === 'tool' ? t('session.tool') : session.scheme}</span>{round.timestamp && <time>{new Date(round.timestamp).toLocaleTimeString(localeTag(locale), { hour: '2-digit', minute: '2-digit' })}</time>}</div>
              {round.role === 'tool' ? <details><summary className="cursor-pointer text-xs text-muted-foreground">{t('session.toolOutput')}</summary><pre className="mt-2 max-h-80 overflow-auto overscroll-x-contain whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono text-xs">{round.text}</pre></details> : <Markdown text={round.text} />}
            </article>)
            : <Empty icon={<FileText className="size-5" />} title={t('session.noTranscript')}><p>{t('session.noTranscriptText')}</p></Empty>}
        </div>
      </div>
      : ended ? <div className="flex flex-1 p-4"><Empty icon={<Check className="size-5" />} title={t('session.endedTitle')}><p>{t('session.endedText')}</p></Empty></div>
      : !session.alive && !web ? <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={t('session.notRunning')}><p>{t('session.reconnectText')}</p><Button disabled={connect.isPending} onClick={() => connect.mutate()}>{connect.isPending ? <LoaderCircle className="animate-spin" /> : <Play />}{t('session.reconnect')}</Button></Empty></div>
      : url ? <div className="flex min-h-0 flex-1 flex-col">{web && <p className="border-b bg-muted/40 px-4 py-1.5 text-xs text-muted-foreground">{t('session.embedNote')}</p>}<iframe className="min-h-0 flex-1 border-0 bg-background" title={t('session.iframeTitle', { scheme: session.scheme })} src={url} referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write" /></div>
      : <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b px-4 py-1.5 text-xs text-muted-foreground"><span className="size-1.5 rounded-full bg-emerald-500" />{t('session.snapshot')}<Button variant="ghost" size="icon" className="ml-auto size-7" aria-label={t('session.refreshSnapshot')} onClick={() => { void capture.refetch(); }}><RefreshCw className="size-3.5" /></Button></div>
        {capture.isPending ? <Loading /> : capture.isError ? <div className="p-4"><ErrorState error={capture.error} retry={() => { void capture.refetch(); }} /></div> : <pre className="terminal-output">{capture.data || t('session.waiting')}</pre>}
        <Alert className="m-4 mt-3 flex flex-wrap items-center gap-3 [&>svg]:static [&>svg~*]:pl-0"><Terminal className="size-4" /><div className="min-w-0 flex-1"><AlertTitle className="mb-0.5">{t('session.ttydTitle')}</AlertTitle><AlertDescription>{t('session.ttydText')}</AlertDescription></div><Button variant="outline" size="sm" onClick={() => navigate({ page: 'settings' })}>{t('session.ttydHow')}</Button></Alert>
      </div>}
    </TabsContent>
    <AlertDialog open={confirm} onOpenChange={value => { if (!remove.isPending) setConfirm(value); }}><AlertDialogContent {...focus}>
      <AlertDialogHeader><AlertDialogTitle>{t('session.confirmTitle')}</AlertDialogTitle><AlertDialogDescription>{t('session.confirmText')}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>{t('session.keep')}</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" disabled={remove.isPending} onClick={event => { event.preventDefault(); remove.mutate(); }}>{remove.isPending ? t('session.ending') : t('session.end')}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </Tabs>;
}
