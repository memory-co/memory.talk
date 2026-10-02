import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import { usePreferences } from './store';
import type { Work, User, Server, SystemInfo, Layer, WorkTrace } from './types';

export const useWorks = () => useQuery({ queryKey: ['works'], queryFn: ({ signal }) => api<Work[]>('/works', { signal }), refetchInterval: 15_000 });
export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: ({ signal }) => api<User[]>('/users', { signal }) });
export const useServers = () => useQuery({ queryKey: ['servers'], queryFn: ({ signal }) => api<Server[]>('/works/servers', { signal }) });
export const useSystem = () => useQuery({ queryKey: ['system'], queryFn: ({ signal }) => api<SystemInfo>('/system/info', { signal }) });
export const useLayers = () => useQuery({ queryKey: ['layers'], queryFn: ({ signal }) => api<Layer[]>('/metas/layers', { signal }) });
export function useWork(id: string) {
  const user = usePreferences(s => s.user);
  return useQuery({ queryKey: ['work', id, user], queryFn: ({ signal }) => api<Work>(`/works/${encodeURIComponent(id)}`, { signal }), refetchInterval: 15_000 });
}
/** 这个 work 自己的轨迹(不带子 work):右侧「动态」用。动了列 / 挪了工作单元 / 开关工作单元 / 归档以后刷新 ['trace', id]。 */
export const useTrace = (id: string) => useQuery({ queryKey: ['trace', id], queryFn: ({ signal }) => api<WorkTrace>(`/works/${encodeURIComponent(id)}/trace`, { signal }), refetchInterval: 5_000 });
