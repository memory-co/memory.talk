import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowUp, CircleAlert, FileText, LoaderCircle, Terminal, Wrench } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { api, ApiError } from '@/lib/api';
import { localeTag, useT, type T } from '@/lib/i18n';
import { usePreferences } from '@/lib/store';
import { attrValue, traceRecords, traceSpans, workletLabel, type TraceLogRecord, type TraceSpan, type Work, type WorkTrace, type Worklet } from '@/lib/types';
import { Empty, ErrorState, Loading, Markdown } from '@/components/Shared';
import { cn } from '@/lib/utils';

/** 一个 agent 工作单元的对话 = trace 里它的 agent 那几层(docs/designs/v5/work-trace.md §6;output 就是 trace,没有别的接口)。
 *  先整份读一次(worklet + agent + bodies),再带着 seq 等变化(after + wait,长轮询):有新消息、轮次开始或结束、状态变了才回来,
 *  并进来——不再每几秒整份拉。段按 spanId 换成新的样子(开着的会合并属性、结束即定稿),点按 log.record.uid 去重。 */
function useAgentTrace(workId: string, workletId: string, live: boolean) {
  const [state, setState] = useState<{ spans: TraceSpan[]; points: TraceLogRecord[]; loaded: boolean; error: unknown }>({ spans: [], points: [], loaded: false, error: null });
  useEffect(() => {
    const abort = new AbortController();
    const spans = new Map<string, TraceSpan>(), points = new Map<string, TraceLogRecord>();
    const base = `/works/${encodeURIComponent(workId)}/trace?worklet=${encodeURIComponent(workletId)}&agent=1&bodies=1`;
    let seq: string | undefined;
    const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
    void (async () => {
      while (!abort.signal.aborted) {
        try {
          const data = await api<WorkTrace>(seq === undefined ? base : `${base}&after=${seq}&wait=25`, { signal: abort.signal });
          const fresh = traceSpans(data), records = traceRecords(data);
          for (const s of fresh) spans.set(s.spanId, s);
          for (const p of records) points.set(String(attrValue(p.attributes, 'log.record.uid') ?? `${p.spanId}:${p.timeUnixNano}:${p.eventName}`), p);
          const first = seq === undefined;
          seq = data.seq ?? seq;
          if (first || fresh.length || records.length) setState({ spans: [...spans.values()], points: [...points.values()], loaded: true, error: null });
          if (!live) return;                                          // 归档了:读一次就够
          if (data.seq === undefined) await pause(5000);              // 服务端还不认 after / wait(老版本):别一直整份重读
        } catch (error) {
          if (abort.signal.aborted) return;
          setState(s => ({ ...s, error }));
          await pause(3000);
        }
      }
    })();
    return () => abort.abort();
  }, [workId, workletId, live]);
  return state;
}

const nanos = (value: string | undefined) => { try { return BigInt(value || 0); } catch { return 0n; } };
const text = (r: { attributes?: TraceLogRecord['attributes'] } | undefined, key: string) => { const v = attrValue(r?.attributes, key); return v === undefined ? '' : String(v); };
const body = (p: TraceLogRecord | undefined) => p?.body?.stringValue ?? '';

type Item =
  | { kind: 'message'; at: bigint; key: string; point: TraceLogRecord }
  | { kind: 'tool'; at: bigint; key: string; span: TraceSpan; input?: TraceLogRecord; output?: TraceLogRecord }
  | { kind: 'turn'; at: bigint; key: string; span: TraceSpan }
  | { kind: 'session'; at: bigint; key: string; span: TraceSpan };
const ORDER = { session: 0, message: 1, tool: 1, turn: 2 } as const;

/** 摊成一条时间线:消息一条一项,工具调用一项(参数和结果并进去),一轮结束一项(耗时、token),换会话一项。 */
function build(spans: TraceSpan[], points: TraceLogRecord[]) {
  const items: Item[] = [];
  const io = new Map<string, { input?: TraceLogRecord; output?: TraceLogRecord }>();
  let state: TraceLogRecord | undefined;
  for (const p of points) {
    if (p.eventName === 'agent.message') items.push({ kind: 'message', at: nanos(p.timeUnixNano), key: text(p, 'log.record.uid') || `${p.spanId}:${p.timeUnixNano}`, point: p });
    else if (p.eventName === 'agent.tool.input' || p.eventName === 'agent.tool.output') {
      const slot = io.get(p.spanId ?? '') ?? {};
      slot[p.eventName === 'agent.tool.input' ? 'input' : 'output'] = p;
      io.set(p.spanId ?? '', slot);
    } else if (p.eventName === 'agent.state' && (!state || nanos(p.timeUnixNano) >= nanos(state.timeUnixNano))) state = p;
  }
  const sessions = spans.filter(s => s.name === 'agent.session').sort((a, b) => (nanos(a.startTimeUnixNano) < nanos(b.startTimeUnixNano) ? -1 : 1));
  for (const s of spans) {
    if (s.name === 'agent.tool') items.push({ kind: 'tool', at: nanos(s.startTimeUnixNano), key: s.spanId, span: s, ...io.get(s.spanId) });
    else if (s.name === 'agent.turn' && s.endTimeUnixNano) items.push({ kind: 'turn', at: nanos(s.endTimeUnixNano), key: `${s.spanId}:end`, span: s });
  }
  for (const s of sessions.slice(1)) items.push({ kind: 'session', at: nanos(s.startTimeUnixNano), key: s.spanId, span: s });
  items.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : ORDER[a.kind] - ORDER[b.kind]));
  return { items, state: state ? text(state, 'memorytalk.state') : '' };
}

const compact = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n));
/** 耗时:一秒以内写毫秒(终端的命令大多很快),十秒以内一位小数,再长写分秒。 */
function duration(t: T, ns: bigint) {
  const ms = Number(ns / 1_000_000n);
  if (ms < 1000) return t('agent.millis', { ms });
  if (ms < 10_000) return t('agent.seconds', { s: (ms / 1000).toFixed(1) });
  const s = Math.round(ms / 1000);
  return s < 60 ? t('agent.seconds', { s }) : t('agent.minutes', { m: Math.floor(s / 60), s: s % 60 });
}
/** 工具调用一行里的那句提示:命令、文件、搜的东西……没有就不写。 */
function hint(input: string) {
  try {
    const v = JSON.parse(input) as Record<string, unknown>;
    const first = ['command', 'file_path', 'path', 'pattern', 'url', 'query', 'description'].map(k => v?.[k]).find(x => typeof x === 'string');
    return typeof first === 'string' ? first : '';
  } catch { return ''; }
}
function pretty(input: string) {
  try { return JSON.stringify(JSON.parse(input), null, 2); } catch { return input; }
}

type Refused = 'busy' | 'blocked' | 'gone';

/** 轨迹下面的输入框:经 POST …/input 送进现场(work-server-io.md §4,claude 就是往它的 tmux 里打字再按回车)。
 *  agent 正在干活 / 在等确认时服务端默认不送(409 busy / blocked):正在干活可以「仍然发送」(排在这一轮后面);
 *  在等确认时打的字会被当成回答,不在这里送,去终端处理。送出去的话由节点读回来,出现在上面的轨迹里。 */
function Composer({ work, worklet, state, onTerminal }: { work: Work; worklet: Worklet; state: string; onTerminal?: () => void }) {
  const t = useT();
  const shell = worklet.scheme === 'bash';                           // 终端:送的是命令,忙 = 有命令在跑
  const [text, setText] = useState('');
  const [refused, setRefused] = useState<Refused | null>(null);
  useEffect(() => { setRefused(null); }, [state]);                    // 状态变了,上一次的拒绝就不算数了
  const name = workletLabel(t, worklet.scheme);
  const send = useMutation({
    mutationFn: (force: boolean) => api(`/works/${encodeURIComponent(work.id)}/worklets/${encodeURIComponent(worklet.id)}/input`,
      { method: 'POST', body: { kind: 'text', text, submit: true, force } }),
    onSuccess: () => { setText(''); setRefused(null); },
    onError: (error: Error) => {
      const code = error instanceof ApiError ? error.code : undefined;
      if (code === 'busy' || code === 'blocked' || code === 'gone') setRefused(code);
      else toast.error(error.message);
    },
  });
  const submit = (force = false) => { if (text.trim() && !send.isPending) send.mutate(force); };
  const placeholder = state === 'busy' ? t(shell ? 'agent.shellPlaceholderBusy' : 'agent.placeholderBusy', { name })
    : state === 'blocked' ? t('agent.placeholderBlocked', { name }) : t(shell ? 'agent.shellPlaceholder' : 'agent.placeholder', { name });
  return <div className="shrink-0 border-t bg-background px-4 py-3">
    <div className="mx-auto max-w-3xl">
      {refused && <div className={cn('mb-2 flex flex-wrap items-center gap-2 text-xs', refused === 'busy' ? 'text-muted-foreground' : 'text-amber-600 dark:text-amber-400')}>
        <span>{refused === 'busy' ? t(shell ? 'agent.shellRefusedBusy' : 'agent.refusedBusy', { name }) : refused === 'blocked' ? t('agent.refusedBlocked', { name }) : t('agent.refusedGone')}</span>
        {refused === 'busy' && <Button variant="outline" size="sm" className="h-6 px-2 text-xs" disabled={send.isPending} onClick={() => submit(true)}>{t('agent.sendAnyway')}</Button>}
        {refused === 'blocked' && onTerminal && <Button variant="outline" size="sm" className="h-6 gap-1 px-2 text-xs" onClick={onTerminal}><Terminal className="size-3" />{t('agent.toTerminal')}</Button>}
      </div>}
      <div className="flex items-end gap-2 rounded-lg border bg-background py-1.5 pl-3 pr-1.5 focus-within:ring-1 focus-within:ring-ring">
        <textarea value={text} rows={Math.min(8, Math.max(1, text.split('\n').length))} placeholder={placeholder} aria-label={t('agent.send')}
          className="max-h-48 min-w-0 flex-1 resize-none bg-transparent py-1 text-sm leading-6 outline-none placeholder:text-muted-foreground"
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {                                              // Enter 发送,Shift+Enter 换行;输入法选词时的 Enter 不算
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); submit(); }
          }} />
        <Button size="icon" className="size-8 shrink-0" disabled={!text.trim() || send.isPending} onClick={() => submit()} aria-label={t('agent.send')} title={t('agent.send')}>
          {send.isPending ? <LoaderCircle className="animate-spin" /> : <ArrowUp />}
        </Button>
      </div>
    </div>
  </div>;
}

export function AgentLog({ work, worklet, onTerminal }: { work: Work; worklet: Worklet; onTerminal?: () => void }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const live = work.status !== 'archived';
  const { spans, points, loaded, error } = useAgentTrace(work.id, worklet.id, live);
  const { items, state } = useMemo(() => build(spans, points), [spans, points]);
  const scroller = useRef<HTMLDivElement>(null), stick = useRef(true);
  useLayoutEffect(() => {                                             // 停在底部的人,新消息来了跟着往下走;往上翻着看的不打扰
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  const time = (at: bigint) => new Date(Number(at / 1_000_000n)).toLocaleTimeString(localeTag(locale), { hour: '2-digit', minute: '2-digit' });
  const agentName = workletLabel(t, worklet.scheme);
  const shell = worklet.scheme === 'bash';                           // 终端:人那句是命令、回复是输出、一轮收尾写退出码
  return <div className="flex min-h-0 flex-1 flex-col">
    <div ref={scroller} className="min-h-0 flex-1 overflow-auto" onScroll={e => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground"><FileText className="size-3.5" />{live ? t('agent.live') : t('worklet.transcriptEnded')}</p>
      {live && state && <p className={cn('flex items-center justify-center gap-1.5 text-xs', state === 'blocked' ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground')}>
        <span className={cn('size-1.5 rounded-full', state === 'busy' ? 'animate-pulse bg-emerald-500' : state === 'blocked' ? 'bg-amber-500' : 'bg-muted-foreground/50')} />{t((shell ? `agent.shell.${state}` : `agent.${state}`) as 'agent.busy')}
      </p>}
      {!loaded ? (error ? <ErrorState error={error} /> : <Loading />)
        : !items.length ? <Empty icon={<FileText className="size-5" />} title={t('worklet.noTranscript')}><p>{t('worklet.noTranscriptText')}</p></Empty>
        : items.map(item => {
          if (item.kind === 'session') {
            const source = text(item.span, 'memorytalk.session.source');
            return <p key={item.key} className="flex items-center gap-3 text-xs text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">{source ? t('agent.newSessionFrom', { source }) : t('agent.newSession')}</p>;
          }
          if (item.kind === 'turn') {
            const s = item.span, reason = text(s, 'memorytalk.end.reason'), took = duration(t, nanos(s.endTimeUnixNano) - nanos(s.startTimeUnixNano));
            const code = attrValue(s.attributes, 'process.exit.code');
            if (typeof code === 'number')                              // 终端的一条命令:退出码 + 耗时
              return <p key={item.key} className={cn('text-center text-xs', code === 0 ? 'text-muted-foreground' : 'text-destructive')}>
                {[reason === 'cancelled' ? t('agent.shellCancelled') : code === 0 ? t('agent.exitOk') : t('agent.exitCode', { code }), took].join(' · ')}</p>;
            const input = attrValue(s.attributes, 'gen_ai.usage.input_tokens'), output = attrValue(s.attributes, 'gen_ai.usage.output_tokens');
            const parts = [reason === 'cancelled' ? t('agent.turnCancelled') : t('agent.turnDone'), took];
            if (typeof input === 'number' && typeof output === 'number') parts.push(t('agent.tokens', { input: compact(input), output: compact(output) }));
            return <p key={item.key} className="text-center text-xs text-muted-foreground">{parts.join(' · ')}</p>;
          }
          if (item.kind === 'tool') {
            const s = item.span, failed = s.status?.code === 2, running = !s.endTimeUnixNano, args = body(item.input);
            return <details key={item.key} className={cn('group rounded-lg border border-dashed px-3 py-2 text-sm', failed && 'border-destructive/50')}>
              <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-muted-foreground">
                {running ? <LoaderCircle className="size-3.5 shrink-0 animate-spin" /> : failed ? <CircleAlert className="size-3.5 shrink-0 text-destructive" /> : <Wrench className="size-3.5 shrink-0" />}
                <span className="shrink-0 font-medium text-foreground">{text(s, 'gen_ai.tool.name') || t('worklet.tool')}</span>
                <span className="min-w-0 flex-1 truncate font-mono">{hint(args)}</span>
                <time className="shrink-0">{time(item.at)}</time>
              </summary>
              {args && <><p className="mt-2 text-xs text-muted-foreground">{t('agent.input')}</p><pre className="mt-1 max-h-60 overflow-auto overscroll-x-contain whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono text-xs">{pretty(args)}</pre></>}
              {item.output && <><p className="mt-2 text-xs text-muted-foreground">{failed ? t('agent.failed') : t('agent.output')}</p><pre className={cn('mt-1 max-h-80 overflow-auto overscroll-x-contain whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono text-xs', failed && 'text-destructive')}>{body(item.output)}</pre></>}
            </details>;
          }
          const p = item.point, role = text(p, 'memorytalk.message.role'), thinking = text(p, 'memorytalk.message.kind') === 'thinking';
          if (role === 'system') return <details key={item.key} className="text-xs text-muted-foreground"><summary className="cursor-pointer truncate">{body(p).replace(/<[^>]+>/g, ' ').trim().slice(0, 120) || t('agent.system')}</summary><pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-2 font-mono">{body(p)}</pre></details>;
          if (thinking) return <details key={item.key} className="mr-8 text-sm text-muted-foreground sm:mr-16"><summary className="cursor-pointer text-xs">{t('agent.thinking')}</summary><p className="mt-1 whitespace-pre-wrap text-xs">{body(p)}</p></details>;
          const human = role === 'user', output = text(p, 'memorytalk.message.kind') === 'output';
          return <article key={item.key} className={cn('min-w-0 rounded-lg text-sm', human ? 'ml-8 border bg-muted/50 p-4 sm:ml-16' : 'mr-8 p-4 sm:mr-16')}>
            <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><span className="font-medium text-foreground">{human ? t('worklet.you') : agentName}</span><time>{time(item.at)}</time></div>
            {attrValue(p.attributes, 'memorytalk.message.hidden') === true ? <p className="text-xs italic text-muted-foreground">{t('agent.shellHidden')}</p>
              : human && shell ? <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-sm"><span className="select-none text-muted-foreground">$ </span>{body(p)}</pre>
              : output ? <pre className="max-h-96 overflow-auto overscroll-x-contain whitespace-pre-wrap break-all rounded bg-muted p-3 font-mono text-xs leading-5">{body(p)}</pre>
              : <Markdown text={body(p)} />}
          </article>;
        })}
    </div>
    </div>
    {live && worklet.alive && <Composer work={work} worklet={worklet} state={state} onTerminal={onTerminal} />}
  </div>;
}
