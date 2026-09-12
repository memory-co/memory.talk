import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, ChevronRight, CircleHelp, LoaderCircle, Plus, Server, Settings2, Terminal, UserRound } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem, useUsers } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import type { User } from '@/lib/types';
import { ErrorState, Loading, Modal, UserAvatar } from '@/components/Shared';

export function Settings() {
  const users = useUsers();
  const system = useSystem();
  const user = usePreferences(s => s.user);
  const setUser = usePreferences(s => s.setUser);
  const [register, setRegister] = useState(false);
  return <div className="settings-page"><div className="page-heading"><div><span className="eyebrow">MAKE IT YOURS</span><h1>设置</h1><p>选择你的身份，连接你的工作环境。</p></div><div className="library-mark"><Settings2 size={25} /></div></div>
    <section className="settings-section"><h2><UserRound size={17} />当前身份</h2><p className="muted">用于标记工作参与者和认知库的提交作者。</p>
      {users.isPending ? <Loading /> : users.isError ? <ErrorState error={users.error} retry={() => { void users.refetch(); }} /> : <div className="user-list">
        <Button variant="ghost" className={`user-option h-auto whitespace-normal ${!user ? 'selected' : ''}`} onClick={() => setUser('')}><UserAvatar><UserRound size={17} /></UserAvatar><span><strong>访客</strong><small>暂不署名</small></span>{!user && <Check size={17} />}</Button>
        {users.data.map(item => <Button variant="ghost" key={item.name} className={`user-option h-auto whitespace-normal ${user === item.name ? 'selected' : ''}`} onClick={() => setUser(item.name)}><UserAvatar>{(item.display_name || item.name).slice(0, 1).toUpperCase()}</UserAvatar><span><strong>{item.display_name || item.name}</strong><small>{item.name}{item.email ? ` · ${item.email}` : ''}</small></span>{user === item.name && <Check size={17} />}</Button>)}
        <Button variant="ghost" className="add-user h-auto whitespace-normal" onClick={() => setRegister(true)}><Plus size={16} />添加团队成员<ChevronRight size={15} /></Button>
      </div>}
    </section>
    <section className="settings-section"><h2><Server size={17} />工作环境</h2>
      {system.isPending ? <Loading /> : system.isError ? <ErrorState error={system.error} retry={() => { void system.refetch(); }} /> : <dl className="system-details"><div><dt>服务状态</dt><dd><span className="connected"><span className="live-dot" />已连接</span></dd></div><div><dt>默认工作目录</dt><dd>{system.data.workspace}</dd></div><div><dt>数据目录</dt><dd>{system.data.home}</dd></div><div><dt>存储方式</dt><dd>{system.data.store.backend}</dd></div><div><dt>浏览器终端</dt><dd>{system.data.ttyd_url || '尚未配置'}</dd></div></dl>}
    </section>
    <section className="settings-section"><h2><Terminal size={17} />浏览器终端</h2><p className="muted">会话运行在服务端的 tmux 中。配置 ttyd 后，就能在页面里直接输入与操作；未配置时仍可查看终端快照和 agent 会话记录。</p>
      <div className="setup-note"><CircleHelp size={18} /><div><strong>接入现有 ttyd 服务</strong><p>让 ttyd 按会话参数连接同一个 tmux socket，并在启动 memory.talk 前设置浏览器可访问的地址：</p><code>MEMORY_TALK_TTYD_URL=https://你的终端服务地址</code><p>窗口地址会携带 <code>?arg=会话ID</code>。当前 tmux socket：<code>{system.data?.tmux_socket || 'memorytalk'}</code>。修改配置后需要重启后端。</p></div></div>
    </section>
    <footer className="settings-footer">memory.talk <span>做事 · 议事 · 记事</span></footer>
    <RegisterUser open={register} onClose={() => setRegister(false)} />
  </div>;
}
function RegisterUser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState(''); const [display, setDisplay] = useState(''); const [email, setEmail] = useState('');
  const setUser = usePreferences(s => s.setUser);
  const mutation = useMutation({ mutationFn: () => api<User>('/users', { method: 'POST', body: { name: name.trim(), display_name: display.trim(), email: email.trim() } }),
    onSuccess: data => { setUser(data.name); void queryClient.invalidateQueries({ queryKey: ['users'] }); onClose(); setName(''); setDisplay(''); setEmail(''); toast.success('已添加并切换身份'); },
  });
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title="添加团队成员" description="每个人都可以参与工作，身份用于记录贡献。">
    <form className="form-stack" onSubmit={e => { e.preventDefault(); mutation.mutate(); }}><Label>用户名<Input aria-label="用户名" value={name} onChange={e => setName(e.target.value)} autoFocus required pattern="[A-Za-z0-9_.\-]{1,64}" placeholder="alice" /><span className="field-hint">支持英文字母、数字、下划线、点和连字符。</span></Label><Label>显示名称<Input value={display} onChange={e => setDisplay(e.target.value)} placeholder="如何称呼你" /></Label><Label>邮箱（可选）<Input type="email" value={email} onChange={e => setEmail(e.target.value)} /></Label>
      {mutation.isError && <ErrorState error={mutation.error} />}<div className="form-actions"><Button variant="default" disabled={!name.trim() || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}添加并使用</Button></div>
    </form>
  </Modal>;
}
