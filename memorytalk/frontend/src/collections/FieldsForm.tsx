import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, X } from 'lucide-react';
import { useT } from '@/lib/i18n';
import { emptyValue, type FieldSpec } from '@/lib/protocol';

/** 按协议的字段表画表单:每种 type 一种控件,像 Notion 一行的属性面板。值是原始的(字符串 / 数组),保存时再 normalize。 */
export function FieldsForm({ fields, value, onChange, idPrefix }: {
  fields: Record<string, FieldSpec>; value: Record<string, unknown>; onChange: (next: Record<string, unknown>) => void; idPrefix: string;
}) {
  return <div className="grid gap-3">
    {Object.entries(fields).map(([name, spec]) => <div key={name} className="grid gap-1.5">
      <Label htmlFor={`${idPrefix}-${name}`} className="flex items-baseline gap-2 text-xs">{name}{spec.required && <span className="text-destructive">*</span>}{spec.description && <span className="font-normal text-muted-foreground">{spec.description}</span>}</Label>
      <FieldInput id={`${idPrefix}-${name}`} spec={spec} value={value[name]} onChange={v => onChange({ ...value, [name]: v })} />
    </div>)}
  </div>;
}

function FieldInput({ id, spec, value, onChange }: { id: string; spec: FieldSpec; value: unknown; onChange: (v: unknown) => void }) {
  const t = useT();
  const text = (v: unknown) => (v === undefined || v === null ? '' : String(v));
  switch (spec.type) {
    case 'text': return <Textarea id={id} rows={3} value={text(value)} onChange={e => onChange(e.target.value)} />;
    case 'number': return <Input id={id} type="number" value={text(value)} onChange={e => onChange(e.target.value)} className="w-40" />;
    case 'date': return <Input id={id} type="date" value={text(value).slice(0, 10)} onChange={e => onChange(e.target.value)} className="w-48" />;
    case 'bool': return <input id={id} type="checkbox" className="size-4 accent-primary" checked={!!value} onChange={e => onChange(e.target.checked)} />;
    case 'enum': return <Select value={text(value)} onValueChange={onChange}><SelectTrigger id={id} className="w-56"><SelectValue placeholder="—" /></SelectTrigger><SelectContent>{(spec.values || []).map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}</SelectContent></Select>;
    case 'ref': return <Input id={id} value={text(value)} onChange={e => onChange(e.target.value)} placeholder={t('editor.refPlaceholder', { layer: spec.layer || '' })} className="font-mono text-xs" />;
    case 'list': {
      const items = Array.isArray(value) ? value : [];
      const item = spec.item!;
      return <div className="grid gap-2">
        {items.map((v, i) => <div key={i} className="flex items-start gap-2 rounded-md border p-2">
          <div className="min-w-0 flex-1">{item.type === 'object'
            ? <FieldsForm fields={item.fields || {}} value={(v && typeof v === 'object' ? v : {}) as Record<string, unknown>} onChange={next => onChange(items.map((x, j) => (j === i ? next : x)))} idPrefix={`${id}-${i}`} />
            : <FieldInput id={`${id}-${i}`} spec={item} value={v} onChange={next => onChange(items.map((x, j) => (j === i ? next : x)))} />}</div>
          <Button type="button" variant="ghost" size="icon" className="size-7 shrink-0" aria-label={t('editor.remove')} onClick={() => onChange(items.filter((_, j) => j !== i))}><X className="size-3.5" /></Button>
        </div>)}
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => onChange([...items, emptyValue(item)])}><Plus />{t('editor.add')}</Button>
      </div>;
    }
    default: return <Input id={id} value={text(value)} onChange={e => onChange(e.target.value)} />;
  }
}
