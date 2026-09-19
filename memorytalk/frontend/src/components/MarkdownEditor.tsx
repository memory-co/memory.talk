import { useEffect, useRef } from 'react';
import { Crepe } from '@milkdown/crepe';
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

/** 正文的读写都用它:Milkdown Crepe(所见即所得的 Markdown,ProseMirror 之上),readOnly 就是阅读视图,这样读写渲染一致。
 *  非受控:挂载时用 value 初始化,之后只往外报 onChange;要换内容就换 key 重新挂。颜色跟着 shadcn token 走(index.css 里映射)。 */
export default function MarkdownEditor({ value, onChange, placeholder, readOnly = false, className }: {
  value: string; onChange?: (markdown: string) => void; placeholder?: string; readOnly?: boolean; className?: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  const crepe = useRef<Crepe | null>(null);
  const change = useRef(onChange); change.current = onChange;
  const initial = useRef({ value, placeholder, readOnly });
  useEffect(() => {
    if (!root.current) return;
    const { value: defaultValue, placeholder: text, readOnly: ro } = initial.current;
    const editor = new Crepe({ root: root.current, defaultValue, features: { [Crepe.Feature.Latex]: false, [Crepe.Feature.AI]: false, ...(ro ? { [Crepe.Feature.BlockEdit]: false, [Crepe.Feature.Toolbar]: false, [Crepe.Feature.Placeholder]: false } : {}) }, featureConfigs: { [Crepe.Feature.Placeholder]: { text: text || '', mode: 'doc' } } });
    editor.on(api => { api.markdownUpdated((_ctx, markdown) => change.current?.(markdown)); });
    let alive = true;
    void editor.create().then(() => { if (!alive) { void editor.destroy(); return; } editor.setReadonly(ro); crepe.current = editor; });
    return () => { alive = false; crepe.current = null; void editor.destroy(); };
  }, []);
  useEffect(() => { crepe.current?.setReadonly(readOnly); }, [readOnly]);
  return <div ref={root} className={className} />;
}
