import { lazy, Suspense, useEffect, useState } from 'react';
import { BookOpen, ChevronsUpDown, PanelRight, Search, SquarePen, UserRound, X } from 'lucide-react';
import { useWorks, useUsers, useSystem } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { localeTag, useT } from '@/lib/i18n';
import { navigate, useRoute } from '@/lib/router';
import { flattenWorks } from '@/lib/types';
import { ErrorState, Loading, Logo, UserAvatar } from '@/components/Shared';
import { Button } from '@/components/ui/button';
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb';
import { Separator } from '@/components/ui/separator';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSkeleton, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
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
  return <SidebarProvider open={!collapsed} onOpenChange={open => { if (open === collapsed) toggleSidebar(); }}><ShellContent /></SidebarProvider>;
}

function AppSidebar({ onSearch }: { onSearch: () => void }) {
  const t = useT();
  const route = useRoute();
  const works = useWorks(); const users = useUsers(); const system = useSystem();
  const user = usePreferences(s => s.user);
  const { setOpenMobile } = useSidebar();
  const currentUser = users.data?.find(u => u.name === user);
  const go = (page: 'home' | 'library' | 'settings') => { navigate({ page }); setOpenMobile(false); };
  return <Sidebar collapsible="icon">
    <SidebarHeader>
      <SidebarMenu><SidebarMenuItem>
        <SidebarMenuButton size="lg" onClick={() => go('home')} aria-label={t('nav.homeLink')}>
          <Logo /><div className="grid flex-1 text-left text-sm leading-tight"><span className="truncate font-semibold">memory.talk</span><span className="truncate text-xs text-muted-foreground">{system.isSuccess ? t('nav.connected') : system.isError ? t('nav.disconnected') : t('nav.connecting')}</span></div>
        </SidebarMenuButton>
      </SidebarMenuItem></SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup><SidebarGroupContent><SidebarMenu>
        <SidebarMenuItem><SidebarMenuButton isActive={route.page === 'home'} onClick={() => go('home')} tooltip={t('nav.newWork')}><SquarePen /><span>{t('nav.newWork')}</span></SidebarMenuButton></SidebarMenuItem>
        <SidebarMenuItem><SidebarMenuButton onClick={() => { setOpenMobile(false); onSearch(); }} tooltip={t('nav.searchWork')}><Search /><span>{t('nav.searchWork')}</span><kbd className="ml-auto text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">⌘K</kbd></SidebarMenuButton></SidebarMenuItem>
        <SidebarMenuItem><SidebarMenuButton isActive={route.page === 'library'} onClick={() => go('library')} tooltip={t('nav.library')}><BookOpen /><span>{t('nav.library')}</span></SidebarMenuButton></SidebarMenuItem>
      </SidebarMenu></SidebarGroupContent></SidebarGroup>
      <SidebarGroup className="group-data-[collapsible=icon]:hidden">
        <SidebarGroupLabel>{t('nav.yourWorks')}<span className="ml-auto">{flattenWorks(works.data || []).length || ''}</span></SidebarGroupLabel>
        <SidebarGroupContent>
          {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} />
            : works.isPending ? <SidebarMenu>{[1, 2, 3].map(i => <SidebarMenuItem key={i}><SidebarMenuSkeleton /></SidebarMenuItem>)}</SidebarMenu>
            : works.data.length ? <TaskTree works={works.data} selected={route.work} onNavigate={() => setOpenMobile(false)} />
            : <p className="px-2 py-2 text-xs text-muted-foreground">{t('nav.noWorks')} {t('nav.noWorksHint')}</p>}
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <SidebarMenu><SidebarMenuItem>
        <SidebarMenuButton size="lg" isActive={route.page === 'settings'} onClick={() => go('settings')} tooltip={t('nav.settings')}>
          <UserAvatar>{currentUser ? (currentUser.display_name || currentUser.name).slice(0, 1).toUpperCase() : <UserRound className="size-4" />}</UserAvatar>
          <div className="grid flex-1 text-left text-sm leading-tight"><span className="truncate font-semibold">{currentUser?.display_name || currentUser?.name || user || t('user.guest')}</span><span className="truncate text-xs text-muted-foreground">{currentUser ? t('nav.teamWorkspace') : t('nav.chooseIdentity')}</span></div>
          <ChevronsUpDown className="ml-auto size-4" />
        </SidebarMenuButton>
      </SidebarMenuItem></SidebarMenu>
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>;
}

function ShellContent() {
  const t = useT();
  const route = useRoute();
  const works = useWorks();
  const { isMobile, openMobile, setOpenMobile } = useSidebar();
  const [search, setSearch] = useState(false);
  const [searchLoaded, setSearchLoaded] = useState(false);
  useEffect(() => { if (search) setSearchLoaded(true); }, [search]);
  const [inspector, setInspector] = useState(false);
  const [selection, setSelection] = useState<{ layer: string; path?: string }>({ layer: 'card' });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearch(true); }
      if (event.key === 'Escape' && !document.querySelector('[role="dialog"], [role="alertdialog"]')) setInspector(false);
    };
    window.addEventListener('keydown', listener); return () => window.removeEventListener('keydown', listener);
  }, []);
  useEffect(() => { setOpenMobile(false); }, [route.page, route.work, setOpenMobile]);
  const pageName = route.page === 'home' ? t('nav.home') : route.page === 'library' ? t('nav.library') : route.page === 'settings' ? t('nav.settings') : t('nav.workspace');
  const currentWork = route.work ? flattenWorks(works.data || []).find(w => w.id === route.work) : undefined;
  const library = <Suspense fallback={<Loading />}><Library compact {...selection} onSelect={setSelection} work={route.work} /></Suspense>;
  return <>
    <AppSidebar onSearch={() => setSearch(true)} />
    <SidebarInset className="h-svh min-h-0 overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        <Breadcrumb className="min-w-0"><BreadcrumbList className="flex-nowrap">
          <BreadcrumbItem className="hidden md:block"><BreadcrumbLink href="#/" onClick={e => { e.preventDefault(); navigate({ page: 'home' }); }}>memory.talk</BreadcrumbLink></BreadcrumbItem>
          <BreadcrumbSeparator className="hidden md:block" />
          {currentWork ? <>
            <BreadcrumbItem><BreadcrumbLink href="#/" onClick={e => { e.preventDefault(); navigate({ page: 'home' }); }}>{pageName}</BreadcrumbLink></BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem className="min-w-0"><BreadcrumbPage className="block max-w-[40vw] truncate">{currentWork.goal}</BreadcrumbPage></BreadcrumbItem>
          </> : <BreadcrumbItem><BreadcrumbPage>{pageName}</BreadcrumbPage></BreadcrumbItem>}
        </BreadcrumbList></Breadcrumb>
        {route.page === 'work' && <Button variant="ghost" size="icon" className="ml-auto" aria-label={inspector ? t('nav.closeInspector') : t('nav.openInspector')} aria-pressed={inspector} onClick={() => setInspector(!inspector)}><PanelRight /></Button>}
      </header>
      <div className="flex min-h-0 flex-1">
        <main id="main-content" tabIndex={-1} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto outline-none">
          <Suspense fallback={<Loading />}>{route.page === 'home' ? <Home /> : route.page === 'work' && route.work ? <Workspace key={route.work} id={route.work} onLibrary={() => setInspector(true)} /> : route.page === 'library' ? <Library layer={route.layer || 'card'} path={route.path} onSelect={selection => navigate({ page: 'library', ...selection })} /> : <Settings />}</Suspense>
        </main>
        {route.page === 'work' && inspector && !isMobile && <aside className="flex w-96 shrink-0 flex-col border-l" aria-label={t('nav.inspector')}>
          <div className="flex h-12 shrink-0 items-center gap-2 border-b px-4 text-sm font-medium"><BookOpen className="size-4" />{t('nav.library')}<Button variant="ghost" size="icon" className="ml-auto size-7" aria-label={t('nav.closeInspectorPanel')} onClick={() => setInspector(false)}><X className="size-4" /></Button></div>
          <div className="flex min-h-0 flex-1 flex-col">{library}</div>
        </aside>}
      </div>
    </SidebarInset>
    {route.page === 'work' && isMobile && <Sheet open={inspector} onOpenChange={setInspector}><SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
      <SheetHeader className="border-b px-4 py-3 text-left"><SheetTitle className="text-sm">{t('nav.library')}</SheetTitle><SheetDescription className="sr-only">{t('nav.inspector')}</SheetDescription></SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col">{library}</div>
    </SheetContent></Sheet>}
    {searchLoaded && <Suspense fallback={null}><SearchWorks open={search && !openMobile} onClose={() => setSearch(false)} /></Suspense>}
  </>;
}
