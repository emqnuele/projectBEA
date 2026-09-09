import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// this config is an ES module, where __dirname does not exist
const here = (file) => fileURLToPath(new URL(file, import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // two entry points, not one app with a route: the OBS browser source runs
      // for a whole stream and must not carry React, the router or the dashboard
      input: {
        main: here('./index.html'),
        stage: here('./stage.html'),
      },
    },
  },
})
