// MermaidBlock Web Component
// Usage: <mermaid-block data-definition="graph TD; A-->B;"></mermaid-block>

class MermaidBlock extends HTMLElement {
  async connectedCallback() {
    const definition = this.dataset.definition || '';
    if (!definition) return;

    this.innerHTML = '<div class="mermaid-loading text-gray-400 text-sm p-4">Rendering diagram...</div>';

    try {
      const mermaid = (await import('mermaid')).default;

      const isDark = document.documentElement.classList.contains('dark');
      mermaid.initialize({
        startOnLoad: false,
        theme: isDark ? 'dark' : 'default',
        securityLevel: 'loose',
        fontFamily: 'inherit',
      });

      const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
      const { svg } = await mermaid.render(id, definition);

      this.innerHTML = `
        <div class="mermaid svg-container flex justify-center p-4 bg-white dark:bg-gray-900 rounded-lg overflow-x-auto">
          ${svg}
        </div>
      `;

      // Re-render on theme change
      const observer = new MutationObserver(() => {
        this.reinitialize();
      });
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class'],
      });
    } catch (e: any) {
      this.innerHTML = `
        <pre class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-4 overflow-x-auto text-sm text-red-700 dark:text-red-300">${escapeHtml(definition)}</pre>
        <p class="text-red-500 text-xs mt-1">Diagram error: ${escapeHtml(e.message)}</p>
      `;
    }
  }

  async reinitialize() {
    const definition = this.dataset.definition || '';
    if (!definition) return;

    try {
      const mermaid = (await import('mermaid')).default;
      const isDark = document.documentElement.classList.contains('dark');
      mermaid.initialize({
        startOnLoad: false,
        theme: isDark ? 'dark' : 'default',
        securityLevel: 'loose',
        fontFamily: 'inherit',
      });

      const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
      const { svg } = await mermaid.render(id, definition);

      const container = this.querySelector('.svg-container');
      if (container) {
        container.innerHTML = svg;
      }
    } catch {
      // silently fail on reinit
    }
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

customElements.define('mermaid-block', MermaidBlock);
