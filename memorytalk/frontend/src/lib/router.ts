import { useSyncExternalStore } from 'react';

export type Route = { page: 'home' | 'work' | 'library' | 'settings'; work?: string; layer?: string; path?: string };
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
  if (pathname === '/library') return { page: 'library', layer: query.get('layer') || 'all', path: query.get('path') || undefined };
  if (pathname === '/settings') return { page: 'settings' };
  return { page: 'home' };
}
export function navigate(route: Route) {
  const query = new URLSearchParams();
  if (route.layer) query.set('layer', route.layer);
  if (route.path) query.set('path', route.path);
  window.location.hash = route.page === 'home' ? '/' : route.page === 'work'
    ? `/work/${encodeURIComponent(route.work || '')}`
    : `/${route.page}${query.size ? `?${query}` : ''}`;
}
