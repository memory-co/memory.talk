import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { AlertCircle, LoaderCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { lazy, Suspense } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

export function Logo({ small = false }: { small?: boolean }) {
  return <span className={cn('logo-mark', small && 'small')} aria-hidden="true"><span /><span /><span /></span>;
}
export function UserAvatar({ children }: { children: ReactNode }) {
  return <Avatar className="h-8 w-8 shrink-0"><AvatarFallback className="bg-accent text-xs text-accent-foreground">{children}</AvatarFallback></Avatar>;
}
export function Loading({ label = '正在加载…' }: { label?: string }) {
  return <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground" role="status"><LoaderCircle className="h-4 w-4 animate-spin" /><span>{label}</span></div>;
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return <Alert variant="destructive" className="my-3"><AlertCircle className="h-4 w-4" /><AlertDescription>{error instanceof Error ? error.message : '加载失败，请稍后重试。'}{retry && <Button variant="link" size="sm" className="ml-2 text-destructive" onClick={retry}>重新加载</Button>}</AlertDescription></Alert>;
}
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return <div className="empty-state">{icon && <div className="empty-icon">{icon}</div>}<h3>{title}</h3>{children}</div>;
}
export function Modal({ open, onClose, title, description, children }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode;
}) {
  const focus = useDialogFocus();
  return <Dialog open={open} onOpenChange={value => { if (!value) onClose(); }}>
    <DialogContent {...focus}>
      <DialogHeader className="pr-6 text-left"><DialogTitle>{title}</DialogTitle><DialogDescription className={description ? 'leading-relaxed' : 'sr-only'}>{description || title}</DialogDescription></DialogHeader>
      {children}
    </DialogContent>
  </Dialog>;
}
const MarkdownContent = lazy(() => import('./Markdown').then(module => ({ default: module.Markdown })));
export function Markdown({ text }: { text: string }) {
  return <Suspense fallback={<Loading label="正在加载正文…" />}><MarkdownContent text={text} /></Suspense>;
}
export function safeWindowUrl(raw?: string | null): string | null {
  if (!raw) return null;
  try { const url = new URL(raw, window.location.origin); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
