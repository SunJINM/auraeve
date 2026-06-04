import { heroui } from '@heroui/theme'

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    './node_modules/@heroui/theme/dist/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {},
  },
  plugins: [
    heroui({
      layout: {
        disabledOpacity: '0.3',
        radius: {
          small: '8px',
          medium: '12px',
          large: '18px',
        },
      },
      themes: {
        light: {
          colors: {
            primary: {
              DEFAULT: '#0071e3',
              foreground: '#ffffff',
              50: '#e8f2fd',
              100: '#d1e6fb',
              200: '#a3ccf7',
              300: '#74b3f3',
              400: '#4699ef',
              500: '#0071e3',
              600: '#005bb6',
              700: '#004488',
              800: '#002e5b',
              900: '#00172d',
            },
            secondary: {
              DEFAULT: '#86868b',
              foreground: '#ffffff',
            },
          },
        },
        dark: {
          colors: {
            primary: {
              DEFAULT: '#0a84ff',
              foreground: '#ffffff',
              50: '#00172d',
              100: '#002e5b',
              200: '#004488',
              300: '#005bb6',
              400: '#0071e3',
              500: '#0a84ff',
              600: '#409cff',
              700: '#74b3f3',
              800: '#a3ccf7',
              900: '#d1e6fb',
            },
            secondary: {
              DEFAULT: '#8e8e93',
              foreground: '#ffffff',
            },
          },
        },
      },
    }),
  ],
}
