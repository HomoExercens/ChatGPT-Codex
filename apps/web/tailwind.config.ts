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
      },
      borderRadius: {
        xl: '1rem',
        '2xl': '1.5rem',
        '3xl': '2rem',
      },
    },
  },
  plugins: [],
} satisfies Config;
