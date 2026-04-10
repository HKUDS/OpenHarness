import { useEffect, useRef, useState } from 'react';

interface MermaidBlockProps {
  definition: string;
  className?: string;
}

export default function MermaidBlock({ definition, className = '' }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function renderMermaid() {
      if (!containerRef.current) return;

      try {
        const mermaid = (await import('mermaid')).default;

        const isDark = document.documentElement.classList.contains('dark');
        mermaid.initialize({
          startOnLoad: false,
          theme: isDark ? 'dark' : 'default',
          securityLevel: 'loose',
        });

        const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
        const { svg } = await mermaid.render(id, definition);

        if (mounted && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setLoading(false);
          setError(false);
        }
      } catch (e) {
        console.error('Mermaid render error:', e);
        if (mounted) {
          setLoading(false);
          setError(true);
        }
      }
    }

    renderMermaid();

    // Re-render on theme change
    const observer = new MutationObserver(() => {
      renderMermaid();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    return () => {
      mounted = false;
      observer.disconnect();
    };
  }, [definition]);

  if (error) {
    return (
      <pre className={`bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-4 overflow-x-auto text-sm ${className}`}>
        <code>{definition}</code>
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`mermaid-block flex items-center justify-center bg-white dark:bg-gray-900 rounded-lg p-4 overflow-x-auto ${className}`}
    >
      {loading && (
        <div className="animate-pulse text-gray-400 text-sm">Rendering diagram...</div>
      )}
    </div>
  );
}
