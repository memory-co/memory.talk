import { lazy, Suspense, useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, ChevronRight, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Search, Settings2, SquarePen, UserRound, X } from 'lucide-react';
import { useWorks, useUsers, useSystem } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { localeTag, useT } from '@/lib/i18n';
import { navigate, useRoute } from '@/lib/router';
import { flattenWorks } from '@/lib/types';
import { ErrorState, Loading, Logo, UserAvatar } from '@/components/Shared';
import { Button } from '@/components/ui/button';
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarGroup, SidebarGroupLabel, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarProvider, useSidebar } from '@/components/ui/sidebar';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { TaskTree } from './TaskTree';
import { Home } from './Home';
const SearchWorks = lazy(() => import('./SearchWorks').then(m => ({ default: m.SearchWorks })));
const Library = lazy(() => import('@/collections/Library').then(m => ({ default: m.Library })));
const Settings = lazy(() => import('@/settings/Settings').then(m => ({ default: m.Settings })));
const Workspace = lazy(() => import('./Workspace').then(m => ({ default: m.Workspace })));

export function Shell() {
  const collapsed = usePreferences(s => s.collapsed);
  const toggleSidebar = usePreferences(s => s.toggleSidebar);
  const locale = usePreferences(s => s.locale);
  useEffect(() => { document.documentElement.lang = localeTag(locale); }, [locale]);
  return <SidebarProvider open={!collapsed} onOpenChange={open => { if (open === collapsed) toggleSidebar(); }} className="h-dvh min-h-0 overflow-hidden"><ShellContent /></SidebarProvider>;
}
function ShellContent() {
  const t = useT();
  const route = useRoute();
  const works = useWorks(); const users = useUsers(); const system = useSystem();
  const user = usePreferences(s => s.user);
  const { isMobile, open, openMobile, toggleSidebar, setOpenMobile } = useSidebar();
  const [search, setSearch] = useState(false);
  const [searchLoaded, setSearchLoaded] = useState(false);
  useEffect(() => { if (search) setSearchLoaded(true); }, [search]);
  const [inspector, setInspector] = useState(false);
  const [selection, setSelection] = useState<{ layer: string; path?: string }>({ layer: 'card' });
  const currentUser = users.data?.find(u => u.name === user);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearch(true); }
      if (event.key === 'Escape' && !document.querySelector('[role="dialog"], [role="alertdialog"]')) setInspector(false);
    };
    window.addEventListener('keydown', listener); return () => window.removeEventListener('keydown', listener);
  }, []);
  useEffect(() => { setOpenMobile(false); }, [route.page, route.work, setOpenMobile]);
  const go = (page: 'home' | 'library' | 'settings') => { navigate({ page }); setOpenMobile(false); };
  const heading = route.page === 'home' ? t('nav.home') : route.page === 'library' ? t('nav.library') : route.page === 'settings' ? t('nav.settings') : t('nav.workspace');
  return <>
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>{t('nav.skip')}</a>
    <Sidebar aria-label={t('nav.main')}>
      <SidebarHeader className="px-3 pb-4 pt-5">
        <div className="flex items-center justify-between gap-2"><Button variant="ghost" className="gap-2 px-2 text-lg font-semibold" onClick={() => go('home')} aria-label={t('nav.homeLink')}><Logo small />memory.talk</Button><Button variant="ghost" size="icon" onClick={toggleSidebar} aria-label={isMobile ? t('nav.closeNav') : t('nav.collapseSidebar')}><PanelLeftClose /></Button></div>
        <SidebarMenu className="mt-4 gap-1">
          <SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'home'} onClick={() => go('home')}><SquarePen /><span>{t('nav.newWork')}</span><span className="ml-auto">＋</span></SidebarMenuButton></SidebarMenuItem>
          <SidebarMenuItem><SidebarMenuButton size="lg" onClick={() => { setOpenMobile(false); setSearch(true); }}><Search /><span>{t('nav.searchWork')}</span><kbd className="ml-auto text-xs text-muted-foreground">⌘ K</kbd></SidebarMenuButton></SidebarMenuItem>
          <SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'library'} onClick={() => go('library')}><BookOpen /><span>{t('nav.library')}</span></SidebarMenuButton></SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent><SidebarGroup className="pt-0"><SidebarGroupLabel className="justify-between"><span>{t('nav.yourWorks')}</span><span>{flattenWorks(works.data || []).length || ''}</span></SidebarGroupLabel>
        {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} /> : works.isPending ? <div className="space-y-3 px-2 py-3"><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-4/5" /><Skeleton className="h-5 w-3/5" /></div> : works.data.length ? <TaskTree works={works.data} selected={route.work} onNavigate={() => setOpenMobile(false)} /> : <p className="px-2 py-4 text-xs leading-6 text-muted-foreground">{t('nav.noWorks')}<br />{t('nav.noWorksHint')}</p>}
      </SidebarGroup></SidebarContent>
      <SidebarFooter className="gap-3 p-3"><div className="flex items-center gap-2 px-2 text-xs text-muted-foreground"><span className={`connection-dot ${system.isSuccess ? 'online' : ''}`} />{system.isSuccess ? t('nav.connected') : system.isError ? t('nav.disconnected') : t('nav.connecting')}</div>
        <SidebarMenu><SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'settings'} onClick={() => go('settings')}><UserAvatar>{currentUser ? (currentUser.display_name || currentUser.name).slice(0, 1).toUpperCase() : <UserRound size={18} />}</UserAvatar><span className="flex min-w-0 flex-1 flex-col gap-1"><strong className="truncate font-medium">{currentUser?.display_name || currentUser?.name || user || t('user.guest')}</strong><small className="truncate text-muted-foreground">{currentUser ? t('nav.teamWorkspace') : t('nav.chooseIdentity')}</small></span><Settings2 /></SidebarMenuButton></SidebarMenuItem></SidebarMenu>
      </SidebarFooter>
    </Sidebar>
    <div className="main-shell"><header className="topbar"><div className="topbar-left">{(isMobile || !open) && <Button variant="ghost" size="icon" aria-label={isMobile ? t('nav.openNav') : t('nav.expandSidebar')} onClick={toggleSidebar}><PanelLeftOpen size={19} /></Button>}<span className="topbar-title">{heading}</span><ChevronRight size={13} className="topbar-chevron" /><span className="topbar-subtitle">{route.page === 'work' ? t('nav.workSubtitle') : t('nav.subtitle')}</span></div>
      <div className="topbar-right">{route.page === 'work' ? <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" aria-label={inspector ? t('nav.closeInspector') : t('nav.openInspector')} onClick={() => setInspector(!inspector)}>{inspector ? <PanelRightClose /> : <PanelRightOpen />}</Button></TooltipTrigger><TooltipContent>{t('nav.library')}</TooltipContent></Tooltip> : <span className="topbar-edition"><span className="mini-dot" />memory.talk</span>}</div>
    </header>
      <div className="main-layout"><main id="main-content" tabIndex={-1} className={`main-content page-${route.page}`}>
        <Suspense fallback={<Loading />}>{route.page === 'home' ? <Home /> : route.page === 'work' && route.work ? <Workspace key={route.work} id={route.work} onLibrary={() => setInspector(true)} /> : route.page === 'library' ? <Library layer={route.layer || 'card'} path={route.path} onSelect={selection => navigate({ page: 'library', ...selection })} /> : <Settings />}</Suspense>
      </main>
      {route.page === 'work' && inspector && <aside className="inspector" aria-label={t('nav.inspector')}><div className="inspector-heading"><span><BookOpen size={17} />{t('nav.library')}</span><div><Button variant="ghost" size="icon" aria-label={t('nav.openLibraryPage')} onClick={() => navigate({ page: 'library', ...selection })}><ArrowUpRight size={16} /></Button><Button variant="ghost" size="icon" aria-label={t('nav.closeInspectorPanel')} onClick={() => setInspector(false)}><X size={17} /></Button></div></div><Suspense fallback={<Loading />}><Library compact {...selection} onSelect={setSelection} work={route.work} /></Suspense></aside>}
      </div>
    </div>
    {searchLoaded && <Suspense fallback={null}><SearchWorks open={search && !openMobile} onClose={() => setSearch(false)} /></Suspense>}
  </>;
}
