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

export function Login() {
  const t = useT();
  const setSession = usePreferences(s => s.setSession);
  const last = usePreferences(s => s.user);                               // 上次登录的名字(退出时留着的)
  const [name, setName] = useState(last || ''); const [password, setPassword] = useState('');
  const mutation = useMutation({
    mutationFn: () => api<LoginResult>('/auth/login', { method: 'POST', body: { name: name.trim(), password } }),
    onSuccess: r => { setSession(r.user.name, r.user.role, r.token); void queryClient.invalidateQueries({ queryKey: ['auth'] }); },
  });
  const ready = !!name.trim() && !!password && !mutation.isPending;
  return <div className="flex min-h-dvh items-center justify-center bg-muted/40 p-4">
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center text-center"><Logo className="mb-2 size-10" /><CardTitle className="text-xl">{t('auth.loginTitle')}</CardTitle><CardDescription>{t('auth.loginText')}</CardDescription></CardHeader>
      <CardContent><form className="grid gap-4" onSubmit={e => { e.preventDefault(); if (ready) mutation.mutate(); }}>
        <div className="grid gap-2"><Label htmlFor="login-name">{t('settings.username')}</Label><Input id="login-name" value={name} onChange={e => setName(e.target.value)} autoComplete="username" autoFocus={!last} required /></div>
        <div className="grid gap-2"><Label htmlFor="login-password">{t('auth.password')}</Label><Input id="login-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} autoFocus={!!last} required /></div>
        {mutation.isError && <ErrorState error={mutation.error} />}
        <Button type="submit" className="w-full" disabled={!ready}>{mutation.isPending && <LoaderCircle className="animate-spin" />}{t('auth.loginSubmit')}</Button>
      </form></CardContent>
    </Card>
  </div>;
}
