import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, CircleHelp, LoaderCircle, Plus, UserRound } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem, useUsers } from '@/lib/queries';
import { usePreferences, type Locale } from '@/lib/store';
import { locales, useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import type { User } from '@/lib/types';
import { ErrorState, Loading, Modal, UserAvatar } from '@/components/Shared';

function Option({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" role="radio" aria-checked={selected} onClick={onClick} className={cn('flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm transition-colors hover:bg-accent', selected && 'border-primary bg-accent')}>{children}{selected && <Check className="ml-auto size-4 shrink-0" />}</button>;
}

export function Settings() {
  const t = useT();
  const users = useUsers();
  const system = useSystem();
  const user = usePreferences(s => s.user);
  const setUser = usePreferences(s => s.setUser);
  const locale = usePreferences(s => s.locale);
  const setLocale = usePreferences(s => s.setLocale);
  const [register, setRegister] = useState(false);
  return <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 md:p-8">
    <div className="space-y-1"><h1 className="text-2xl font-semibold tracking-tight">{t('nav.settings')}</h1><p className="text-sm text-muted-foreground">{t('settings.subtitle')}</p></div>
    <Card>
      <CardHeader><CardTitle className="text-base">{t('settings.identity')}</CardTitle><CardDescription>{t('settings.identityText')}</CardDescription></CardHeader>
      <CardContent>{users.isPending ? <Loading /> : users.isError ? <ErrorState error={users.error} retry={() => { void users.refetch(); }} /> : <div className="grid gap-2" role="radiogroup" aria-label={t('settings.identity')}>
        <Option selected={!user} onClick={() => setUser('')}><UserAvatar><UserRound className="size-4" /></UserAvatar><span className="min-w-0"><span className="block font-medium">{t('user.guest')}</span><span className="block text-xs text-muted-foreground">{t('settings.anonymous')}</span></span></Option>
        {users.data.map(item => <Option key={item.name} selected={user === item.name} onClick={() => setUser(item.name)}><UserAvatar>{(item.display_name || item.name).slice(0, 1).toUpperCase()}</UserAvatar><span className="min-w-0"><span className="block truncate font-medium">{item.display_name || item.name}</span><span className="block truncate text-xs text-muted-foreground">{item.name}{item.email ? ` · ${item.email}` : ''}</span></span></Option>)}
        <Button variant="outline" className="justify-start" onClick={() => setRegister(true)}><Plus />{t('settings.addMember')}</Button>
      </div>}</CardContent>
    </Card>
    <Card>
      <CardHeader><CardTitle className="text-base">{t('settings.language')}</CardTitle><CardDescription>{t('settings.languageText')}</CardDescription></CardHeader>
      <CardContent><Select value={locale} onValueChange={value => setLocale(value as Locale)}><SelectTrigger className="w-48" aria-label={t('settings.language')}><SelectValue /></SelectTrigger><SelectContent>{locales.map(item => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent></Select></CardContent>
    </Card>
    <Card>
      <CardHeader><CardTitle className="text-base">{t('settings.environment')}</CardTitle></CardHeader>
      <CardContent className="p-0 pb-2">{system.isPending ? <Loading /> : system.isError ? <div className="px-6"><ErrorState error={system.error} retry={() => { void system.refetch(); }} /></div> : <Table><TableBody>
        {[[t('settings.serviceStatus'), <span key="s" className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-emerald-500" />{t('settings.connected')}</span>],
          [t('settings.workspace'), system.data.workspace], [t('settings.home'), system.data.home], [t('settings.store'), system.data.store.backend],
          [t('settings.ttyd'), system.data.ttyd_url || t('settings.notConfigured')]].map(([label, value], i) =>
          <TableRow key={i}><TableCell className="w-40 pl-6 text-muted-foreground">{label}</TableCell><TableCell className="break-all pr-6 font-mono text-xs">{value}</TableCell></TableRow>)}
      </TableBody></Table>}</CardContent>
    </Card>
    <Card>
      <CardHeader><CardTitle className="text-base">{t('settings.ttyd')}</CardTitle><CardDescription>{t('settings.ttydText')}</CardDescription></CardHeader>
      <CardContent><Alert><CircleHelp className="size-4" /><AlertTitle>{t('settings.ttydTitle')}</AlertTitle><AlertDescription className="space-y-2">
        <p>{t('settings.ttydHow')}</p>
        <pre className="overflow-auto rounded-md bg-muted p-2 font-mono text-xs">MEMORY_TALK_TTYD_URL={t('settings.ttydExample')}</pre>
        <p>{t('settings.ttydArg')} <code className="rounded bg-muted px-1 font-mono text-xs">?arg=&lt;session_id&gt;</code>{t('settings.ttydSocket')}<code className="rounded bg-muted px-1 font-mono text-xs">{system.data?.tmux_socket || 'memorytalk'}</code>{t('settings.ttydRestart')}</p>
      </AlertDescription></Alert></CardContent>
    </Card>
    <RegisterUser open={register} onClose={() => setRegister(false)} />
  </div>;
}

function RegisterUser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const [name, setName] = useState(''); const [display, setDisplay] = useState(''); const [email, setEmail] = useState('');
  const setUser = usePreferences(s => s.setUser);
  const mutation = useMutation({ mutationFn: () => api<User>('/users', { method: 'POST', body: { name: name.trim(), display_name: display.trim(), email: email.trim() } }),
    onSuccess: data => { setUser(data.name); void queryClient.invalidateQueries({ queryKey: ['users'] }); onClose(); setName(''); setDisplay(''); setEmail(''); toast.success(t('settings.added')); },
  });
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={t('settings.addMember')} description={t('settings.addMemberText')}>
    <form className="grid gap-4" onSubmit={e => { e.preventDefault(); mutation.mutate(); }}>
      <div className="grid gap-2"><Label htmlFor="user-name">{t('settings.username')}</Label><Input id="user-name" value={name} onChange={e => setName(e.target.value)} autoFocus required pattern="[A-Za-z0-9_.\-]{1,64}" placeholder="alice" /><p className="text-xs text-muted-foreground">{t('settings.usernameHint')}</p></div>
      <div className="grid gap-2"><Label htmlFor="user-display">{t('settings.displayName')}</Label><Input id="user-display" value={display} onChange={e => setDisplay(e.target.value)} placeholder={t('settings.displayNamePlaceholder')} /></div>
      <div className="grid gap-2"><Label htmlFor="user-email">{t('settings.email')}</Label><Input id="user-email" type="email" value={email} onChange={e => setEmail(e.target.value)} /></div>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <DialogFooter><Button type="submit" disabled={!name.trim() || mutation.isPending}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('settings.addAndUse')}</Button></DialogFooter>
    </form>
  </Modal>;
}
