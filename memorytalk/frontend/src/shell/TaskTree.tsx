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
  return <div>
    <div className={`work-row ${selected === work.id ? 'selected' : ''}`} style={{ paddingLeft: 8 + Math.min(depth, 7) * 14 }}>
      {children.length ? <button className="tree-toggle" aria-label={`${open ? '收起' : '展开'}${work.goal}`} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button>
        : <span className="tree-status" title={statusLabels[work.status]}>{work.status === 'done' ? <CircleCheck size={14} /> : work.status === 'doing' ? <span className="live-dot" /> : depth ? <Circle size={11} /> : <GitBranch size={14} />}</span>}
      <button className="work-row-label" title={work.goal} aria-current={selected === work.id ? 'page' : undefined} onClick={() => { navigate({ page: 'work', work: work.id }); onNavigate(); }}>{work.goal}</button>
      {work.status === 'doing' && children.length > 0 && <span className="live-dot" />}
    </div>
    {open && children.map(child => <WorkRow key={child.id} work={child} selected={selected} depth={depth + 1} onNavigate={onNavigate} />)}
  </div>;
}
