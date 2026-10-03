import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Check, ExternalLink, FileText, LoaderCircle, Play, Terminal, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { localeTag, useT } from '@/lib/i18n';
import { pushedSchemes, type Round, type Worklet, type Work } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown, safeWindowUrl } from '@/components/Shared';
import { AgentLog } from './AgentLog';

const workletPath = (work: Work, worklet: Worklet) => `/works/${encodeURIComponent(work.id)}/worklets/${encodeURIComponent(worklet.id)}`;
/** 窗:网页就是它自己的地址;终端类是 tmuxd 自带的 ttyd 地址(重入拿到的优先,其次清单里带的)。死了的没有。 */
const windowUrl = (worklet: Worklet, live: Worklet | undefined) =>
  safeWindowUrl(['http', 'https'].includes(worklet.scheme) ? worklet.uri : live?.window?.embed || worklet.window?.embed || null);

/** 工作单元标题行上的两个动作:在新窗口打开(有窗才有)、结束并移除(先确认)。work 归档了就都没有。 */
export function WorkletActions({ work, worklet }: { work: Work; worklet: Worklet }) {
  const t = useT();
  const focus = useDialogFocus();
  const [confirm, setConfirm] = useState(false);
  const live = useQuery<Worklet>({ queryKey: ['live', work.id, worklet.id], enabled: false });
  const remove = useMutation({ mutationFn: () => api(workletPath(work, worklet), { method: 'DELETE' }), onSuccess: () => {
    for (const key of ['live', 'rounds']) queryClient.removeQueries({ queryKey: [key, work.id, worklet.id] });
    for (const key of ['worklets', 'trace']) void queryClient.invalidateQueries({ queryKey: [key, work.id] });
    setConfirm(false); toast.success(t('worklet.closed'));
  }, onError: (error: Error) => toast.error(error.message) });
  if (work.status === 'archived') return null;
  const url = windowUrl(worklet, live.data);
  return <>
    {url && <Button asChild variant="ghost" size="icon" className="size-7 text-muted-foreground"><a href={url} target="_blank" rel="noopener noreferrer" aria-label={t('worklet.openWindow')} title={t('worklet.openWindow')}><ExternalLink className="size-3.5" /></a></Button>}
    <Button variant="ghost" size="icon" className="size-7 text-muted-foreground hover:text-destructive" onClick={() => setConfirm(true)} aria-label={t('worklet.remove')} title={t('worklet.remove')}><Trash2 className="size-3.5" /></Button>
    <AlertDialog open={confirm} onOpenChange={value => { if (!remove.isPending) setConfirm(value); }}><AlertDialogContent {...focus}>
      <AlertDialogHeader><AlertDialogTitle>{t('worklet.confirmTitle')}</AlertDialogTitle><AlertDialogDescription>{t('worklet.confirmText')}</AlertDialogDescription></AlertDialogHeader>
      <AlertDialogFooter><AlertDialogCancel disabled={remove.isPending}>{t('worklet.keep')}</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" disabled={remove.isPending} onClick={event => { event.preventDefault(); remove.mutate(); }}>{remove.isPending ? t('worklet.ending') : t('worklet.end')}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </>;
}

export function WorkletBody({ work, worklet }: { work: Work; worklet: Worklet }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const [mode, setMode] = useState<'terminal' | 'rounds'>('terminal');
  const base = workletPath(work, worklet);
  const ended = work.status === 'archived';
  const web = ['http', 'https'].includes(worklet.scheme);
  const agent = ['codex', 'claude', 'kimi'].includes(worklet.scheme);
  // 记录在 trace 里(节点推):claude 的对话、bash 的每条命令。活着的看把手有没有 trace.agent(跑脚本的、装钩子之前起的 bash 没有)
  const pushed = pushedSchemes.includes(worklet.scheme) && (worklet.handle ? worklet.handle.capabilities.includes('trace.agent') : true);
  const logged = agent || pushed;                                      // 有「记录」这一页
  const live = useQuery<Worklet>({ queryKey: ['live', work.id, worklet.id], enabled: false });
  const connect = useMutation({ mutationFn: () => api<Worklet>(`${base}/attach`, { method: 'POST' }),
    onSuccess: data => { queryClient.setQueryData(['live', work.id, worklet.id], data); for (const key of ['worklets', 'trace']) void queryClient.invalidateQueries({ queryKey: [key, work.id] }); },   // 重入可能开了新的一段
    onError: (error: Error) => toast.error(error.message),
  });
  const url = windowUrl(worklet, live.data);
  const rounds = useQuery({ queryKey: ['rounds', work.id, worklet.id], queryFn: ({ signal }) => api<Round[]>(`${base}/rounds`, { signal }),
    enabled: agent && !pushed && (mode === 'rounds' || ended), refetchInterval: ended ? false : 4_000,
  });
  const showRounds = (mode === 'rounds' || ended) && logged;
  return <Tabs value={ended && logged ? 'rounds' : mode} onValueChange={value => setMode(value as 'terminal' | 'rounds')} className="flex min-h-0 flex-1 flex-col" aria-label={t('worklet.current')}>
    {logged && !ended && <div className="flex items-center justify-end border-b px-2 py-1">   {/* 有记录的才有这一行:终端 / 记录;打开 / 移除在标题行上 */}
      <TabsList className="h-8" aria-label={t('worklet.view')}><TabsTrigger value="terminal" className="text-xs">{t('worklet.terminal')}</TabsTrigger><TabsTrigger value="rounds" className="text-xs">{t('worklet.transcript')}</TabsTrigger></TabsList>
    </div>}
    <TabsContent value={ended && logged ? 'rounds' : mode} className="mt-0 flex min-h-0 flex-1 flex-col">
      {showRounds && pushed ? <AgentLog work={work} worklet={worklet} onTerminal={() => setMode('terminal')} />
      : showRounds ? <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
          <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground"><FileText className="size-3.5" />{ended ? t('worklet.transcriptEnded') : t('worklet.transcriptLive')}</p>
          {rounds.isPending ? <Loading /> : rounds.isError ? <ErrorState error={rounds.error} retry={() => { void rounds.refetch(); }} /> : rounds.data?.length ? rounds.data.map(round =>
            <article key={round.id} className={`rounded-lg text-sm ${round.role === 'human' ? 'ml-8 border bg-muted/50 p-4 sm:ml-16' : round.role === 'tool' ? 'border border-dashed p-3' : 'mr-8 p-4 sm:mr-16'}`}>
              <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><span className="font-medium text-foreground">{round.role === 'human' ? t('worklet.you') : round.role === 'tool' ? t('worklet.tool') : worklet.scheme}</span>{round.timestamp && <time>{new Date(round.timestamp).toLocaleTimeString(localeTag(locale), { hour: '2-digit', minute: '2-digit' })}</time>}</div>
              {round.role === 'tool' ? <details><summary className="cursor-pointer text-xs text-muted-foreground">{t('worklet.toolOutput')}</summary><pre className="mt-2 max-h-80 overflow-auto overscroll-x-contain whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono text-xs">{round.text}</pre></details> : <Markdown text={round.text} />}
            </article>)
            : <Empty icon={<FileText className="size-5" />} title={t('worklet.noTranscript')}><p>{t('worklet.noTranscriptText')}</p></Empty>}
        </div>
      </div>
      : ended ? <div className="flex flex-1 p-4"><Empty icon={<Check className="size-5" />} title={t('worklet.endedTitle')}><p>{t('worklet.endedText')}</p></Empty></div>
      : !worklet.alive && !web ? <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={t('worklet.notRunning')}><p>{t('worklet.reconnectText')}</p><Button disabled={connect.isPending} onClick={() => connect.mutate()}>{connect.isPending ? <LoaderCircle className="animate-spin" /> : <Play />}{t('worklet.reconnect')}</Button></Empty></div>
      : url ? <div className="flex min-h-0 flex-1 flex-col">{web && <p className="border-b bg-muted/40 px-4 py-1.5 text-xs text-muted-foreground">{t('worklet.embedNote')}</p>}<iframe className="min-h-0 flex-1 border-0 bg-background" title={t('worklet.iframeTitle', { scheme: worklet.scheme })} src={url} referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write" /></div>
      : <div className="flex flex-1 p-4"><Empty icon={<Terminal className="size-5" />} title={t('worklet.noWindow')}><p>{t('worklet.noWindowText')}</p></Empty></div>}
    </TabsContent>
  </Tabs>;
}
