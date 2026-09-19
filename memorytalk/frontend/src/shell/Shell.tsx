import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { BookOpen, ChevronsUpDown, Menu, PanelRight, Search, SquarePen, UserRound, X } from 'lucide-react';
import { useWorks, useUsers, useSystem } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { localeTag, useT } from '@/lib/i18n';
import { navigate, useRoute } from '@/lib/router';
import { flattenWorks } from '@/lib/types';
import { cn } from '@/lib/utils';
import { ErrorState, Loading, Logo, UserAvatar } from '@/components/Shared';
import { Button } from '@/components/ui/button';
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb';
import { Separator } from '@/components/ui/separator';
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { TaskTree } from './TaskTree';
import { Home } from './Home';
const GlobalSearch = lazy(() => import('./GlobalSearch').then(m => ({ default: m.GlobalSearch })));
const Library = lazy(() => import('@/collections/Library').then(m => ({ default: m.Library })));
const Settings = lazy(() => import('@/settings/Settings').then(m => ({ default: m.Settings })));
const Workspace = lazy(() => import('./Workspace').then(m => ({ default: m.Workspace })));

/* 三种宽度,同一份侧栏:
   ≥1024  桌面:sidebar-07,展开 / 图标栏由用户切换(记在偏好里)
   768–1023 平板 / 横屏手机:默认图标栏,点开是挤开内容(不记偏好)
   <768   竖屏手机:侧栏是横向吸附滚动的第一列,主内容第二列,认知库面板第三列;左右滑动切换,顶栏按钮兜底 */

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    mql.addEventListener('change', onChange); setMatches(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

export function Shell() {
  const collapsed = usePreferences(s => s.collapsed);
  const toggleSidebar = usePreferences(s => s.toggleSidebar);
  const locale = usePreferences(s => s.locale);
  const large = useMediaQuery('(min-width: 1024px)');
  const [tabletOpen, setTabletOpen] = useState(false);
  useEffect(() => { document.documentElement.lang = localeTag(locale); }, [locale]);
  const open = large ? !collapsed : tabletOpen;
  const onOpenChange = (next: boolean) => { if (large) { if (next === collapsed) toggleSidebar(); } else setTabletOpen(next); };
  return <SidebarProvider open={open} onOpenChange={onOpenChange}><ShellContent /></SidebarProvider>;
}

/** 侧栏的内容:桌面放进 <Sidebar>,手机放进吸附列,同一份。 */
function SidebarBody({ onNavigate, onClose }: { onNavigate: () => void; onClose?: () => void }) {
  const t = useT();
  const route = useRoute();
  const works = useWorks(); const users = useUsers(); const system = useSystem();
  const user = usePreferences(s => s.user);
  const currentUser = users.data?.find(u => u.name === user);
  const go = (page: 'home' | 'library' | 'settings') => { navigate({ page }); onNavigate(); };
  return <>
    <SidebarHeader className="border-b border-sidebar-border">
      <SidebarMenu><SidebarMenuItem className="flex items-center gap-1">
        <SidebarMenuButton size="lg" onClick={() => go('home')} aria-label={t('nav.homeLink')}>
          <Logo /><div className="grid flex-1 text-left text-sm leading-tight"><span className="truncate font-semibold">memory.talk</span><span className="truncate text-xs text-muted-foreground">{system.isSuccess ? t('nav.connected') : system.isError ? t('nav.disconnected') : t('nav.connecting')}</span></div>
        </SidebarMenuButton>
        {onClose && <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={onClose} aria-label={t('nav.closeNav')}><X /></Button>}
      </SidebarMenuItem></SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup><SidebarGroupContent><SidebarMenu>
        <SidebarMenuItem><SidebarMenuButton isActive={route.page === 'home'} onClick={() => go('home')} tooltip={t('nav.newWork')}><SquarePen /><span>{t('nav.newWork')}</span></SidebarMenuButton></SidebarMenuItem>
        <SidebarMenuItem><SidebarMenuButton isActive={route.page === 'library'} onClick={() => go('library')} tooltip={t('nav.library')}><BookOpen /><span>{t('nav.library')}</span></SidebarMenuButton></SidebarMenuItem>
      </SidebarMenu></SidebarGroupContent></SidebarGroup>
      <SidebarGroup className="group-data-[collapsible=icon]:hidden">
        <SidebarGroupLabel>{t('nav.yourWorks')}<span className="ml-auto">{flattenWorks(works.data || []).length || ''}</span></SidebarGroupLabel>
        <SidebarGroupContent>
          {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} />
            : works.isPending ? <SidebarMenu>{[1, 2, 3].map(i => <SidebarMenuItem key={i}><SidebarMenuSkeleton /></SidebarMenuItem>)}</SidebarMenu>
            : works.data.length ? <TaskTree works={works.data} selected={route.work} onNavigate={onNavigate} />
            : <div className="space-y-2 px-2 py-2"><p className="text-xs text-muted-foreground">{t('nav.noWorks')} {t('nav.noWorksHint')}</p><Button variant="outline" size="sm" className="w-full" onClick={() => go('home')}><SquarePen />{t('nav.newWork')}</Button></div>}
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter className="border-t border-sidebar-border">
      <SidebarMenu><SidebarMenuItem>
        <SidebarMenuButton size="lg" isActive={route.page === 'settings'} onClick={() => go('settings')} tooltip={t('nav.settings')}>
          <UserAvatar>{currentUser ? (currentUser.display_name || currentUser.name).slice(0, 1).toUpperCase() : <UserRound className="size-4" />}</UserAvatar>
          <div className="grid flex-1 text-left text-sm leading-tight"><span className="truncate font-semibold">{currentUser?.display_name || currentUser?.name || user || t('user.guest')}</span><span className="truncate text-xs text-muted-foreground">{currentUser ? t('nav.teamWorkspace') : t('nav.chooseIdentity')}</span></div>
          <ChevronsUpDown className="ml-auto size-4" />
        </SidebarMenuButton>
      </SidebarMenuItem></SidebarMenu>
    </SidebarFooter>
  </>;
}

function Crumbs() {
  const t = useT();
  const route = useRoute();
  const works = useWorks();
  const pageName = route.page === 'home' ? t('nav.home') : route.page === 'library' ? t('nav.library') : route.page === 'settings' ? t('nav.settings') : t('nav.workspace');
  const currentWork = route.work ? flattenWorks(works.data || []).find(w => w.id === route.work) : undefined;
  const home = (e: React.MouseEvent) => { e.preventDefault(); navigate({ page: 'home' }); };
  return <Breadcrumb className="min-w-0"><BreadcrumbList className="flex-nowrap">
    <BreadcrumbItem className="hidden md:block"><BreadcrumbLink href="#/" onClick={home}>memory.talk</BreadcrumbLink></BreadcrumbItem>
    <BreadcrumbSeparator className="hidden md:block" />
    {currentWork ? <>
      <BreadcrumbItem><BreadcrumbLink href="#/" onClick={home}>{pageName}</BreadcrumbLink></BreadcrumbItem>
      <BreadcrumbSeparator />
      <BreadcrumbItem className="min-w-0"><BreadcrumbPage className="block max-w-[45vw] truncate">{currentWork.goal}</BreadcrumbPage></BreadcrumbItem>
    </> : <BreadcrumbItem><BreadcrumbPage>{pageName}</BreadcrumbPage></BreadcrumbItem>}
  </BreadcrumbList></Breadcrumb>;
}

function Page({ onLibrary, selection }: { onLibrary: () => void; selection: (s: { filter: string; layer?: string; path?: string; file?: string }) => void }) {
  const route = useRoute();
  return <Suspense fallback={<Loading />}>{route.page === 'home' ? <Home /> : route.page === 'work' && route.work ? <Workspace key={route.work} id={route.work} onLibrary={onLibrary} /> : route.page === 'library' ? <Library filter={route.filter || 'all'} layer={route.layer} path={route.path} file={route.file} onSelect={selection} /> : <Settings />}</Suspense>;
}

function ShellContent() {
  const t = useT();
  const route = useRoute();
  const { isMobile } = useSidebar();
  const [search, setSearch] = useState(false);
  const [searchLoaded, setSearchLoaded] = useState(false);
  useEffect(() => { if (search) setSearchLoaded(true); }, [search]);
  const [inspector, setInspector] = useState(false);
  const [selection, setSelection] = useState<{ filter: string; layer?: string; path?: string; file?: string }>({ filter: 'all' });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearch(true); }
      if (event.key === 'Escape' && !document.querySelector('[role="dialog"], [role="alertdialog"]')) setInspector(false);
    };
    window.addEventListener('keydown', listener); return () => window.removeEventListener('keydown', listener);
  }, []);
  const library = <Suspense fallback={<Loading />}><Library compact {...selection} onSelect={setSelection} work={route.work} /></Suspense>;
  const searchDialog = searchLoaded && <Suspense fallback={null}><GlobalSearch open={search} onClose={() => setSearch(false)} /></Suspense>;
  if (isMobile) return <><MobileShell onSearch={() => setSearch(true)} library={route.page === 'work' ? library : null} page={goInspector => <Page onLibrary={goInspector} selection={s => navigate({ page: 'library', ...s })} />} />{searchDialog}</>;
  return <>
    <Sidebar collapsible="icon"><SidebarBody onNavigate={() => undefined} /><SidebarRail /></Sidebar>
    <SidebarInset className="h-svh min-h-0 overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        <Crumbs />
        <div className="ml-auto flex items-center gap-1">
          <Button variant="outline" size="sm" className="h-8 gap-2 text-muted-foreground" onClick={() => setSearch(true)} aria-label={t('search.title')}><Search className="size-3.5" /><span className="hidden lg:inline">{t('search.button')}</span><kbd className="hidden rounded border bg-muted px-1 font-mono text-[10px] lg:inline">⌘K</kbd></Button>
          {route.page === 'work' && <Button variant="ghost" size="icon" aria-label={inspector ? t('nav.closeInspector') : t('nav.openInspector')} aria-pressed={inspector} onClick={() => setInspector(!inspector)}><PanelRight /></Button>}
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <main id="main-content" tabIndex={-1} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto outline-none">
          <Page onLibrary={() => setInspector(true)} selection={s => navigate({ page: 'library', ...s })} />
        </main>
        {route.page === 'work' && inspector && <aside className="flex w-80 shrink-0 flex-col border-l lg:w-96" aria-label={t('nav.inspector')}>
          <div className="flex h-12 shrink-0 items-center gap-2 border-b px-4 text-sm font-medium"><BookOpen className="size-4" />{t('nav.library')}</div>
          <div className="flex min-h-0 flex-1 flex-col">{library}</div>
        </aside>}
      </div>
    </SidebarInset>
    {searchDialog}
  </>;
}

/** 竖屏手机:侧栏 | 主内容 | 认知库面板 三列横向吸附。 */
function MobileShell({ onSearch, library, page }: { onSearch: () => void; library: ReactNode; page: (goInspector: () => void) => ReactNode }) {
  const t = useT();
  const route = useRoute();
  const track = useRef<HTMLDivElement>(null);
  const [col, setCol] = useState(1);
  const goTo = useCallback((index: number, smooth = true) => {
    const el = track.current; const target = el?.children[index] as HTMLElement | undefined;
    if (el && target) el.scrollTo({ left: target.offsetLeft, behavior: smooth ? 'smooth' : 'auto' });
  }, []);
  useEffect(() => { goTo(1, false); }, [goTo]);                                       // 初始停在主内容
  useEffect(() => { goTo(1); }, [route.page, route.work, route.filter, route.layer, route.path, goTo]);   // 导航后回到主内容
  const onScroll = () => { const el = track.current; if (el) setCol(Math.round(el.scrollLeft / el.clientWidth)); };   // 三列等宽:一列一页
  const safe = 'pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]';
  return <div ref={track} onScroll={onScroll} className="flex h-dvh w-full snap-x snap-mandatory overflow-x-auto overflow-y-hidden overscroll-x-contain bg-background [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
    <div className={cn('group flex h-full w-full shrink-0 snap-start flex-col bg-sidebar text-sidebar-foreground', safe)} data-state="expanded" aria-label={t('nav.main')} aria-hidden={col !== 0}>
      <SidebarBody onNavigate={() => goTo(1)} onClose={() => goTo(1)} />
    </div>
    <div className={cn('flex h-full w-full shrink-0 snap-start flex-col', safe)} aria-hidden={col !== 1}>
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
        <Button variant="ghost" size="icon" aria-label={col === 0 ? t('nav.closeNav') : t('nav.openNav')} aria-expanded={col === 0} onClick={() => goTo(col === 0 ? 1 : 0)}><Menu /></Button>
        <Crumbs />
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={onSearch} aria-label={t('search.title')}><Search /></Button>
          {library && <Button variant="ghost" size="icon" aria-label={col === 2 ? t('nav.closeInspector') : t('nav.openInspector')} aria-pressed={col === 2} onClick={() => goTo(col === 2 ? 1 : 2)}><PanelRight /></Button>}
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto outline-none">{page(() => goTo(2))}</main>
    </div>
    {library && <div className={cn('flex h-full w-full shrink-0 snap-start flex-col', safe)} aria-label={t('nav.inspector')} aria-hidden={col !== 2}>
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4 text-sm font-medium"><BookOpen className="size-4" />{t('nav.library')}<Button variant="ghost" size="icon" className="ml-auto size-8" aria-label={t('nav.closeInspectorPanel')} onClick={() => goTo(1)}><X /></Button></div>
      <div className="flex min-h-0 flex-1 flex-col">{library}</div>
    </div>}
  </div>;
}
