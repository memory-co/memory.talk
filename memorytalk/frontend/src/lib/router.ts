import { useSyncExternalStore } from 'react';

/** meta 页:filter = 左边列表在看哪层(all | 某层);layer + path (+ file) = 右边打开的文件;dir = 没打开文件时文件目录视图停在哪个目录(面包屑点中间一段用)。 */
export type Route = { page: 'home' | 'work' | 'meta' | 'settings'; work?: string; filter?: string; layer?: string; path?: string; file?: string; dir?: string };
const subscribe = (onChange: () => void) => {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
};
export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const [pathname, search] = hash.replace(/^#/, '').split('?');
  const query = new URLSearchParams(search || '');
  if (pathname?.startsWith('/work/')) {
    try { return { page: 'work', work: decodeURIComponent(pathname.slice(6)) }; }
    catch { return { page: 'home' }; }
  }
  if (pathname === '/meta') return { page: 'meta', filter: query.get('filter') || 'all', layer: query.get('layer') || undefined, path: query.get('path') || undefined, file: query.get('file') || undefined, dir: query.get('dir') ?? undefined };
  if (pathname === '/settings') return { page: 'settings' };
  return { page: 'home' };
}
export function navigate(route: Route) {
  const query = new URLSearchParams();
  if (route.filter && route.filter !== 'all') query.set('filter', route.filter);
  if (route.layer && route.path) { query.set('layer', route.layer); query.set('path', route.path); if (route.file) query.set('file', route.file); }
  if (route.dir !== undefined && !(route.layer && route.path)) query.set('dir', route.dir);
  window.location.hash = route.page === 'home' ? '/' : route.page === 'work'
    ? `/work/${encodeURIComponent(route.work || '')}`
    : `/${route.page}${query.size ? `?${query}` : ''}`;
}
