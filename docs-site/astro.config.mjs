// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';
import remarkDocsLinks from './src/lib/remark-docs-links.mjs';

// https://astro.build/config
export default defineConfig({
  integrations: [
    react(),
    tailwind(),
  ],
  output: 'static',
  markdown: {
    shikiConfig: {
      theme: 'github-dark',
    },
    remarkPlugins: [remarkDocsLinks],
  },
  vite: {
    optimizeDeps: {
      include: ['mermaid'],
    },
  },
});