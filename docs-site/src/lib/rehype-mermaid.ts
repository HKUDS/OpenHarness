import { visit } from 'unist-util-visit';
import type { Root, Element } from 'hast';
import {h} from 'hastscript';

export function rehypeMermaid() {
  return (tree: Root) => {
    let count = 0;
    visit(tree, 'element', (node: Element, index, parent: any) => {
      if (node.tagName !== 'pre') return;

      // Support both Shiki's data-language and direct className check
      const dataLang = node.properties?.dataLanguage as string | string[] | undefined;
      const lang = Array.isArray(dataLang) ? dataLang[0] : dataLang;
      const classNames = node.properties?.className as string[] | undefined;
      const hasLangClass = classNames?.some(c => c.startsWith('language-') || c === 'mermaid');

      if (lang !== 'mermaid' && !hasLangClass) return;

      // Extract text content
      const codeEl = node.children.find((c): c is Element => (c as Element).tagName === 'code');
      const textContent = codeEl ? getTextContent(codeEl) : '';

      const mermaidEl = h('mermaid-block', { 'data-definition': textContent });

      if (parent && typeof index === 'number') {
        parent.children.splice(index, 1, mermaidEl);
        count++;
      }
    });
    console.log('[rehype-mermaid] Converted', count, 'mermaid blocks');
  };
}

function getTextContent(node: any): string {
  if (node.type === 'text') return node.value || '';
  if (node.children) return node.children.map(getTextContent).join('');
  return '';
}
