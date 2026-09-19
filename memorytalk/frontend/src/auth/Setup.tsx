import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import { useT } from '@/lib/i18n';
import type { LoginResult } from '@/lib/types';
import { ErrorState, Logo } from '@/components/Shared';

/** 首次:还没有 admin。设一个密码,建好就登录进去。 */
export function Setup() {
  const t = useT();
  const setSession = usePreferences(s => s.setSession);
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState(''); const [display, setDisplay] = useState('');
  const mutation = useMutation({
    mutationFn: () => api<LoginResult>('/auth/setup', { method: 'POST', body: { password, display_name: display.trim() } }),
    onSuccess: r => { setSession(r.user.name, r.user.role, r.token); void queryClient.invalidateQueries({ queryKey: ['auth'] }); },
  });
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = password.length >= 6 && confirm === password && !mutation.isPending;
  return <div className="flex min-h-dvh items-center justify-center bg-muted/40 p-4">
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center"><Logo className="mb-2 size-10" /><CardTitle className="text-xl">{t('auth.setupTitle')}</CardTitle><CardDescription>{t('auth.setupText')}</CardDescription></CardHeader>
      <CardContent><form className="grid gap-4" onSubmit={e => { e.preventDefault(); if (ready) mutation.mutate(); }}>
        <div className="grid gap-2"><Label htmlFor="setup-name">{t('settings.username')}</Label><Input id="setup-name" value="admin" disabled className="font-mono" /></div>
        <div className="grid gap-2"><Label htmlFor="setup-display">{t('settings.displayName')}</Label><Input id="setup-display" value={display} onChange={e => setDisplay(e.target.value)} placeholder={t('settings.displayNamePlaceholder')} autoFocus /></div>
        <div className="grid gap-2"><Label htmlFor="setup-password">{t('auth.password')}</Label><Input id="setup-password" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} /><p className="text-xs text-muted-foreground">{t('auth.passwordHint')}</p></div>
        <div className="grid gap-2"><Label htmlFor="setup-confirm">{t('auth.confirmPassword')}</Label><Input id="setup-confirm" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} required aria-invalid={mismatch} />{mismatch && <p className="text-xs text-destructive">{t('auth.mismatch')}</p>}</div>
        {mutation.isError && <ErrorState error={mutation.error} />}
        <Button type="submit" className="w-full" disabled={!ready}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('auth.setupSubmit')}</Button>
      </form></CardContent>
    </Card>
  </div>;
}
