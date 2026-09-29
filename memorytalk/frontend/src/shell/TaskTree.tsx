import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem } from '@/components/ui/sidebar';
import { useState, type MouseEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Archive, ArchiveRestore, ChevronDown, ChevronRight, Dot, GitBranch, MoreHorizontal } from 'lucide-react';
import { RunningMark } from '@/components/Shared';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { navigate } from '@/lib/router';
import { statusLabel, type Work, type WorkStatus } from '@/lib/types';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { NewSubwork } from './Home';

type RowProps = { work: Work; selected?: string; onNavigate: () => void; onSplit: (id: string) => void };

export function TaskTree({ works, selected, onNavigate }: { works: Work[]; selected?: string; onNavigate: () => void }) {
  const [splitting, setSplitting] = useState('');
  return <>
    <SidebarMenu>{[...works].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(work =>
      <WorkRow key={work.id} work={work} selected={selected} onNavigate={onNavigate} onSplit={setSplitting} />)}</SidebarMenu>
    {splitting && <NewSubwork parent={splitting} open onClose={() => setSplitting('')} />}
  </>;
}

/** 行尾的「⋯」:只在悬停这一行(或菜单开着 / 键盘聚焦)时出现,点开是这个 work 的操作菜单:拆分、归档 / 改回运行中。用 peer 而不是 group-hover,悬停子行时不会把父行的也带出来。 */
function RowActions({ work, onSplit, className }: { work: Work; onSplit: (id: string) => void; className?: string }) {
  const t = useT();
  const ended = work.status === 'archived';
  const setStatus = useMutation({ mutationFn: (status: WorkStatus) => api<Work>(`/works/${encodeURIComponent(work.id)}`, { method: 'PATCH', body: { status } }),
    onSuccess: () => { for (const key of [['work', work.id], ['works'], ['worklets', work.id], ['events', work.id]]) void queryClient.invalidateQueries({ queryKey: key }); },
    onError: (error: Error) => toast.error(error.message),
  });
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <SidebarMenuAction aria-label={`${t('work.actions')} ${work.goal}`} className={cn('hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 md:opacity-0', className)}><MoreHorizontal /></SidebarMenuAction>
    </DropdownMenuTrigger>
    <DropdownMenuContent side="bottom" align="start">
      <DropdownMenuItem disabled={ended} onSelect={() => onSplit(work.id)}><GitBranch />{t('work.split')}</DropdownMenuItem>
      <DropdownMenuSeparator />
      {ended ? <DropdownMenuItem disabled={setStatus.isPending} onSelect={() => setStatus.mutate('running')}><ArchiveRestore />{t('work.unarchive')}</DropdownMenuItem>
        : <DropdownMenuItem disabled={setStatus.isPending} onSelect={() => setStatus.mutate('archived')}><Archive />{t('work.archive')}</DropdownMenuItem>}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** 行首那一格:有子 work 就是展开 / 收起的箭头(点它不跳转);没有就是一个点。状态不在这儿——运行中的在名字后面跟一个 `RunningMark`。 */
function Lead({ work, open, onToggle }: { work: Work; open?: boolean; onToggle?: (e: MouseEvent) => void }) {
  const t = useT();
  if (onToggle) return <button type="button" className="-ml-1 flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-sidebar-accent hover:text-foreground" aria-label={`${open ? t('common.collapse') : t('common.expand')} ${work.goal}`} aria-expanded={open} onClick={onToggle}>{open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</button>;
  return <Dot className="size-4 shrink-0 text-muted-foreground" />;
}

function WorkRow({ work, selected, onNavigate, onSplit }: RowProps) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  const go = () => { navigate({ page: 'work', work: work.id }); onNavigate(); };
  const toggle = children.length ? (e: MouseEvent) => { e.stopPropagation(); setOpen(o => !o); } : undefined;
  return <Collapsible asChild open={open} onOpenChange={setOpen}>
    <SidebarMenuItem>
      <SidebarMenuButton isActive={selected === work.id} onClick={go} tooltip={work.goal} title={statusLabel(t, work.status)} className="pr-8">
        <Lead work={work} open={open} onToggle={toggle} /><span className="truncate">{work.goal}</span>{work.status === 'running' && <RunningMark />}
      </SidebarMenuButton>
      <RowActions work={work} onSplit={onSplit} className="peer-hover/menu-button:opacity-100" />
      {children.length > 0 && <CollapsibleContent><SidebarMenuSub className="mr-0 pr-0">{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} onSplit={onSplit} />)}</SidebarMenuSub></CollapsibleContent>}
    </SidebarMenuItem>
  </Collapsible>;
}

function SubRow({ work, selected, onNavigate, onSplit }: RowProps) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  const toggle = children.length ? (e: MouseEvent) => { e.stopPropagation(); setOpen(o => !o); } : undefined;
  return <SidebarMenuSubItem className="relative">
    <SidebarMenuSubButton isActive={selected === work.id} title={`${work.goal} · ${statusLabel(t, work.status)}`} onClick={() => { navigate({ page: 'work', work: work.id }); onNavigate(); }} className="peer/menu-sub-button pr-8">
      <Lead work={work} open={open} onToggle={toggle} /><span className="truncate">{work.goal}</span>{work.status === 'running' && <RunningMark />}
    </SidebarMenuSubButton>
    <RowActions work={work} onSplit={onSplit} className="top-1 peer-hover/menu-sub-button:opacity-100" />
    {children.length > 0 && open && <SidebarMenuSub className="mr-0 pr-0">{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} onSplit={onSplit} />)}</SidebarMenuSub>}
  </SidebarMenuSubItem>;
}
