/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2563eb',
          hover: '#1d4ed8',
          light: '#dbeafe',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f8fafc',
        },
        border: '#e2e8f0',
        text: {
          DEFAULT: '#0f172a',
          muted: '#64748b',
        },
        danger: {
          DEFAULT: '#dc2626',
          light: '#fee2e2',
        },
      },
    },
  },
  plugins: [],
}
