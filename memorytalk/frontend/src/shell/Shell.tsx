import { useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, ChevronRight, GitBranch, Menu, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Search, Settings2, SquarePen, UserRound, X } from 'lucide-react';
import { useWorks, useUsers, useSystem } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { navigate, useRoute } from '@/lib/router';
import { flattenWorks, statusLabels } from '@/lib/types';
import { ErrorState, Logo, Modal } from '@/components/Shared';
import { Library } from '@/collections/Library';
import { Settings } from '@/settings/Settings';
import { TaskTree } from './TaskTree';
import { Home } from './Home';
import { Workspace } from './Workspace';

export function Shell() {
  const route = useRoute();
  const works = useWorks(); const users = useUsers(); const system = useSystem();
  const collapsed = usePreferences(s => s.collapsed); const toggleSidebar = usePreferences(s => s.toggleSidebar);
  const user = usePreferences(s => s.user);
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState(false);
  const [inspector, setInspector] = useState(false);
  const [selection, setSelection] = useState<{ layer: string; path?: string }>({ layer: 'card' });
  const currentUser = users.data?.find(u => u.name === user);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearch(true); }
      if (event.key === 'Escape') { setMobile(false); setInspector(false); }
    };
    window.addEventListener('keydown', listener); return () => window.removeEventListener('keydown', listener);
  }, []);
  useEffect(() => { setMobile(false); }, [route.page, route.work]);
  const go = (page: 'home' | 'library' | 'settings') => { navigate({ page }); setMobile(false); };
  const heading = route.page === 'home' ? '工作台' : route.page === 'library' ? '认知库' : route.page === 'settings' ? '设置' : '工作空间';
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''} ${mobile ? 'mobile-open' : ''}`}>
    <a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>跳转到主要内容</a>
    {mobile && <button className="sidebar-backdrop" aria-label="收起导航" onClick={() => setMobile(false)} />}
    <aside className="sidebar" aria-label="主导航">
      <div className="sidebar-brand"><button className="brand" onClick={() => go('home')} aria-label="memory.talk 首页"><Logo small /><span>memory<span className="brand-dot">.</span>talk</span></button><button className="icon-button sidebar-collapse" onClick={() => { toggleSidebar(); setMobile(false); }} aria-label="收起侧栏"><PanelLeftClose size={18} /></button><button className="icon-button mobile-close" onClick={() => setMobile(false)} aria-label="收起导航"><X size={18} /></button></div>
      <nav className="primary-nav"><button className={route.page === 'home' ? 'active' : ''} onClick={() => go('home')}><SquarePen size={18} /><span>新建工作</span><PlusHint /></button><button onClick={() => setSearch(true)}><Search size={18} /><span>搜索工作</span><kbd>⌘ K</kbd></button><button className={route.page === 'library' ? 'active' : ''} onClick={() => go('library')}><BookOpen size={18} /><span>认知库</span></button></nav>
      <div className="sidebar-section-label"><span>你的工作</span><span>{flattenWorks(works.data || []).length || ''}</span></div>
      <div className="sidebar-works">{works.isError ? <ErrorState error={works.error} retry={() => { void works.refetch(); }} /> : works.isPending ? <div className="sidebar-skeleton"><i /><i /><i /></div> : works.data.length ? <TaskTree works={works.data} selected={route.work} onNavigate={() => setMobile(false)} /> : <div className="sidebar-empty">还没有工作<br /><span>从一个想法开始。</span></div>}</div>
      <div className="sidebar-bottom"><div className="workspace-note"><span className={`connection-dot ${system.isSuccess ? 'online' : ''}`} /><span>{system.isSuccess ? '工作空间已连接' : system.isError ? '工作空间未连接' : '正在连接工作空间'}</span></div>
        <button className={`profile-button ${route.page === 'settings' ? 'active' : ''}`} onClick={() => go('settings')}><span className="avatar">{currentUser ? (currentUser.display_name || currentUser.name).slice(0, 1).toUpperCase() : <UserRound size={18} />}</span><span className="profile-label"><strong>{currentUser?.display_name || currentUser?.name || (user ? user : '访客')}</strong><small>{currentUser ? '团队工作空间' : '选择或添加你的身份'}</small></span><Settings2 size={16} /></button>
      </div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setMobile(true)}><Menu size={20} /></button>{collapsed && <button className="icon-button desktop-expand" aria-label="展开侧栏" onClick={toggleSidebar}><PanelLeftOpen size={19} /></button>}<span className="topbar-title">{heading}</span><ChevronRight size={13} className="topbar-chevron" /><span className="topbar-subtitle">{route.page === 'work' ? '专注当下的这件事' : '做事，也留下认知'}</span></div>
      <div className="topbar-right">{route.page === 'work' ? <button className={`icon-button ${inspector ? 'active' : ''}`} aria-label={inspector ? '收起认知库面板' : '打开认知库面板'} title="认知库" onClick={() => setInspector(!inspector)}>{inspector ? <PanelRightClose size={19} /> : <PanelRightOpen size={19} />}</button> : <span className="topbar-edition"><span className="mini-dot" />memory.talk</span>}</div>
    </header>
      <div className="main-layout"><main id="main-content" tabIndex={-1} className={`main-content page-${route.page}`}>
        {route.page === 'home' ? <Home /> : route.page === 'work' && route.work ? <Workspace key={route.work} id={route.work} onLibrary={() => setInspector(true)} /> : route.page === 'library' ? <Library key={route.layer || 'card'} layer={route.layer} path={route.path} onSelect={selection => navigate({ page: 'library', ...selection })} /> : <Settings />}
      </main>
      {route.page === 'work' && inspector && <aside className="inspector" aria-label="认知库面板"><div className="inspector-heading"><span><BookOpen size={17} />认知库</span><div><button className="icon-button small" aria-label="在主页面打开认知库" onClick={() => navigate({ page: 'library', ...selection })}><ArrowUpRight size={16} /></button><button className="icon-button small" aria-label="关闭认知库面板" onClick={() => setInspector(false)}><X size={17} /></button></div></div><Library compact {...selection} onSelect={setSelection} work={route.work} /></aside>}
      </div>
    </div>
    <SearchWorks open={search} onClose={() => setSearch(false)} />
  </div>;
}
function PlusHint() { return <span className="nav-plus">＋</span>; }
function SearchWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  const works = useWorks(); const [term, setTerm] = useState('');
  const filtered = flattenWorks(works.data || []).filter(work => work.goal.toLocaleLowerCase().includes(term.toLocaleLowerCase())).sort((a, b) => b.created_at.localeCompare(a.created_at));
  return <Modal open={open} onClose={onClose} title="搜索工作"><div className="search-dialog-field"><Search size={18} /><input autoFocus value={term} onChange={e => setTerm(e.target.value)} placeholder="输入工作名称…" aria-label="搜索工作名称" /></div><div className="search-work-results">
    {works.isError ? <ErrorState error={works.error} /> : filtered.length ? filtered.map(work => <button key={work.id} onClick={() => { navigate({ page: 'work', work: work.id }); onClose(); }}><GitBranch size={17} /><span>{work.goal}</span><small>{statusLabels[work.status]}</small></button>) : <p className="muted">{works.isPending ? '正在加载工作…' : '没有找到匹配的工作。'}</p>}
  </div></Modal>;
}
