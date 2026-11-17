import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: './', // Relative paths so the bundle can be hosted on any subpath or URL
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  }
})
