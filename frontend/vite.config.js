import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rolldownOptions: {
      output: {
        // The shared chunk created by the dynamically imported chart modules is
        // dominated by Recharts. Name it explicitly so build output and network
        // panels are readable; chunk membership and lazy loading are unchanged.
        chunkFileNames(chunk) {
          const containsRecharts = chunk.moduleIds?.some((id) =>
            /node_modules[\\/]recharts[\\/]/.test(id),
          )
          return containsRecharts && !chunk.isDynamicEntry
            ? 'assets/recharts-[hash].js'
            : 'assets/[name]-[hash].js'
        },
      },
    },
  },
})
