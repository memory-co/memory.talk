import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowUp, BookOpen, GitBranch, LoaderCircle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { navigate } from '@/lib/router';
import { useUsers, useWorks } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import { dateLabel, flattenWorks, statusLabel, type Work } from '@/lib/types';
import { ErrorState, Modal } from '@/components/Shared';

export function WorkComposer({ parent, onCreated, autoFocus = false }: {
  parent?: string; onCreated?: () => void; autoFocus?: boolean;
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
  const id = parent ? 'subwork-goal' : 'work-goal';
  return <form onSubmit={submit} className="space-y-3">
    <Label className="sr-only" htmlFor={id}>{t('home.goalLabel')}</Label>
    <Textarea id={id} value={goal} maxLength={2000} autoFocus={autoFocus} rows={3} className="min-h-24 resize-y text-base md:text-sm"
      onChange={e => setGoal(e.target.value)} placeholder={parent ? t('home.subworkPlaceholder') : t('home.workPlaceholder')}
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} />
    <div className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><GitBranch className="size-3.5" />{parent ? t('home.splitHint') : t('home.startHint')}<span className="hidden sm:inline"> · {t('home.hintEnter')} · {t('home.hintShift')}</span></span>
      <Button type="submit" size="icon" className="shrink-0 rounded-full" disabled={!goal.trim() || mutation.isPending} aria-label={t('home.create')}>
        {mutation.isPending ? <LoaderCircle className="animate-spin" /> : <ArrowUp />}
      </Button>
    </div>
    {mutation.isError && <ErrorState error={mutation.error} />}
  </form>;
}

export function NewSubwork({ parent, open, onClose }: { parent: string; open: boolean; onClose: () => void }) {
  const t = useT();
  return <Modal open={open} onClose={onClose} title={t('home.subworkTitle')} description={t('home.subworkDescription')}>
    <WorkComposer parent={parent} autoFocus onCreated={onClose} />
  </Modal>;
}

export function Home() {
  const t = useT();
  const locale = usePreferences(s => s.locale);
  const works = useWorks();
  const users = useUsers();
  const user = usePreferences(s => s.user);
  const profile = users.data?.find(u => u.name === user);
  const recent = flattenWorks(works.data || []).filter(w => !w.parent).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6);
  return <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-4 pt-8 md:p-8 md:pt-16">
    <div className="space-y-1">
      <h1 className="text-2xl font-semibold tracking-tight">{profile ? t('home.greetingNamed', { name: profile.display_name || profile.name }) : t('home.greeting')}</h1>
      <p className="text-sm text-muted-foreground">{t('home.description')}</p>
    </div>
    <Card><CardContent className="p-4"><WorkComposer /></CardContent></Card>
    <section className="space-y-3">
      <div className="flex items-center justify-between"><h2 className="text-sm font-medium">{t('home.recent')}</h2>
        <Button variant="ghost" size="sm" onClick={() => navigate({ page: 'library' })}><BookOpen />{t('home.fromLibrary')}</Button></div>
      {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} />
        : works.isPending ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[1, 2, 3].map(i => <Skeleton key={i} className="h-28" />)}</div>
        : recent.length ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recent.map(work => <Card key={work.id} role="button" tabIndex={0} className="flex cursor-pointer flex-col transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => navigate({ page: 'work', work: work.id })} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate({ page: 'work', work: work.id }); } }}>
            <CardHeader className="p-4 pb-2"><CardDescription className="text-xs">{dateLabel(work.created_at, locale)}</CardDescription><CardTitle className="line-clamp-2 text-sm font-medium leading-snug">{work.goal}</CardTitle></CardHeader>
            <CardFooter className="mt-auto p-4 pt-0"><Badge variant={work.status === 'doing' ? 'default' : 'secondary'}>{statusLabel(t, work.status)}</Badge></CardFooter>
          </Card>)}
        </div>
        : <Card className="border-dashed"><CardHeader className="flex-row items-start gap-3 space-y-0"><Sparkles className="mt-0.5 size-5 text-muted-foreground" /><div className="space-y-1"><CardTitle className="text-sm">{t('home.emptyTitle')}</CardTitle><CardDescription>{t('home.emptyText')}</CardDescription></div></CardHeader></Card>}
    </section>
  </div>;
}
