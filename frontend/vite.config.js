import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';

// Resolve real path to avoid Windows symlink/junction issues with Rollup
const realCwd = fs.realpathSync(process.cwd());

export default defineConfig({
  root: realCwd,
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
});
