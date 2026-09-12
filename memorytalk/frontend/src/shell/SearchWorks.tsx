import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { useState } from 'react';
import { GitBranch } from 'lucide-react';
import { useWorks } from '@/lib/queries';
import { flattenWorks, statusLabels } from '@/lib/types';
import { navigate } from '@/lib/router';
import { ErrorState, Loading } from '@/components/Shared';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Command, CommandInput, CommandList, CommandEmpty, CommandItem, CommandGroup } from '@/components/ui/command';
export function SearchWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  const focus = useDialogFocus();
  const works = useWorks(); const [term, setTerm] = useState('');
  const filtered = flattenWorks(works.data || []).filter(work => work.goal.toLocaleLowerCase().includes(term.toLocaleLowerCase())).sort((a, b) => b.created_at.localeCompare(a.created_at));
  return <Dialog open={open} onOpenChange={value => { if (!value) onClose(); }}><DialogContent {...focus} className="gap-0 overflow-hidden p-0"><DialogTitle className="sr-only">搜索工作</DialogTitle><DialogDescription className="sr-only">输入工作名称，使用上下方向键选择，按 Enter 打开。</DialogDescription>
    <Command shouldFilter={false}><CommandInput value={term} onValueChange={setTerm} placeholder="输入工作名称…" aria-label="搜索工作名称" className="pr-8" /><CommandList>
      {works.isError ? <ErrorState error={works.error} /> : works.isPending ? <Loading label="正在加载工作…" /> : <><CommandEmpty>没有找到匹配的工作。</CommandEmpty><CommandGroup>{filtered.map(work => <CommandItem key={work.id} value={work.id} onSelect={() => { navigate({ page: 'work', work: work.id }); onClose(); }}><GitBranch /><span className="min-w-0 flex-1 truncate">{work.goal}</span><small className="text-muted-foreground">{statusLabels[work.status]}</small></CommandItem>)}</CommandGroup></>}
    </CommandList></Command>
  </DialogContent></Dialog>;
}
