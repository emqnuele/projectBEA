import { resolve } from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // two entry points, not one page with a route: the OBS browser source runs
      // for a whole stream and must not carry React, the router or the dashboard
      input: {
        main: resolve(__dirname, 'index.html'),
        stage: resolve(__dirname, 'stage.html'),
      },
    },
  },
})
