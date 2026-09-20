import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, FileText, GitBranch, MessageSquare, UserRound } from 'lucide-react';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { navigate } from '@/lib/router';
import { layerLabel, statusLabel, type SearchResult, type WorkStatus } from '@/lib/types';
import { ErrorState, Loading } from '@/components/Shared';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Command, CommandInput, CommandList, CommandEmpty, CommandItem, CommandGroup } from '@/components/ui/command';

/** 综合搜索:一个输入框,后端 /api/search 把 q 交给每个 service,这里按 kind 分组显示。 */
export function GlobalSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const focus = useDialogFocus(); const t = useT();
  const [term, setTerm] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => { const timer = setTimeout(() => setQ(term.trim()), 250); return () => clearTimeout(timer); }, [term]);
  const result = useQuery({ queryKey: ['search', q], queryFn: ({ signal }) => api<SearchResult>(`/search?${new URLSearchParams({ q })}`, { signal }), enabled: !!q });
  const go = (fn: () => void) => { fn(); onClose(); };
  const hits = result.data?.hits || [];
  const works = hits.filter(h => h.kind === 'work');
  const objects = hits.filter(h => h.kind === 'meta');
  const users = hits.filter(h => h.kind === 'user');
  return <Dialog open={open} onOpenChange={value => { if (!value) onClose(); }}><DialogContent {...focus} className="gap-0 overflow-hidden p-0"><DialogTitle className="sr-only">{t('search.title')}</DialogTitle><DialogDescription className="sr-only">{t('search.description')}</DialogDescription>
    <Command shouldFilter={false}><CommandInput value={term} onValueChange={setTerm} placeholder={t('search.placeholder')} aria-label={t('search.inputLabel')} className="pr-8" /><CommandList>
      {!q ? <p className="p-4 text-center text-sm text-muted-foreground">{t('search.hint')}</p>
        : result.isError ? <ErrorState error={result.error} /> : result.isPending ? <Loading label={t('search.loading')} /> : <>
          <CommandEmpty>{t('search.empty')}</CommandEmpty>
          {works.length > 0 && <CommandGroup heading={`${t('search.works')} ${result.data?.counts.work ?? works.length}`}>{works.map(h => <CommandItem key={h.id} value={`work:${h.id}`} onSelect={() => go(() => navigate({ page: 'work', work: h.id }))}><GitBranch /><span className="min-w-0 flex-1 truncate">{h.title}</span><small className="text-muted-foreground">{statusLabel(t, h.status as WorkStatus)}</small></CommandItem>)}</CommandGroup>}
          {objects.length > 0 && <CommandGroup heading={`${t('search.metas')} ${result.data?.counts.meta ?? objects.length}`}>{objects.map((h, i) => <CommandItem key={`${h.id}:${h.file}:${h.line}:${i}`} value={`meta:${h.file}:${h.line}`} onSelect={() => go(() => navigate({ page: 'meta', filter: 'all', layer: h.layer || 'origin', path: h.id, file: h.layer && h.layer !== 'origin' && h.file ? h.file : undefined }))}>
            {h.layer === 'card' ? <BookOpen /> : h.layer === 'issue' ? <MessageSquare /> : <FileText />}<span className="flex min-w-0 flex-1 flex-col"><span className="truncate">{h.title}<small className="ml-2 text-muted-foreground">{layerLabel(t, h.layer || '')}</small></span><span className="truncate text-xs text-muted-foreground">{h.snippet.trim()}</span></span></CommandItem>)}</CommandGroup>}
          {users.length > 0 && <CommandGroup heading={`${t('search.users')} ${result.data?.counts.user ?? users.length}`}>{users.map(h => <CommandItem key={h.id} value={`user:${h.id}`} onSelect={() => go(() => navigate({ page: 'settings' }))}><UserRound /><span className="min-w-0 flex-1 truncate">{h.title}</span><small className="text-muted-foreground">{h.id}</small></CommandItem>)}</CommandGroup>}
        </>}
    </CommandList></Command>
  </DialogContent></Dialog>;
}
