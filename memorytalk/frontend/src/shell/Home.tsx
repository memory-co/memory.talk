import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, ArrowUp, BookOpen, CornerDownLeft, GitBranch, LoaderCircle, Sparkles, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { navigate } from '@/lib/router';
import { useUsers, useWorks } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { dateLabel, flattenWorks, statusLabels, type Work } from '@/lib/types';
import { ErrorState, Logo, Modal } from '@/components/Shared';

export function WorkComposer({ parent, onCreated, compact = false }: {
  parent?: string; onCreated?: () => void; compact?: boolean;
}) {
  const [goal, setGoal] = useState('');
  const mutation = useMutation({
    mutationFn: () => api<Work>('/works', { method: 'POST', body: { goal: goal.trim(), parent: parent || null } }),
    onSuccess: work => {
      void queryClient.invalidateQueries({ queryKey: ['works'] });
      setGoal(''); onCreated?.(); navigate({ page: 'work', work: work.id });
      toast.success(parent ? '子工作已创建' : '工作已创建');
    },
  });
  const submit = (event?: FormEvent) => { event?.preventDefault(); if (goal.trim() && !mutation.isPending) mutation.mutate(); };
  return <form onSubmit={submit} className={compact ? 'work-composer compact' : 'work-composer'}>
    <label className="sr-only" htmlFor={compact ? 'subwork-goal' : 'work-goal'}>工作目标</label>
    <textarea id={compact ? 'subwork-goal' : 'work-goal'} value={goal} maxLength={2000} autoFocus={compact}
      onChange={e => setGoal(e.target.value)} placeholder={parent ? '这一步要完成什么？' : '描述你想完成的事…'}
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} />
    <div className="composer-footer"><span><GitBranch size={15} />{parent ? '拆分为子工作' : '从一个目标开始'}</span>
      <button type="submit" className="send-button" disabled={!goal.trim() || mutation.isPending} aria-label="创建工作">
        {mutation.isPending ? <LoaderCircle size={20} className="spin" /> : <ArrowUp size={20} />}
      </button>
    </div>
    {mutation.isError && <ErrorState error={mutation.error} />}
  </form>;
}

export function NewSubwork({ parent, open, onClose }: { parent: string; open: boolean; onClose: () => void }) {
  return <Modal open={open} onClose={onClose} title="拆分一步，继续推进" description="子工作会保留在当前工作下，拥有独立的会话。">
    <WorkComposer parent={parent} compact onCreated={onClose} />
  </Modal>;
}

export function Home() {
  const works = useWorks();
  const users = useUsers();
  const user = usePreferences(s => s.user);
  const profile = users.data?.find(u => u.name === user);
  const recent = flattenWorks(works.data || []).filter(w => !w.parent).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3);
  return <div className="home-page">
    <section className="welcome">
      <div className="welcome-eyebrow"><Logo small /><span>每一次开始，都有所积累</span></div>
      <h1>{profile ? `${profile.display_name || profile.name}，` : ''}今天想做些什么？</h1>
      <p className="welcome-description">让工作发生，让认知留下。</p>
      <WorkComposer />
      <div className="composer-hint"><CornerDownLeft size={12} /> Enter 创建工作 <span>·</span> Shift + Enter 换行</div>
      <div className="start-actions">
        <button onClick={() => { const field = document.getElementById('work-goal') as HTMLTextAreaElement; field?.focus(); }}><Terminal size={16} />开始一个工作<ArrowRight size={14} /></button>
        <button onClick={() => navigate({ page: 'library', layer: 'card' })}><BookOpen size={16} />从已有认知出发<ArrowRight size={14} /></button>
      </div>
    </section>
    <section className="recent-section">
      <div className="section-caption"><span>继续最近的工作</span><span className="caption-note">接着上次的思路</span></div>
      {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} /> : recent.length ? <div className="recent-grid">
        {recent.map(work => <button className="recent-card" key={work.id} onClick={() => navigate({ page: 'work', work: work.id })}>
          <div className="recent-card-top"><GitBranch size={17} /><span>{dateLabel(work.created_at)}</span></div>
          <h3>{work.goal}</h3><div className="recent-card-bottom"><span className={`status-text ${work.status}`}><i />{statusLabels[work.status]}</span><ArrowUpRightIcon /></div>
        </button>)}
      </div> : <div className="home-empty"><Sparkles size={18} /><div><strong>{works.isPending ? '正在寻找你的工作…' : '留一个起点给未来的自己'}</strong><p>创建第一项工作后，你可以随时从这里继续。</p></div></div>}
    </section>
    <footer className="home-footer"><span className="mini-dot" /> 工作在这里发生，记忆随之生长</footer>
  </div>;
}
function ArrowUpRightIcon() { return <ArrowRight size={16} className="recent-arrow" />; }
