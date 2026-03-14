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
      },
      themes: {
        light: {
          colors: {
            primary: {
              DEFAULT: '#FF7FAC',
              foreground: '#fff',
              50: '#FFF0F5',
              100: '#FFE4E9',
              200: '#FFCDD9',
              300: '#FF9EB5',
              400: '#FF7FAC',
              500: '#F33B7C',
              600: '#C92462',
              700: '#991B4B',
              800: '#691233',
              900: '#380A1B',
            },
            secondary: {
              DEFAULT: '#88C0D0',
              foreground: '#fff',
            },
          },
        },
        dark: {
          colors: {
            primary: {
              DEFAULT: '#f31260',
              foreground: '#fff',
              50: '#310413',
              100: '#610726',
              200: '#920b3a',
              300: '#c20e4d',
              400: '#f31260',
              500: '#f54180',
              600: '#f871a0',
              700: '#faa0bf',
              800: '#fdd0df',
              900: '#fee7ef',
            },
            secondary: {
              DEFAULT: '#88C0D0',
              foreground: '#fff',
            },
          },
        },
      },
    }),
  ],
}
