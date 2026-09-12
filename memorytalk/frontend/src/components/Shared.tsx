import { Dialog } from '@base-ui-components/react/dialog';
import { AlertCircle, ArrowUpRight, LoaderCircle, X } from 'lucide-react';
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';

export function Logo({ small = false }: { small?: boolean }) {
  return <span className={cn('logo-mark', small && 'small')} aria-hidden="true"><span /><span /><span /></span>;
}
export function Loading({ label = '正在加载…' }: { label?: string }) {
  return <div className="state-box" role="status"><LoaderCircle className="spin" size={20} /><span>{label}</span></div>;
}
export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return <div className="error-state" role="alert"><AlertCircle size={19} /><div><p>{error instanceof Error ? error.message : '加载失败，请稍后重试。'}</p>{retry && <button className="text-button" onClick={retry}>重新加载</button>}</div></div>;
}
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return <div className="empty-state">{icon && <div className="empty-icon">{icon}</div>}<h3>{title}</h3>{children}</div>;
}
export function Modal({ open, onClose, title, description, children }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode;
}) {
  return <Dialog.Root open={open} onOpenChange={value => { if (!value) onClose(); }}>
    <Dialog.Portal><Dialog.Backdrop className="modal-backdrop" /><Dialog.Popup className="modal">
      <div className="modal-heading"><Dialog.Title>{title}</Dialog.Title><Dialog.Close className="icon-button" aria-label="关闭对话框"><X size={19} /></Dialog.Close></div>
      {description && <Dialog.Description className="muted modal-description">{description}</Dialog.Description>}
      {children}
    </Dialog.Popup></Dialog.Portal>
  </Dialog.Root>;
}
export function Markdown({ text }: { text: string }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}<ArrowUpRight size={12} className="inline-icon" /></a>,
  }}>{text}</ReactMarkdown></div>;
}
export function safeWindowUrl(raw?: string | null): string | null {
  if (!raw) return null;
  try { const url = new URL(raw, window.location.origin); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
