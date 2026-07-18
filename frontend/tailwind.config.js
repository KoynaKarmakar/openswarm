/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"IBM Plex Sans"', 'ui-sans-serif', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // IDBI Bank brand (Orange Passion / Observatory teal) — extended for a
        // dark ops-console UI, not a retail app.
        surface: { base: '#0B1220', panel: '#121B2E', panelHover: '#17223A' },
        ink: { primary: '#EDEFF3', secondary: '#C3C9D6', muted: '#8A93A6' },
        hairline: '#232E45',
        focusRing: '#4FA8FF', // keyboard focus outline ONLY — never decorative
        accent: {
          verified: '#00836C', verifiedDim: '#0A5A4C',    // compliant/verified/passed/resolved ONLY
          flagged: '#F58220', flaggedDim: '#7A4415',       // flagged/pending/attention/under-review ONLY
          critical: '#D64545', criticalDim: '#5C2323',     // hard-fail/critical fraud ONLY — never generic errors
        },
        // Neutral interactive accent for buttons/links — NOT a status color,
        // so it never competes with accent.verified / accent.flagged / accent.critical.
        brand: { 50: '#eef4f9', 100: '#d9e6f0', 200: '#b3cde1', 300: '#82abc7', 400: '#5689a9', 500: '#3E7CB1', 600: '#2F6491', 700: '#254F74', 800: '#1C3C58', 900: '#13293D' },
      },
    },
  },
  plugins: [],
}
