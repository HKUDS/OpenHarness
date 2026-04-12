/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'bg-start': 'var(--color-bg-bg-start)',
        'bg-end': 'var(--color-bg-end)',
        'text-primary': 'var(--color-text)',
        'text-secondary': 'var(--color-secondary)',
        'sidebar-bg': 'var(--color-sidebar-bg)',
        'sidebar-bg-dim': 'var(--color-sidebar-bg-dim)',
        border: 'var(--color-border)',
        code: 'var(--gradient-code-start)',
      },
      animation: {
        'fade-in-down': 'fade-in-down 300ms var(--ease-smooth) forwards',
        'fade-in-up': 'fade-in-up 400ms var(--ease-smooth) forwards',
        'slide-in-left': 'slide-in-left 400ms var(--ease-smooth) forwards',
      },
      typography: {
        DEFAULT: {
          css: {
            maxWidth: '75ch',
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
