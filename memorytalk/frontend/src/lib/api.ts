import { usePreferences } from './store';
import { t } from './i18n';

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}
export const pathPart = (path: string) => path.split('/').map(encodeURIComponent).join('/');

export async function api<T>(path: string, options: {
  method?: string; body?: unknown; work?: string; signal?: AbortSignal;
} = {}): Promise<T> {
  const user = usePreferences.getState().user;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (user) headers['X-Memory-Talk-User'] = user;
  if (options.work) headers['X-Memory-Talk-Work'] = options.work;
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method || 'GET', headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body), signal: options.signal,
    });
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') throw e;
    throw new ApiError(t('api.unreachable'), 0);
  }
  const result = await response.json().catch(() => null);
  if (!response.ok || result?.error) {
    const detail = Array.isArray(result?.detail)
      ? result.detail.map((d: { msg: string }) => d.msg).join(t('api.separator')) : result?.detail;
    throw new ApiError(result?.message || detail || t('api.failed', { status: response.status }), response.status, result?.error);
  }
  if (!result || !('data' in result)) throw new ApiError(t('api.badResponse'), response.status);
  return result.data as T;
}
