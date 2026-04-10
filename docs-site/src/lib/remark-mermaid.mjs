import { visit } from 'unist-util-visit';

export function remarkMermaid() {
  let conversionCount = 0;

  return (tree) => {
    visit(tree, (node, index, parent) => {
      // Only process elements that are code with language-mermaid
      if (node.type !== 'element') return;
      if (node.tagName !== 'code') return;

      const className = node.properties?.className;
      const classArray = Array.isArray(className) ? className : [];

      // Find language class
      const langClass = classArray.find((c) => c && c.startsWith('language-'));
      const lang = langClass ? langClass.replace('language-', '') : '';

      if (lang !== 'mermaid') return;

      // Extract text content
      const textContent = extractText(node);

      // Replace <code class="language-mermaid">...</code> with <mermaid-block>
      const mermaidElement = {
        type: 'element',
        tagName: 'mermaid-block',
        properties: {
          'data-definition': textContent,
        },
        children: [],
      };

      // Replace in parent
      if (parent && typeof index === 'number') {
        parent.children.splice(index, 1, mermaidElement);
        conversionCount++;
      }
    });

    if (conversionCount > 0) {
      console.log(`[remark-mermaid] Converted ${conversionCount} mermaid code blocks`);
    } else {
      console.log('[remark-mermaid] No mermaid blocks found');
    }
  };
}

function extractText(node) {
  if (node.type === 'text') {
    return node.value || '';
  }
  if (node.children && Array.isArray(node.children)) {
    return node.children.map(extractText).join('');
  }
  return '';
}
