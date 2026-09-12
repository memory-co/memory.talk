import { lazy, Suspense, useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, ChevronRight, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Search, Settings2, SquarePen, UserRound, X } from 'lucide-react';
import { useWorks, useUsers, useSystem } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
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
  return <SidebarProvider open={!collapsed} onOpenChange={open => { if (open === collapsed) toggleSidebar(); }} className="h-dvh min-h-0 overflow-hidden"><ShellContent /></SidebarProvider>;
}
function ShellContent() {
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
  const heading = route.page === 'home' ? '工作台' : route.page === 'library' ? '认知库' : route.page === 'settings' ? '设置' : '工作空间';
  return <>
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>跳转到主要内容</a>
    <Sidebar aria-label="主导航">
      <SidebarHeader className="px-3 pb-4 pt-5">
        <div className="flex items-center justify-between gap-2"><Button variant="ghost" className="gap-2 px-2 text-lg font-semibold" onClick={() => go('home')} aria-label="memory.talk 首页"><Logo small />memory.talk</Button><Button variant="ghost" size="icon" onClick={toggleSidebar} aria-label={isMobile ? '收起导航' : '收起侧栏'}><PanelLeftClose /></Button></div>
        <SidebarMenu className="mt-4 gap-1">
          <SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'home'} onClick={() => go('home')}><SquarePen /><span>新建工作</span><span className="ml-auto">＋</span></SidebarMenuButton></SidebarMenuItem>
          <SidebarMenuItem><SidebarMenuButton size="lg" onClick={() => { setOpenMobile(false); setSearch(true); }}><Search /><span>搜索工作</span><kbd className="ml-auto text-xs text-muted-foreground">⌘ K</kbd></SidebarMenuButton></SidebarMenuItem>
          <SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'library'} onClick={() => go('library')}><BookOpen /><span>认知库</span></SidebarMenuButton></SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent><SidebarGroup className="pt-0"><SidebarGroupLabel className="justify-between"><span>你的工作</span><span>{flattenWorks(works.data || []).length || ''}</span></SidebarGroupLabel>
        {works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} /> : works.isPending ? <div className="space-y-3 px-2 py-3"><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-4/5" /><Skeleton className="h-5 w-3/5" /></div> : works.data.length ? <TaskTree works={works.data} selected={route.work} onNavigate={() => setOpenMobile(false)} /> : <p className="px-2 py-4 text-xs leading-6 text-muted-foreground">还没有工作<br />从一个想法开始。</p>}
      </SidebarGroup></SidebarContent>
      <SidebarFooter className="gap-3 p-3"><div className="flex items-center gap-2 px-2 text-xs text-muted-foreground"><span className={`connection-dot ${system.isSuccess ? 'online' : ''}`} />{system.isSuccess ? '工作空间已连接' : system.isError ? '工作空间未连接' : '正在连接工作空间'}</div>
        <SidebarMenu><SidebarMenuItem><SidebarMenuButton size="lg" isActive={route.page === 'settings'} onClick={() => go('settings')}><UserAvatar>{currentUser ? (currentUser.display_name || currentUser.name).slice(0, 1).toUpperCase() : <UserRound size={18} />}</UserAvatar><span className="flex min-w-0 flex-1 flex-col gap-1"><strong className="truncate font-medium">{currentUser?.display_name || currentUser?.name || user || '访客'}</strong><small className="truncate text-muted-foreground">{currentUser ? '团队工作空间' : '选择或添加你的身份'}</small></span><Settings2 /></SidebarMenuButton></SidebarMenuItem></SidebarMenu>
      </SidebarFooter>
    </Sidebar>
    <div className="main-shell"><header className="topbar"><div className="topbar-left">{(isMobile || !open) && <Button variant="ghost" size="icon" aria-label={isMobile ? '打开导航' : '展开侧栏'} onClick={toggleSidebar}><PanelLeftOpen size={19} /></Button>}<span className="topbar-title">{heading}</span><ChevronRight size={13} className="topbar-chevron" /><span className="topbar-subtitle">{route.page === 'work' ? '专注当下的这件事' : '做事，也留下认知'}</span></div>
      <div className="topbar-right">{route.page === 'work' ? <Tooltip><TooltipTrigger asChild><Button variant="ghost" size="icon" aria-label={inspector ? '收起认知库面板' : '打开认知库面板'} onClick={() => setInspector(!inspector)}>{inspector ? <PanelRightClose /> : <PanelRightOpen />}</Button></TooltipTrigger><TooltipContent>认知库</TooltipContent></Tooltip> : <span className="topbar-edition"><span className="mini-dot" />memory.talk</span>}</div>
    </header>
      <div className="main-layout"><main id="main-content" tabIndex={-1} className={`main-content page-${route.page}`}>
        <Suspense fallback={<Loading />}>{route.page === 'home' ? <Home /> : route.page === 'work' && route.work ? <Workspace key={route.work} id={route.work} onLibrary={() => setInspector(true)} /> : route.page === 'library' ? <Library layer={route.layer || 'card'} path={route.path} onSelect={selection => navigate({ page: 'library', ...selection })} /> : <Settings />}</Suspense>
      </main>
      {route.page === 'work' && inspector && <aside className="inspector" aria-label="认知库面板"><div className="inspector-heading"><span><BookOpen size={17} />认知库</span><div><Button variant="ghost" size="icon" aria-label="在主页面打开认知库" onClick={() => navigate({ page: 'library', ...selection })}><ArrowUpRight size={16} /></Button><Button variant="ghost" size="icon" aria-label="关闭认知库面板" onClick={() => setInspector(false)}><X size={17} /></Button></div></div><Suspense fallback={<Loading />}><Library compact {...selection} onSelect={setSelection} work={route.work} /></Suspense></aside>}
      </div>
    </div>
    {searchLoaded && <Suspense fallback={null}><SearchWorks open={search && !openMobile} onClose={() => setSearch(false)} /></Suspense>}
  </>;
}
