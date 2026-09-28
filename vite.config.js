import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  plugins: [tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: {
    port: 5173,
    proxy: {
      // Model controls belong to Spark. The local API runs in observation mode.
      '/api/inference': { target: process.env.SPARK_DEBUG_API_URL || 'http://spark-82.tailb7a50b.ts.net:7000', changeOrigin: true },
      '/api': process.env.LOCAL_API_URL || 'http://127.0.0.1:4176',
    },
  },
});
