import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// `npm run build` writes into the Python package, so `./strata-scan serve` serves the built app.
// `npm run dev` runs the dev server with hot reload and proxies /api to a running `./strata-scan serve` (port 8368).
export default defineConfig(({ mode }) => ({
  base: './',       // relative asset paths, so the app works at the server's root and behind a reverse proxy at a path (the server's <base> tag and api.ts BASE do the same for routes and the API)
  plugins: [
    react(),
    tailwindcss(),
    // The visual suite serves the build as plain files, without the Python server, which gives every page a <base> back to the
    // root (app.py with_base). Without one, /books/1 asks for /books/assets/... and its BASE is /books. The visual build adds it.
    mode === 'visual' && { name: 'root-base', transformIndexHtml: (html: string) => html.replace('<head>', '<head><base href="/">') },
  ],
  build: {
    outDir: '../src/stratascan/server/static',
    emptyOutDir: true,
    // One bundle of about 940 kB (280 kB gzipped), most of it React, React Aria, React Router, TanStack and Strata. A local app loads it once; split routes with lazy() when that stops being true.
    chunkSizeWarningLimit: 1000,
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8368' } },
}))
