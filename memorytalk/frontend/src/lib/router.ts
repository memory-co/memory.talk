import { useSyncExternalStore } from 'react';

/** library 页两件事分开带:filter = 左边列表在看哪层(all | 某层),layer + path = 右边打开的对象。 */
export type Route = { page: 'home' | 'work' | 'library' | 'settings'; work?: string; filter?: string; layer?: string; path?: string; file?: string };
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
  if (pathname === '/library') return { page: 'library', filter: query.get('filter') || 'all', layer: query.get('layer') || undefined, path: query.get('path') || undefined, file: query.get('file') || undefined };
  if (pathname === '/settings') return { page: 'settings' };
  return { page: 'home' };
}
export function navigate(route: Route) {
  const query = new URLSearchParams();
  if (route.filter && route.filter !== 'all') query.set('filter', route.filter);
  if (route.layer && route.path) { query.set('layer', route.layer); query.set('path', route.path); if (route.file) query.set('file', route.file); }
  window.location.hash = route.page === 'home' ? '/' : route.page === 'work'
    ? `/work/${encodeURIComponent(route.work || '')}`
    : `/${route.page}${query.size ? `?${query}` : ''}`;
}
