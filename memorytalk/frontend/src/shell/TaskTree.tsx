import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem } from '@/components/ui/sidebar';
import { useState, type MouseEvent } from 'react';
import { ChevronDown, ChevronRight, CircleCheck, CircleDashed, Dot, LoaderCircle } from 'lucide-react';
import { navigate } from '@/lib/router';
import { statusLabel, type Work } from '@/lib/types';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';

export function TaskTree({ works, selected, onNavigate }: { works: Work[]; selected?: string; onNavigate: () => void }) {
  return <SidebarMenu>{[...works].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(work =>
    <WorkRow key={work.id} work={work} selected={selected} onNavigate={onNavigate} />)}</SidebarMenu>;
}

/** 行首那一格:有子 work 就是展开 / 收起的箭头(点它不跳转);没有就是状态标记(做完 ✓、进行中转圈、放弃虚圈、待开始一个点)。 */
function Lead({ work, open, onToggle }: { work: Work; open?: boolean; onToggle?: (e: MouseEvent) => void }) {
  const t = useT();
  if (onToggle) return <button type="button" className="-ml-1 flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-sidebar-accent hover:text-foreground" aria-label={`${open ? t('common.collapse') : t('common.expand')} ${work.goal}`} aria-expanded={open} onClick={onToggle}>{open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</button>;
  const cls = 'size-4 shrink-0 text-muted-foreground';
  if (work.status === 'done') return <CircleCheck className={cls} />;
  if (work.status === 'doing') return <LoaderCircle className={cn(cls, 'text-primary')} />;
  if (work.status === 'abandoned') return <CircleDashed className={cls} />;
  return <Dot className={cls} />;
}

function WorkRow({ work, selected, onNavigate }: { work: Work; selected?: string; onNavigate: () => void }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  const go = () => { navigate({ page: 'work', work: work.id }); onNavigate(); };
  const toggle = children.length ? (e: MouseEvent) => { e.stopPropagation(); setOpen(o => !o); } : undefined;
  return <Collapsible asChild open={open} onOpenChange={setOpen}>
    <SidebarMenuItem>
      <SidebarMenuButton isActive={selected === work.id} onClick={go} tooltip={work.goal} title={statusLabel(t, work.status)}>
        <Lead work={work} open={open} onToggle={toggle} /><span className="truncate">{work.goal}</span>
      </SidebarMenuButton>
      {children.length > 0 && <CollapsibleContent><SidebarMenuSub className="mr-0 pr-0">{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} />)}</SidebarMenuSub></CollapsibleContent>}
    </SidebarMenuItem>
  </Collapsible>;
}

function SubRow({ work, selected, onNavigate }: { work: Work; selected?: string; onNavigate: () => void }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  const toggle = children.length ? (e: MouseEvent) => { e.stopPropagation(); setOpen(o => !o); } : undefined;
  return <SidebarMenuSubItem>
    <SidebarMenuSubButton isActive={selected === work.id} title={`${work.goal} · ${statusLabel(t, work.status)}`} onClick={() => { navigate({ page: 'work', work: work.id }); onNavigate(); }}>
      <Lead work={work} open={open} onToggle={toggle} /><span className="truncate">{work.goal}</span>
    </SidebarMenuSubButton>
    {children.length > 0 && open && <SidebarMenuSub className="mr-0 pr-0">{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} />)}</SidebarMenuSub>}
  </SidebarMenuSubItem>;
}
