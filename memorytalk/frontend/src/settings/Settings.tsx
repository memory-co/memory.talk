import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, ChevronRight, CircleHelp, Languages, LoaderCircle, Plus, Server, Settings2, Terminal, UserRound } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/query';
import { useSystem, useUsers } from '@/lib/queries';
import { usePreferences } from '@/lib/store';
import { locales, useT } from '@/lib/i18n';
import type { User } from '@/lib/types';
import { ErrorState, Loading, Modal, UserAvatar } from '@/components/Shared';

export function Settings() {
  const t = useT();
  const users = useUsers();
  const system = useSystem();
  const user = usePreferences(s => s.user);
  const setUser = usePreferences(s => s.setUser);
  const locale = usePreferences(s => s.locale);
  const setLocale = usePreferences(s => s.setLocale);
  const [register, setRegister] = useState(false);
  return <div className="settings-page"><div className="page-heading"><div><span className="eyebrow">MAKE IT YOURS</span><h1>{t('nav.settings')}</h1><p>{t('settings.subtitle')}</p></div><div className="library-mark"><Settings2 size={25} /></div></div>
    <section className="settings-section"><h2><UserRound size={17} />{t('settings.identity')}</h2><p className="muted">{t('settings.identityText')}</p>
      {users.isPending ? <Loading /> : users.isError ? <ErrorState error={users.error} retry={() => { void users.refetch(); }} /> : <div className="user-list">
        <Button variant="ghost" className={`user-option h-auto whitespace-normal ${!user ? 'selected' : ''}`} onClick={() => setUser('')}><UserAvatar><UserRound size={17} /></UserAvatar><span><strong>{t('user.guest')}</strong><small>{t('settings.anonymous')}</small></span>{!user && <Check size={17} />}</Button>
        {users.data.map(item => <Button variant="ghost" key={item.name} className={`user-option h-auto whitespace-normal ${user === item.name ? 'selected' : ''}`} onClick={() => setUser(item.name)}><UserAvatar>{(item.display_name || item.name).slice(0, 1).toUpperCase()}</UserAvatar><span><strong>{item.display_name || item.name}</strong><small>{item.name}{item.email ? ` · ${item.email}` : ''}</small></span>{user === item.name && <Check size={17} />}</Button>)}
        <Button variant="ghost" className="add-user h-auto whitespace-normal" onClick={() => setRegister(true)}><Plus size={16} />{t('settings.addMember')}<ChevronRight size={15} /></Button>
      </div>}
    </section>
    <section className="settings-section"><h2><Languages size={17} />{t('settings.language')}</h2><p className="muted">{t('settings.languageText')}</p>
      <div className="user-list">{locales.map(item => <Button variant="ghost" key={item.value} className={`user-option h-auto whitespace-normal ${locale === item.value ? 'selected' : ''}`} onClick={() => setLocale(item.value)} aria-pressed={locale === item.value}><span><strong>{item.label}</strong></span>{locale === item.value && <Check size={17} />}</Button>)}</div>
    </section>
    <section className="settings-section"><h2><Server size={17} />{t('settings.environment')}</h2>
      {system.isPending ? <Loading /> : system.isError ? <ErrorState error={system.error} retry={() => { void system.refetch(); }} /> : <dl className="system-details"><div><dt>{t('settings.serviceStatus')}</dt><dd><span className="connected"><span className="live-dot" />{t('settings.connected')}</span></dd></div><div><dt>{t('settings.workspace')}</dt><dd>{system.data.workspace}</dd></div><div><dt>{t('settings.home')}</dt><dd>{system.data.home}</dd></div><div><dt>{t('settings.store')}</dt><dd>{system.data.store.backend}</dd></div><div><dt>{t('settings.ttyd')}</dt><dd>{system.data.ttyd_url || t('settings.notConfigured')}</dd></div></dl>}
    </section>
    <section className="settings-section"><h2><Terminal size={17} />{t('settings.ttyd')}</h2><p className="muted">{t('settings.ttydText')}</p>
      <div className="setup-note"><CircleHelp size={18} /><div><strong>{t('settings.ttydTitle')}</strong><p>{t('settings.ttydHow')}</p><code>MEMORY_TALK_TTYD_URL={t('settings.ttydExample')}</code><p>{t('settings.ttydArg')} <code>?arg=&lt;session_id&gt;</code>{t('settings.ttydSocket')}<code>{system.data?.tmux_socket || 'memorytalk'}</code>{t('settings.ttydRestart')}</p></div></div>
    </section>
    <footer className="settings-footer">memory.talk <span>{t('settings.footer')}</span></footer>
    <RegisterUser open={register} onClose={() => setRegister(false)} />
  </div>;
}
function RegisterUser({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const [name, setName] = useState(''); const [display, setDisplay] = useState(''); const [email, setEmail] = useState('');
  const setUser = usePreferences(s => s.setUser);
  const mutation = useMutation({ mutationFn: () => api<User>('/users', { method: 'POST', body: { name: name.trim(), display_name: display.trim(), email: email.trim() } }),
    onSuccess: data => { setUser(data.name); void queryClient.invalidateQueries({ queryKey: ['users'] }); onClose(); setName(''); setDisplay(''); setEmail(''); toast.success(t('settings.added')); },
  });
  return <Modal open={open} onClose={() => { if (!mutation.isPending) { mutation.reset(); onClose(); } }} title={t('settings.addMember')} description={t('settings.addMemberText')}>
    <form className="form-stack" onSubmit={e => { e.preventDefault(); mutation.mutate(); }}><Label>{t('settings.username')}<Input aria-label={t('settings.username')} value={name} onChange={e => setName(e.target.value)} autoFocus required pattern="[A-Za-z0-9_.\-]{1,64}" placeholder="alice" /><span className="field-hint">{t('settings.usernameHint')}</span></Label><Label>{t('settings.displayName')}<Input value={display} onChange={e => setDisplay(e.target.value)} placeholder={t('settings.displayNamePlaceholder')} /></Label><Label>{t('settings.email')}<Input type="email" value={email} onChange={e => setEmail(e.target.value)} /></Label>
      {mutation.isError && <ErrorState error={mutation.error} />}<div className="form-actions"><Button variant="default" disabled={!name.trim() || mutation.isPending}>{mutation.isPending && <LoaderCircle size={15} className="spin" />}{t('settings.addAndUse')}</Button></div>
    </form>
  </Modal>;
}
