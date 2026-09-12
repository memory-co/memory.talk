import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { ChevronDown, ChevronRight, Circle, CircleCheck, GitBranch } from 'lucide-react';
import { navigate } from '@/lib/router';
import { statusLabels, type Work } from '@/lib/types';

export function TaskTree({ works, selected, onNavigate }: { works: Work[]; selected?: string; onNavigate: () => void }) {
  return <div className="work-tree">{[...works].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(work =>
    <WorkRow key={work.id} work={work} selected={selected} onNavigate={onNavigate} depth={0} />)}</div>;
}
function WorkRow({ work, selected, onNavigate, depth }: { work: Work; selected?: string; onNavigate: () => void; depth: number }) {
  const [open, setOpen] = useState(true);
  const children = work.children || [];
  return <Collapsible open={open} onOpenChange={setOpen}>
    <div className={`work-row ${selected === work.id ? 'selected' : ''}`} style={{ paddingLeft: 8 + Math.min(depth, 7) * 14 }}>
      {children.length ? <CollapsibleTrigger asChild><Button variant="ghost" className="tree-toggle h-6 w-[18px] p-0" aria-label={`${open ? '收起' : '展开'}${work.goal}`} aria-expanded={open}>{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</Button></CollapsibleTrigger>
        : <span className="tree-status" title={statusLabels[work.status]}>{work.status === 'done' ? <CircleCheck size={14} /> : work.status === 'doing' ? <span className="live-dot" /> : depth ? <Circle size={11} /> : <GitBranch size={14} />}</span>}
      <Button variant="ghost" className="work-row-label block h-auto truncate rounded-none px-0 py-2 text-left hover:bg-transparent" title={work.goal} aria-current={selected === work.id ? 'page' : undefined} onClick={() => { navigate({ page: 'work', work: work.id }); onNavigate(); }}>{work.goal}</Button>
      {work.status === 'doing' && children.length > 0 && <span className="live-dot" />}
    </div>
    <CollapsibleContent>{children.map(child => <WorkRow key={child.id} work={child} selected={selected} depth={depth + 1} onNavigate={onNavigate} />)}</CollapsibleContent>
  </Collapsible>;
}
