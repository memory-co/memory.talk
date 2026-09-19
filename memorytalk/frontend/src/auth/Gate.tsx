import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { usePreferences } from '@/lib/store';
import type { AuthStatus } from '@/lib/types';
import { Loading } from '@/components/Shared';
import { Shell } from '@/shell/Shell';
import { Setup } from './Setup';
import { Login } from './Login';

/** 门(docs/designs/v5/auth.md):先问 /auth/status —— 没 admin → setup 页;没登录(或 token 不认了)→ 登录页;否则才是壳。 */
export function Gate() {
  const token = usePreferences(s => s.token);
  const setupRequired = usePreferences(s => s.setupRequired);
  const status = useQuery({ queryKey: ['auth', 'status', token], queryFn: ({ signal }) => api<AuthStatus>('/auth/status', { signal }), staleTime: 60_000 });
  useEffect(() => { if (status.data) usePreferences.getState().setSetupRequired(status.data.setup_required); }, [status.data]);
  useEffect(() => { if (!token) queryClient.removeQueries({ predicate: q => q.queryKey[0] !== 'auth' }); }, [token]);   // 换人 / 退出:别把上一个人的数据留在缓存里
  if (status.isPending) return <div className="flex h-dvh items-center justify-center"><Loading /></div>;
  if (setupRequired || status.data?.setup_required) return <Setup />;
  if (!token || (status.data && !status.data.authenticated)) return <Login />;
  return <Shell />;
}
