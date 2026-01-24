import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        bg: 'rgb(var(--nl-bg) / <alpha-value>)',
        fg: 'rgb(var(--nl-fg) / <alpha-value>)',
        muted: 'rgb(var(--nl-fg-muted) / <alpha-value>)',
        subtle: 'rgb(var(--nl-fg-subtle) / <alpha-value>)',
        border: 'rgb(var(--nl-border) / <alpha-value>)',
        ring: 'rgb(var(--nl-ring) / <alpha-value>)',
        surface: {
          1: 'rgb(var(--nl-surface-1) / <alpha-value>)',
          2: 'rgb(var(--nl-surface-2) / <alpha-value>)',
          3: 'rgb(var(--nl-surface-3) / <alpha-value>)',
        },
        brand: {
          50: 'rgb(var(--nl-brand-50) / <alpha-value>)',
          100: 'rgb(var(--nl-brand-100) / <alpha-value>)',
          200: 'rgb(var(--nl-brand-200) / <alpha-value>)',
          300: 'rgb(var(--nl-brand-300) / <alpha-value>)',
          400: 'rgb(var(--nl-brand-400) / <alpha-value>)',
          500: 'rgb(var(--nl-brand-500) / <alpha-value>)',
          600: 'rgb(var(--nl-brand-600) / <alpha-value>)',
          700: 'rgb(var(--nl-brand-700) / <alpha-value>)',
          900: 'rgb(var(--nl-brand-900) / <alpha-value>)',
        },
        lab: {
          50: 'rgb(var(--nl-lab-50) / <alpha-value>)',
          900: 'rgb(var(--nl-lab-900) / <alpha-value>)',
        },
        accent: {
          200: 'rgb(var(--nl-accent-200) / <alpha-value>)',
          500: 'rgb(var(--nl-accent-500) / <alpha-value>)',
          700: 'rgb(var(--nl-accent-700) / <alpha-value>)',
        },
        success: {
          500: 'rgb(var(--nl-success-500) / <alpha-value>)',
        },
        warning: {
          500: 'rgb(var(--nl-warning-500) / <alpha-value>)',
        },
        danger: {
          500: 'rgb(var(--nl-danger-500) / <alpha-value>)',
        },
      },
      borderRadius: {
        xl: 'var(--nl-radius-sm)',
        '2xl': 'var(--nl-radius-md)',
        '3xl': 'var(--nl-radius-lg)',
      },
      boxShadow: {
        glass: 'var(--nl-shadow-glass)',
        depth: 'var(--nl-shadow-depth)',
        'glow-brand': '0 0 22px rgb(var(--nl-brand-500) / 0.22)',
      },
    },
  },
  plugins: [],
} satisfies Config;
