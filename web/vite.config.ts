import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `npm run build` writes into the Python package, so `./app serve` serves the built app.
// `npm run dev` runs the dev server with hot reload and proxies /api to a running `./app serve` (port 8360).
export default defineConfig({
  base: './',       // relative asset paths, so the app works at the server's root and behind a reverse proxy at a path (the server's <base> tag and api.ts BASE do the same for routes and the API)
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../src/app/server/static',
    emptyOutDir: true,
    // One bundle of about 520 kB (160 kB gzipped), most of it React, React Router, TanStack and Strata. A local app loads it once; split routes with lazy() when that stops being true.
    chunkSizeWarningLimit: 1000,
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8360' } },
})
