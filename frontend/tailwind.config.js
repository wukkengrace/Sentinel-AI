/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sentinel: {
          dark: '#030b16',
          panel: 'rgba(5,12,24,0.9)',
          border: '#0d2535',
          text: '#c8d8e8',
          subtext: '#607080',
          accent: '#2979ff',
          critical: '#ff2d2d',
          success: '#00e676',
          warning: '#f5c518',
        }
      }
    },
  },
  plugins: [],
}
