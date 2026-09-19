import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CircleHelp, KeyRound, LoaderCircle, LogOut, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem, useUsers } from '@/lib/queries';
import { usePreferences, type Locale } from '@/lib/store';
import { locales, useT } from '@/lib/i18n';
import type { User } from '@/lib/types';
import { ErrorState, Loading, Modal, UserAvatar } from '@/components/Shared';

export function Settings() {
  const t = useT();
  const users = useUsers();
  const system = useSystem();
  const user = usePreferences(s => s.user);
  const role = usePreferences(s => s.role);
  const locale = usePreferences(s => s.locale);
  const setLocale = usePreferences(s => s.setLocale);
  const [register, setRegister] = useState(false);
  const [passwordFor, setPasswordFor] = useState<string | null>(null);
  const me = users.data?.find(u => u.name === user);
  const logout = useMutation({ mutationFn: () => api('/auth/logout', { method: 'POST' }), onSettled: () => { usePreferences.getState().clearSession(); } });
  return <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 md:p-8">
    <div className="space-y-1"><h1 className="text-2xl font-semibold tracking-tight">{t('nav.settings')}</h1><p className="text-sm text-muted-foreground">{t('settings.subtitle')}</p></div>
    <Card>
      <CardHeader className="flex-row items-center gap-3 space-y-0">
        <UserAvatar className="size-10">{(me?.display_name || user).slice(0, 1).toUpperCase()}</UserAvatar>
        <div className="min-w-0 flex-1"><CardTitle className="flex items-center gap-2 text-base">{me?.display_name || user}<Badge variant={role === 'admin' ? 'default' : 'secondary'}>{role === 'admin' ? t('auth.roleAdmin') : t('auth.roleMember')}</Badge></CardTitle><CardDescription className="font-mono text-xs">{user}{me?.email ? ` · ${me.email}` : ''}</CardDescription></div>
        <Button variant="outline" size="sm" onClick={() => logout.mutate()} disabled={logout.isPending}><LogOut />{t('auth.logout')}</Button>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-2">
        <ProfileForm user={me} />
        <PasswordForm name={user} self />
      </CardContent>
    </Card>
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0"><div className="space-y-1.5"><CardTitle className="text-base">{t('settings.members')}</CardTitle><CardDescription>{role === 'admin' ? t('settings.membersTextAdmin') : t('settings.membersText')}</CardDescription></div>
        {role === 'admin' && <Button variant="outline" size="sm" onClick={() => setRegister(true)}><Plus />{t('settings.addMember')}</Button>}</CardHeader>
      <CardContent className="p-0 pb-2">{users.isPending ? <Loading /> : users.isError ? <div className="px-6"><ErrorState error={users.error} retry={() => { void users.refetch(); }} /></div> : <Table><TableBody>
        {users.data.map(item => <TableRow key={item.name}>
          <TableCell className="pl-6"><span className="flex items-center gap-3"><UserAvatar>{(item.display_name || item.name).slice(0, 1).toUpperCase()}</UserAvatar><span className="min-w-0"><span className="block truncate font-medium">{item.display_name || item.name}</span><span className="block truncate font-mono text-xs text-muted-foreground">{item.name}{item.email ? ` · ${item.email}` : ''}</span></span></span></TableCell>
          <TableCell className="text-xs text-muted-foreground">{item.role === 'admin' ? t('auth.roleAdmin') : t('auth.roleMember')}</TableCell>
          <TableCell className="pr-6 text-right">{role === 'admin' && item.name !== user && <Button variant="ghost" size="sm" onClick={() => setPasswordFor(item.name)}><KeyRound />{t('auth.setPassword')}</Button>}</TableCell>
        </TableRow>)}
      </TableBody></Table>}</CardContent>
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
    <Modal open={!!passwordFor} onClose={() => setPasswordFor(null)} title={t('auth.setPasswordFor', { name: passwordFor || '' })} description={t('auth.setPasswordText')}>
      {passwordFor && <PasswordForm name={passwordFor} onDone={() => setPasswordFor(null)} />}
    </Modal>
  </div>;
}

/** 改自己的显示名 / 邮箱。 */
function ProfileForm({ user }: { user?: User }) {
  const t = useT();
  const [display, setDisplay] = useState(user?.display_name || ''); const [email, setEmail] = useState(user?.email || '');
  useEffect(() => { setDisplay(user?.display_name || ''); setEmail(user?.email || ''); }, [user?.display_name, user?.email]);
  const mutation = useMutation({ mutationFn: () => api<User>(`/users/${encodeURIComponent(user!.name)}`, { method: 'PUT', body: { display_name: display.trim(), email: email.trim() } }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); toast.success(t('settings.profileSaved')); } });
  const dirty = !!user && (display.trim() !== user.display_name || email.trim() !== user.email);
  return <form className="grid gap-3" onSubmit={e => { e.preventDefault(); if (dirty) mutation.mutate(); }}>
    <p className="text-sm font-medium">{t('settings.profile')}</p>
    <div className="grid gap-2"><Label htmlFor="profile-display">{t('settings.displayName')}</Label><Input id="profile-display" value={display} onChange={e => setDisplay(e.target.value)} placeholder={t('settings.displayNamePlaceholder')} /></div>
    <div className="grid gap-2"><Label htmlFor="profile-email">{t('settings.email')}</Label><Input id="profile-email" type="email" value={email} onChange={e => setEmail(e.target.value)} /></div>
    {mutation.isError && <ErrorState error={mutation.error} />}
    <Button type="submit" size="sm" className="w-fit" disabled={!dirty || mutation.isPending}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('common.save')}</Button>
  </form>;
}

/** 改密码:self = 自己的(要旧密码,改完登录态作废、回登录页);否则 admin 给 name 设。 */
function PasswordForm({ name, self = false, onDone }: { name: string; self?: boolean; onDone?: () => void }) {
  const t = useT();
  const [old, setOld] = useState(''); const [next, setNext] = useState(''); const [confirm, setConfirm] = useState('');
  const mutation = useMutation({ mutationFn: () => api(`/users/${encodeURIComponent(name)}/password`, { method: 'PUT', body: { ...(self ? { old_password: old } : {}), new_password: next } }),
    onSuccess: () => { toast.success(self ? t('auth.passwordChangedRelogin') : t('auth.passwordSet', { name })); setOld(''); setNext(''); setConfirm(''); if (self) usePreferences.getState().clearSession(); else onDone?.(); } });
  const mismatch = confirm.length > 0 && confirm !== next;
  const ready = next.length >= 6 && confirm === next && (!self || !!old) && !mutation.isPending;
  return <form className="grid gap-3" onSubmit={e => { e.preventDefault(); if (ready) mutation.mutate(); }}>
    {self && <p className="text-sm font-medium">{t('auth.changePassword')}</p>}
    {self && <div className="grid gap-2"><Label htmlFor={`pw-old-${name}`}>{t('auth.oldPassword')}</Label><Input id={`pw-old-${name}`} type="password" autoComplete="current-password" value={old} onChange={e => setOld(e.target.value)} /></div>}
    <div className="grid gap-2"><Label htmlFor={`pw-new-${name}`}>{t('auth.newPassword')}</Label><Input id={`pw-new-${name}`} type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} minLength={6} autoFocus={!self} /><p className="text-xs text-muted-foreground">{t('auth.passwordHint')}</p></div>
    <div className="grid gap-2"><Label htmlFor={`pw-confirm-${name}`}>{t('auth.confirmPassword')}</Label><Input id={`pw-confirm-${name}`} type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} aria-invalid={mismatch} />{mismatch && <p className="text-xs text-destructive">{t('auth.mismatch')}</p>}</div>
    {mutation.isError && <ErrorState error={mutation.error} />}
    {self ? <Button type="submit" size="sm" className="w-fit" disabled={!ready}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('auth.changePassword')}</Button>
      : <DialogFooter><Button type="submit" disabled={!ready}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('auth.setPassword')}</Button></DialogFooter>}
  </form>;
}

/** admin 建账号。 */
function RegisterUser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const [name, setName] = useState(''); const [display, setDisplay] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const reset = () => { setName(''); setDisplay(''); setEmail(''); setPassword(''); };
  const mutation = useMutation({ mutationFn: () => api<User>('/users', { method: 'POST', body: { name: name.trim(), display_name: display.trim(), email: email.trim(), password } }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['users'] }); onClose(); reset(); toast.success(t('settings.added')); },
  });
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={t('settings.addMember')} description={t('settings.addMemberText')}>
    <form className="grid gap-4" onSubmit={e => { e.preventDefault(); mutation.mutate(); }}>
      <div className="grid gap-2"><Label htmlFor="user-name">{t('settings.username')}</Label><Input id="user-name" value={name} onChange={e => setName(e.target.value)} autoFocus required pattern="[A-Za-z0-9_.\-]{1,64}" placeholder="alice" /><p className="text-xs text-muted-foreground">{t('settings.usernameHint')}</p></div>
      <div className="grid gap-2"><Label htmlFor="user-display">{t('settings.displayName')}</Label><Input id="user-display" value={display} onChange={e => setDisplay(e.target.value)} placeholder={t('settings.displayNamePlaceholder')} /></div>
      <div className="grid gap-2"><Label htmlFor="user-email">{t('settings.email')}</Label><Input id="user-email" type="email" value={email} onChange={e => setEmail(e.target.value)} /></div>
      <div className="grid gap-2"><Label htmlFor="user-password">{t('auth.initialPassword')}</Label><Input id="user-password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} minLength={6} /><p className="text-xs text-muted-foreground">{t('auth.initialPasswordHint')}</p></div>
      {mutation.isError && <ErrorState error={mutation.error} />}
      <DialogFooter><Button type="submit" disabled={!name.trim() || (password.length > 0 && password.length < 6) || mutation.isPending}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('settings.add')}</Button></DialogFooter>
    </form>
  </Modal>;
}
