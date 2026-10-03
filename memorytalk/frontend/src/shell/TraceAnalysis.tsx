import { Fragment, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactElement } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ChevronDown, ChevronRight, Crosshair, Maximize, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { localeTag, useT, type T } from '@/lib/i18n';
import { useTrace } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { attrValue, traceSpans, workletLabel, type TraceSpan, type Work, type WorkTrace } from '@/lib/types';
import { Empty, ErrorState, Loading } from '@/components/Shared';
import { cn } from '@/lib/utils';

/** 轨迹分析(工作页左边换成这一页;docs/designs/v5/work-trace.md §6 的甘特 / 瀑布):一根时间轴,上面是甘特,点开是火焰图。
 *  甘特:一个工作单元一行,它的每一段 worklet 段画成一根条(开着的画到现在,尾巴渐隐;现场没了的是虚线)。最上面一行是整个工作。
 *  火焰图:点一行,在它下面把它的 agent 段一层一层叠出来——会话 / 轮次 / 工具(bash 是会话 / 命令),和甘特同一根轴。
 *  缩放:Ctrl / ⌘ + 滚轮(触控板捏合)以光标为中心;拖动平移;在时间轴上框选放大;点一段放大到它;双击看全貌。
 *  数据都是同一个 GET /works/{id}/trace:甘特用右边「轨迹」面板那份(只有 work / worklet 段),火焰图按工作单元另取 agent=1&fields=spans(只要段)。 */

const LABEL = 'w-52 shrink-0';                                          // 左边名字那一栏
const ms = (ns?: string) => { try { return Number(BigInt(ns || 0) / 1_000_000n); } catch { return 0; } };
const str = (s: TraceSpan, key: string) => { const v = attrValue(s.attributes, key); return v === undefined ? '' : String(v); };

interface Bar { span: TraceSpan; start: number; end: number | null }      // 毫秒;end 为空 = 还开着
interface Lane { worklet: string; scheme: string; uri: string; number: string; bars: Bar[]; first: number }
interface View { from: number; to: number }

const bar = (span: TraceSpan): Bar => ({ span, start: ms(span.startTimeUnixNano), end: span.endTimeUnixNano ? ms(span.endTimeUnixNano) : null });

function lanesOf(trace: WorkTrace) {
  const spans = traceSpans(trace);
  const lanes = new Map<string, Lane>();
  for (const s of spans) {
    if (s.name !== 'worklet') continue;
    const id = str(s, 'memorytalk.worklet.id');
    if (!id) continue;
    const lane = lanes.get(id) ?? { worklet: id, scheme: str(s, 'memorytalk.worklet.scheme'), uri: str(s, 'memorytalk.worklet.uri'),
      number: id.match(/-w(\d+)$/)?.[1] ?? '', bars: [], first: Infinity };
    lane.bars.push(bar(s));
    lane.first = Math.min(lane.first, ms(s.startTimeUnixNano));
    lanes.set(id, lane);
  }
  return { work: spans.filter(s => s.name === 'work').map(bar), lanes: [...lanes.values()].sort((a, b) => a.first - b.first) };
}

function extent(bars: Bar[], now: number): View | null {
  if (!bars.length) return null;
  const from = Math.min(...bars.map(b => b.start)), to = Math.max(...bars.map(b => b.end ?? now));
  const pad = Math.max((to - from) * 0.02, 1_000);
  return { from: from - pad, to: to + pad };
}

/** 刻度:按宽度挑一个整齐的步长(毫秒到周),一小时以上按本地时间对齐(整点、零点)。 */
const STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1e3, 2e3, 5e3, 1e4, 15e3, 3e4, 6e4, 12e4, 3e5, 6e5, 9e5, 18e5, 36e5, 72e5, 108e5, 216e5, 432e5, 864e5, 1728e5, 6048e5];
function ticks(v: View, width: number): { at: number; step: number }[] {
  const target = (v.to - v.from) / Math.max(2, width / 110);
  const step = STEPS.find(s => s >= target) ?? STEPS[STEPS.length - 1];
  const tz = step >= 36e5 ? -new Date().getTimezoneOffset() * 6e4 : 0;
  const out = [];
  for (let at = Math.ceil((v.from + tz) / step) * step - tz; at <= v.to && out.length < 200; at += step) out.push({ at, step });
  return out;
}
function tickLabel(at: number, step: number, locale: string) {
  const d = new Date(at);
  if (step >= 864e5) return d.toLocaleDateString(locale, { month: 'numeric', day: 'numeric' });
  if (step >= 6e4) return d.getHours() === 0 && d.getMinutes() === 0 ? d.toLocaleDateString(locale, { month: 'numeric', day: 'numeric' })
    : d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
  const s = d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  return step >= 1e3 ? s : `${s}.${String(d.getMilliseconds()).padStart(3, '0')}`;
}

function took(t: T, msec: number) {
  if (msec < 1000) return t('agent.millis', { ms: Math.round(msec) });
  if (msec < 10_000) return t('agent.seconds', { s: (msec / 1000).toFixed(1) });
  const s = Math.round(msec / 1000);
  if (s < 3600) return s < 60 ? t('agent.seconds', { s }) : t('agent.minutes', { m: Math.floor(s / 60), s: s % 60 });
  return t('analysis.hours', { h: Math.floor(s / 3600), m: Math.floor((s % 3600) / 60) });
}

/** 悬停看的那几行:是什么、何时开始、多长、怎么结束的,再加几样有用的属性。 */
function tooltip(t: T, b: Bar, title: string, now: number, tag: string) {
  const s = b.span;
  const lines = [title, t('analysis.startedAt', { at: new Date(b.start).toLocaleString(tag) }),
    b.end === null ? t('analysis.running', { d: took(t, now - b.start) }) : t('analysis.took', { d: took(t, b.end - b.start) })];
  const reason = str(s, 'memorytalk.end.reason');
  if (reason) lines.push(t('analysis.endedBy', { reason: t(`analysis.reason.${reason}` as 'analysis.reason.completed') }));
  const code = attrValue(s.attributes, 'process.exit.code');
  if (typeof code === 'number') lines.push(t('agent.exitCode', { code }));
  const input = attrValue(s.attributes, 'gen_ai.usage.input_tokens'), output = attrValue(s.attributes, 'gen_ai.usage.output_tokens');
  if (typeof input === 'number' && typeof output === 'number') lines.push(t('agent.tokens', { input: compact(input), output: compact(output) }));
  return lines.join('\n');
}
const compact = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n));

function useNow(every: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const h = window.setInterval(() => setNow(Date.now()), every); return () => window.clearInterval(h); }, [every]);
  return now;
}

const FADE = { maskImage: 'linear-gradient(to right, black 80%, transparent)', WebkitMaskImage: 'linear-gradient(to right, black 80%, transparent)' };

export function TraceAnalysis({ work, onBack }: { work: Work; onBack: () => void }) {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const tag = localeTag(locale);
  const trace = useTrace(work.id);
  const now = useNow(5_000);
  const data = useMemo(() => (trace.data ? lanesOf(trace.data) : null), [trace.data]);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [view, setView] = useState<View | null>(null);
  const [width, setWidth] = useState(800);
  const [brush, setBrush] = useState<{ a: number; b: number } | null>(null);
  const axis = useRef<HTMLDivElement>(null), scroller = useRef<HTMLDivElement>(null);
  const full = useMemo(() => extent([...(data?.work ?? []), ...(data?.lanes.flatMap(l => l.bars) ?? [])], now) ?? { from: now - 36e5, to: now },
    [data, now]);
  const v = view ?? full;
  const charted = !!data && (data.lanes.length > 0 || data.work.length > 0);   // 有图才有时间轴和滚动区
  const live = useRef({ v, width }); live.current = { v, width };
  const x = (at: number) => ((at - v.from) / (v.to - v.from)) * width;
  const timeAt = (clientX: number) => {
    const rect = axis.current!.getBoundingClientRect();
    return live.current.v.from + ((clientX - rect.left) / live.current.width) * (live.current.v.to - live.current.v.from);
  };
  const zoom = (factor: number, center = (v.from + v.to) / 2) => {
    const span = Math.max((v.to - v.from) * factor, 1);                 // 最小看 1 毫秒
    const k = (center - v.from) / (v.to - v.from);
    setView({ from: center - span * k, to: center + span * (1 - k) });
  };
  const focus = (from: number, to: number) => {
    const pad = Math.max((to - from) * 0.08, 5);
    setView({ from: from - pad, to: to + pad });
  };

  useEffect(() => {                                                     // 量出时间轴那一栏有多宽
    const el = axis.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.max(el.clientWidth, 100)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [charted]);
  useEffect(() => {                                                     // Ctrl / ⌘ + 滚轮缩放(要能 preventDefault,不用 React 的 onWheel)
    const el = scroller.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const { v: cur } = live.current;
      const at = timeAt(e.clientX);
      const span = Math.max((cur.to - cur.from) * Math.exp(e.deltaY * 0.005), 1);       // 滚轮一格(100)约 0.6 倍;捏合的增量小,平滑
      const k = (at - cur.from) / (cur.to - cur.from);
      setView({ from: at - span * k, to: at + span * (1 - k) });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [charted]);

  const dragged = useRef(false);
  const pan = (e: ReactPointerEvent) => {                               // 在图上按住拖:平移
    if (e.button !== 0) return;
    const startX = e.clientX, start = live.current.v;
    dragged.current = false;
    const move = (m: PointerEvent) => {
      const dx = m.clientX - startX;
      if (Math.abs(dx) > 3) dragged.current = true;
      const shift = (-dx / live.current.width) * (start.to - start.from);
      setView({ from: start.from + shift, to: start.to + shift });
    };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  const select = (e: ReactPointerEvent) => {                            // 在时间轴上框选:放大到选中的那一段
    if (e.button !== 0) return;
    const rect = axis.current!.getBoundingClientRect();
    const a = e.clientX - rect.left;
    setBrush({ a, b: a });
    const move = (m: PointerEvent) => setBrush({ a, b: Math.min(Math.max(m.clientX - rect.left, 0), rect.width) });
    const up = (m: PointerEvent) => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      setBrush(null);
      const b = Math.min(Math.max(m.clientX - rect.left, 0), rect.width);
      if (Math.abs(b - a) > 4) { const lo = timeAt(rect.left + Math.min(a, b)), hi = timeAt(rect.left + Math.max(a, b)); setView({ from: lo, to: hi }); }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  if (trace.isPending) return <Loading />;
  if (trace.isError) return <div className="p-4"><ErrorState error={trace.error} retry={() => { void trace.refetch(); }} /></div>;
  const { work: workBars, lanes } = data!;
  const marks = ticks(v, width);
  const chart = 'relative min-w-0 flex-1 cursor-grab touch-none overflow-hidden active:cursor-grabbing';   // 伸出视野的部分裁掉,不盖住左边的名字
  const seq = trace.data?.seq;

  const bars = (list: Bar[], className: (b: Bar) => string, title: (b: Bar) => string, onClick?: (b: Bar) => void, label?: (b: Bar) => string) =>
    list.map(b => {
      const left = x(b.start), right = x(b.end ?? now);
      if (right < -1 || left > width + 1) return null;                 // 不在视野里的不画
      const w = Math.max(right - left, 1);
      const text = label?.(b);
      return <div key={b.span.spanId} title={title(b)} onClick={onClick && (() => { if (!dragged.current) onClick(b); })}
        className={cn('absolute top-1/2 h-4 -translate-y-1/2 overflow-hidden whitespace-nowrap rounded-sm px-1 text-[10px] leading-4 text-white', onClick && 'cursor-zoom-in', className(b))}
        style={{ left, width: w, ...(b.end === null ? FADE : {}) }}>{text && w > 36 ? text : null}</div>;
    });

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
      <Button variant="ghost" size="sm" className="-ml-2 gap-1" onClick={onBack}><ArrowLeft />{t('analysis.back')}</Button>
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold" title={work.goal}>{t('analysis.title')} · {work.goal}</h1>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {([['bg-primary/70', 'analysis.legendWorklet'], ['bg-sky-500/80', 'analysis.sessions'], ['bg-emerald-500/80', 'analysis.turns'], ['bg-amber-500/90', 'analysis.tools'], ['bg-red-500/90', 'analysis.failed']] as const)
          .map(([color, key]) => <span key={key} className="flex items-center gap-1"><span className={cn('size-2.5 rounded-sm', color)} />{t(key)}</span>)}
      </div>
      <div className="flex items-center">
        <Button variant="ghost" size="icon" className="size-8" aria-label={t('analysis.zoomIn')} title={t('analysis.zoomIn')} onClick={() => zoom(0.5)}><ZoomIn /></Button>
        <Button variant="ghost" size="icon" className="size-8" aria-label={t('analysis.zoomOut')} title={t('analysis.zoomOut')} onClick={() => zoom(2)}><ZoomOut /></Button>
        <Button variant="ghost" size="icon" className="size-8" aria-label={t('analysis.fit')} title={t('analysis.fit')} disabled={!view} onClick={() => setView(null)}><Maximize /></Button>
      </div>
    </div>
    <p className="border-b px-4 py-1.5 text-xs text-muted-foreground">{t('analysis.hint')}</p>
    {!charted ? <div className="flex flex-1 p-4"><Empty title={t('analysis.empty')} /></div> :
    <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden pb-6" onDoubleClick={() => setView(null)}>
      <div className="sticky top-0 z-10 flex border-b bg-background/95 backdrop-blur">  {/* 时间轴:框选放大 */}
        <div className={cn(LABEL, 'px-4 py-1.5 text-xs text-muted-foreground')}>{t('analysis.worklets')}</div>
        <div ref={axis} className="relative h-8 min-w-0 flex-1 cursor-crosshair select-none overflow-hidden" onPointerDown={select}>
          {marks.map(m => <span key={m.at} className="absolute top-2 -translate-x-1/2 whitespace-nowrap text-[10px] text-muted-foreground" style={{ left: x(m.at) }}>{tickLabel(m.at, m.step, tag)}</span>)}
          {brush && <div className="absolute inset-y-0 bg-primary/15 outline outline-1 outline-primary/40" style={{ left: Math.min(brush.a, brush.b), width: Math.abs(brush.b - brush.a) }} />}
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-0 left-52 right-0 top-0">  {/* 刻度线和「现在」 */}
        {marks.map(m => <div key={m.at} className="absolute inset-y-0 w-px bg-border/70" style={{ left: x(m.at) }} />)}
        {now >= v.from && now <= v.to && <div className="absolute inset-y-0 w-px bg-primary/60" style={{ left: x(now) }} title={t('analysis.now')} />}
      </div>
      {workBars.length > 0 && <div className="flex h-9 items-center border-b">
        <div className={cn(LABEL, 'truncate px-4 text-xs font-medium')}>{t('analysis.work')}</div>
        <div className={cn(chart, 'h-full')} onPointerDown={pan}>
          {bars(workBars, b => (b.end === null ? 'bg-foreground/60' : 'bg-foreground/30'), b => tooltip(t, b, t('analysis.work'), now, tag))}
        </div>
      </div>}
      {lanes.map(lane => {
        const expanded = open.has(lane.worklet);
        const name = `${workletLabel(t, lane.scheme)}${lane.number ? ` ${lane.number}` : ''}`;
        const toggle = () => setOpen(s => { const n = new Set(s); if (n.has(lane.worklet)) n.delete(lane.worklet); else n.add(lane.worklet); return n; });
        return <Fragment key={lane.worklet}>
          <div className={cn('flex h-9 items-center border-b', expanded && 'bg-muted/40')}>
            <button type="button" className={cn(LABEL, 'flex h-full items-center gap-1 px-2 text-left text-xs hover:bg-accent')} aria-expanded={expanded} onClick={toggle} title={lane.uri}>
              {expanded ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
              <span className="shrink-0 font-medium">{name}</span>
              <span className="min-w-0 truncate font-mono text-[10px] text-muted-foreground">{lane.uri.replace(/^[a-z]+:\/\//, '')}</span>
            </button>
            <div className={cn(chart, 'h-full')} onPointerDown={pan}>
              {bars(lane.bars, b => cn(b.end === null ? 'bg-primary/80' : 'bg-primary/40', str(b.span, 'memorytalk.end.reason') === 'gone' && 'border border-dashed border-primary bg-transparent'),
                b => tooltip(t, b, name, now, tag), b => focus(b.start, b.end ?? now))}
            </div>
          </div>
          {expanded && <Flame work={work} lane={lane} seq={seq} now={now} chart={chart} pan={pan} bars={bars}
            onFocus={focus} label={name} />}
        </Fragment>;
      })}
    </div>}
  </div>;
}

type Bars = (list: Bar[], className: (b: Bar) => string, title: (b: Bar) => string, onClick?: (b: Bar) => void, label?: (b: Bar) => string) => (ReactElement | null)[];

/** 一个工作单元的火焰图:它的 agent 段按层叠(父是 worklet 段的在第一层),每层一行,和甘特同一根轴。 */
function Flame({ work, lane, seq, now, chart, pan, bars, onFocus, label }: {
  work: Work; lane: Lane; seq?: string; now: number; chart: string; pan: (e: ReactPointerEvent) => void; bars: Bars;
  onFocus: (from: number, to: number) => void; label: string;
}) {
  const t = useT();
  const tag = localeTag(usePreferences(s => s.locale));
  const q = useQuery({
    queryKey: ['trace', work.id, 'flame', lane.worklet, seq],          // 这个 work 有新东西(seq 变了)就再取一次
    queryFn: ({ signal }) => api<WorkTrace>(`/works/${encodeURIComponent(work.id)}/trace?worklet=${encodeURIComponent(lane.worklet)}&agent=1&fields=spans`, { signal }),
    placeholderData: keepPreviousData,
  });
  const levels = useMemo(() => {
    const spans = q.data ? traceSpans(q.data).filter(s => s.name.startsWith('agent.')) : [];
    const byId = new Map(spans.map(s => [s.spanId, s]));
    const depth = new Map<string, number>();
    const depthOf = (s: TraceSpan, guard = 0): number => {
      if (depth.has(s.spanId)) return depth.get(s.spanId)!;
      const parent = s.parentSpanId ? byId.get(s.parentSpanId) : undefined;
      const d = parent && guard < 32 ? depthOf(parent, guard + 1) + 1 : 0;
      depth.set(s.spanId, d);
      return d;
    };
    const out: Bar[][] = [];
    for (const s of spans) (out[depthOf(s)] ??= []).push(bar(s));
    const turns = spans.filter(s => s.name === 'agent.turn').map(bar).sort((a, b) => a.start - b.start);
    const order = new Map(turns.map((b, i) => [b.span.spanId, i + 1]));
    return { out, order };
  }, [q.data]);
  if (q.isPending) return <div className="flex h-8 items-center border-b px-4 text-xs text-muted-foreground">…</div>;
  if (q.isError) return <div className="border-b p-2"><ErrorState error={q.error} /></div>;
  if (!levels.out.length) return <div className="flex h-8 items-center border-b bg-muted/20 pl-9 text-xs text-muted-foreground">{t('analysis.noDetail')}</div>;
  const all = levels.out.flat();
  const shell = lane.scheme === 'bash';
  const nameOf = (b: Bar) => {
    const s = b.span;
    if (s.name === 'agent.session') return t('analysis.session');
    if (s.name === 'agent.turn') return t(shell ? 'analysis.command' : 'analysis.turn', { n: levels.order.get(s.spanId) ?? '' });
    if (s.name === 'agent.tool') return str(s, 'gen_ai.tool.name') || t('worklet.tool');
    return s.name;
  };
  const color = (b: Bar) => {
    const s = b.span, code = attrValue(s.attributes, 'process.exit.code');
    if (s.status?.code === 2 || (typeof code === 'number' && code !== 0 && code !== 130)) return 'bg-red-500/90';
    return s.name === 'agent.session' ? 'bg-sky-500/80' : s.name === 'agent.turn' ? 'bg-emerald-500/80' : s.name === 'agent.tool' ? 'bg-amber-500/90' : 'bg-violet-500/80';
  };
  const levelName = (row: Bar[]) => {
    const names = new Set(row.map(b => b.span.name));
    return names.size === 1 && names.has('agent.session') ? t('analysis.sessions') : names.size === 1 && names.has('agent.turn') ? t(shell ? 'analysis.commands' : 'analysis.turns')
      : names.size === 1 && names.has('agent.tool') ? t('analysis.tools') : '';
  };
  return <div className="border-b bg-muted/20">
    {levels.out.map((row, depth) => <div key={depth} className="flex h-7 items-center">
      <div className={cn(LABEL, 'flex h-full items-center justify-between gap-1 pl-9 pr-2 text-[11px] text-muted-foreground')}>
        <span className="truncate">{levelName(row)}</span>
        {depth === 0 && <button type="button" className="rounded p-0.5 hover:bg-accent hover:text-foreground" aria-label={t('analysis.focus')} title={t('analysis.focus')}
          onClick={() => onFocus(Math.min(...all.map(b => b.start)), Math.max(...all.map(b => b.end ?? now)))}><Crosshair className="size-3.5" /></button>}
      </div>
      <div className={cn(chart, 'h-full')} onPointerDown={pan}>
        {bars(row, color, b => tooltip(t, b, `${label} · ${nameOf(b)}`, now, tag), b => onFocus(b.start, b.end ?? now), nameOf)}
      </div>
    </div>)}
  </div>;
}
