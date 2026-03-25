import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Use relative paths so the app works on GitHub Pages (e.g. username.github.io/repo-name/)
  base: './',
})
