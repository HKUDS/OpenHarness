// Convert mermaid code blocks to mermaid-block elements
// Auto-loads mermaid-block component and converts all mermaid code blocks

(function() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', convertMermaidBlocks);
  } else {
    convertMermaidBlocks();
  }
})();

function convertMermaidBlocks() {
  const codeBlocks = document.querySelectorAll('code[data-language="mermaid"], code.language-mermaid');
  console.log('[mermaid-convert] Found', codeBlocks.length, 'mermaid code blocks');

  codeBlocks.forEach((codeEl) => {
    const preEl = codeEl.closest('pre');
    if (!preEl) {
      console.warn('[mermaid-convert] Code element has no pre parent');
      return;
    }

    const definition = codeEl.textContent || '';

    const mermaidBlock = document.createElement('mermaid-block');
    mermaidBlock.dataset.definition = definition;

    preEl.parentNode?.replaceChild(mermaidBlock, preEl);
  });
}
