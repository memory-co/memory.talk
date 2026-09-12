import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, ArrowUp, BookOpen, CornerDownLeft, GitBranch, LoaderCircle, Sparkles, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { navigate } from '@/lib/router';
import { useUsers, useWorks } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { dateLabel, flattenWorks, statusLabel, type Work } from '@/lib/types';
import { ErrorState, Logo, Modal } from '@/components/Shared';

export function WorkComposer({ parent, onCreated, compact = false }: {
  parent?: string; onCreated?: () => void; compact?: boolean;
}) {
  const t = useT();
  const [goal, setGoal] = useState('');
  const mutation = useMutation({
    mutationFn: () => api<Work>('/works', { method: 'POST', body: { goal: goal.trim(), parent: parent || null } }),
    onSuccess: work => {
      void queryClient.invalidateQueries({ queryKey: ['works'] });
      setGoal(''); onCreated?.(); navigate({ page: 'work', work: work.id });
      toast.success(parent ? t('home.subworkCreated') : t('home.workCreated'));
    },
  });
  const submit = (event?: FormEvent) => { event?.preventDefault(); if (goal.trim() && !mutation.isPending) mutation.mutate(); };
  return <form onSubmit={submit} className={compact ? 'work-composer compact' : 'work-composer'}>
    <Label className="sr-only" htmlFor={compact ? 'subwork-goal' : 'work-goal'}>{t('home.goalLabel')}</Label>
    <Textarea className="border-0 p-0 shadow-none focus-visible:ring-0" id={compact ? 'subwork-goal' : 'work-goal'} value={goal} maxLength={2000} autoFocus={compact}
      onChange={e => setGoal(e.target.value)} placeholder={parent ? t('home.subworkPlaceholder') : t('home.workPlaceholder')}
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} />
    <div className="composer-footer"><span><GitBranch size={15} />{parent ? t('home.splitHint') : t('home.startHint')}</span>
      <Button variant="default" type="submit" size="icon" className="rounded-full" disabled={!goal.trim() || mutation.isPending} aria-label={t('home.create')}>
        {mutation.isPending ? <LoaderCircle size={20} className="spin" /> : <ArrowUp size={20} />}
      </Button>
    </div>
    {mutation.isError && <ErrorState error={mutation.error} />}
  </form>;
}

export function NewSubwork({ parent, open, onClose }: { parent: string; open: boolean; onClose: () => void }) {
  const t = useT();
  return <Modal open={open} onClose={onClose} title={t('home.subworkTitle')} description={t('home.subworkDescription')}>
    <WorkComposer parent={parent} compact onCreated={onClose} />
  </Modal>;
}

export function Home() {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const works = useWorks();
  const users = useUsers();
  const user = usePreferences(s => s.user);
  const profile = users.data?.find(u => u.name === user);
  const recent = flattenWorks(works.data || []).filter(w => !w.parent).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3);
  return <div className="home-page">
    <section className="welcome">
      <div className="welcome-eyebrow"><Logo small /><span>{t('home.eyebrow')}</span></div>
      <h1>{profile ? t('home.greetingNamed', { name: profile.display_name || profile.name }) : t('home.greeting')}</h1>
      <p className="welcome-description">{t('home.description')}</p>
      <WorkComposer />
      <div className="composer-hint"><CornerDownLeft size={12} /> {t('home.hintEnter')} <span>·</span> {t('home.hintShift')}</div>
      <div className="start-actions">
        <Button variant="outline" size="sm" onClick={() => { const field = document.getElementById('work-goal') as HTMLTextAreaElement; field?.focus(); }}><Terminal size={16} />{t('home.startWork')}<ArrowRight size={14} /></Button>
        <Button variant="outline" size="sm" onClick={() => navigate({ page: 'library', layer: 'card' })}><BookOpen size={16} />{t('home.fromLibrary')}<ArrowRight size={14} /></Button>
      </div>
    </section>
    <section className="recent-section">
      <div className="section-caption"><span>{t('home.recent')}</span><span className="caption-note">{t('home.recentNote')}</span></div>
      {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} /> : recent.length ? <div className="recent-grid">
        {recent.map(work => <Button variant="ghost" className="recent-card h-auto min-w-0 whitespace-normal grid grid-cols-[1fr_auto] md:block" key={work.id} onClick={() => navigate({ page: 'work', work: work.id })}>
          <div className="recent-card-top"><GitBranch size={17} /><span>{dateLabel(work.created_at, locale)}</span></div>
          <h3>{work.goal}</h3><div className="recent-card-bottom"><span className={`status-text ${work.status}`}><i />{statusLabel(t, work.status)}</span><ArrowUpRightIcon /></div>
        </Button>)}
      </div> : <div className="home-empty"><Sparkles size={18} /><div><strong>{works.isPending ? t('home.searching') : t('home.emptyTitle')}</strong><p>{t('home.emptyText')}</p></div></div>}
    </section>
    <footer className="home-footer"><span className="mini-dot" /> {t('home.footer')}</footer>
  </div>;
}
function ArrowUpRightIcon() { return <ArrowRight size={16} className="recent-arrow" />; }
