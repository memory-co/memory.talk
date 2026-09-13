import { useDialogFocus } from '@/hooks/use-dialog-focus';
import { AlertCircle, LoaderCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { lazy, Suspense } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

export function Logo({ className }: { className?: string }) {
  return <span className={cn('inline-flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground', className)} aria-hidden="true">
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 17V9" /><path d="M12 17V5" /><path d="M18 17v-6" /></svg>
  </span>;
}
export function UserAvatar({ children, className }: { children: ReactNode; className?: string }) {
  return <Avatar className={cn('h-8 w-8 shrink-0 rounded-lg', className)}><AvatarFallback className="rounded-lg bg-muted text-xs">{children}</AvatarFallback></Avatar>;
}
export function Loading({ label }: { label?: string }) {
  const t = useT();
  return <div className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground" role="status"><LoaderCircle className="h-4 w-4 animate-spin" /><span>{label ?? t('common.loading')}</span></div>;
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const t = useT();
  return <Alert variant="destructive" className="my-3"><AlertCircle className="h-4 w-4" /><AlertDescription>{error instanceof Error ? error.message : t('common.loadFailed')}{retry && <Button variant="link" size="sm" className="ml-2 h-auto p-0 text-destructive" onClick={retry}>{t('common.reload')}</Button>}</AlertDescription></Alert>;
}
export function Empty({ icon, title, children, className }: { icon?: ReactNode; title: string; children?: ReactNode; className?: string }) {
  return <div className={cn('flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center', className)}>
    {icon && <div className="mb-1 flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">{icon}</div>}
    <h3 className="text-base font-medium">{title}</h3>
    <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground [&>p]:max-w-sm">{children}</div>
  </div>;
}
export function Modal({ open, onClose, title, description, children }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode;
}) {
  const focus = useDialogFocus();
  return <Dialog open={open} onOpenChange={value => { if (!value) onClose(); }}>
    <DialogContent {...focus}>
      <DialogHeader className="pr-6 text-left"><DialogTitle>{title}</DialogTitle><DialogDescription className={description ? '' : 'sr-only'}>{description || title}</DialogDescription></DialogHeader>
      {children}
    </DialogContent>
  </Dialog>;
}
const MarkdownContent = lazy(() => import('./Markdown').then(module => ({ default: module.Markdown })));
export function Markdown({ text }: { text: string }) {
  const t = useT();
  return <Suspense fallback={<Loading label={t('common.loadingBody')} />}><MarkdownContent text={text} /></Suspense>;
}
export function safeWindowUrl(raw?: string | null): string | null {
  if (!raw) return null;
  try { const url = new URL(raw, window.location.origin); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
