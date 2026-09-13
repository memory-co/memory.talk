import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SidebarMenu, SidebarMenuAction, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem } from '@/components/ui/sidebar';
import { useState } from 'react';
import { ChevronRight, CircleCheck, CircleDashed, GitBranch, LoaderCircle } from 'lucide-react';
import { navigate } from '@/lib/router';
import { statusLabel, type Work } from '@/lib/types';
import { useT } from '@/lib/i18n';

export function TaskTree({ works, selected, onNavigate }: { works: Work[]; selected?: string; onNavigate: () => void }) {
  return <SidebarMenu>{[...works].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(work =>
    <WorkRow key={work.id} work={work} selected={selected} onNavigate={onNavigate} />)}</SidebarMenu>;
}

function StatusIcon({ work }: { work: Work }) {
  if (work.status === 'done') return <CircleCheck />;
  if (work.status === 'doing') return <LoaderCircle className="text-primary" />;
  if (work.status === 'abandoned') return <CircleDashed />;
  return <GitBranch />;
}

function WorkRow({ work, selected, onNavigate }: { work: Work; selected?: string; onNavigate: () => void }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  const go = () => { navigate({ page: 'work', work: work.id }); onNavigate(); };
  return <Collapsible asChild open={open} onOpenChange={setOpen}>
    <SidebarMenuItem>
      <SidebarMenuButton isActive={selected === work.id} onClick={go} tooltip={work.goal} title={statusLabel(t, work.status)}>
        <StatusIcon work={work} /><span className="truncate">{work.goal}</span>
      </SidebarMenuButton>
      {children.length > 0 && <>
        <CollapsibleTrigger asChild><SidebarMenuAction className="data-[state=open]:rotate-90" aria-label={`${open ? t('common.collapse') : t('common.expand')} ${work.goal}`}><ChevronRight /></SidebarMenuAction></CollapsibleTrigger>
        <CollapsibleContent><SidebarMenuSub>{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} />)}</SidebarMenuSub></CollapsibleContent>
      </>}
    </SidebarMenuItem>
  </Collapsible>;
}

function SubRow({ work, selected, onNavigate }: { work: Work; selected?: string; onNavigate: () => void }) {
  const t = useT();
  const children = work.children || [];
  return <SidebarMenuSubItem>
    <SidebarMenuSubButton isActive={selected === work.id} title={`${work.goal} · ${statusLabel(t, work.status)}`} onClick={() => { navigate({ page: 'work', work: work.id }); onNavigate(); }}>
      <StatusIcon work={work} /><span className="truncate">{work.goal}</span>
    </SidebarMenuSubButton>
    {children.length > 0 && <SidebarMenuSub>{children.map(child => <SubRow key={child.id} work={child} selected={selected} onNavigate={onNavigate} />)}</SidebarMenuSub>}
  </SidebarMenuSubItem>;
}
