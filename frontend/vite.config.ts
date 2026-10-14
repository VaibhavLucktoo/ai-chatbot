import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import {defineConfig} from 'vite';

const target = 'http://127.0.0.1:8000';
const proxy = {
  target,
  changeOrigin: true,
  configure(server: any) {
    server.on('proxyReq', (outgoing: any, incoming: any) => {
      // Foreign origins must still be rejected by the backend.
      const origin = incoming.headers.origin;
      if (origin === 'http://127.0.0.1:3000' || origin === 'http://localhost:3000') {
        outgoing.setHeader('Origin', target);
      }
    });
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {alias: {'@': path.resolve(import.meta.dirname, '.')}},
  server: {
    host: '127.0.0.1', port: 3000, strictPort: true,
    hmr: process.env.DISABLE_HMR !== 'true',
    proxy: {'/v1': proxy, '/openapi.json': proxy},
  },
  preview: {
    host: '127.0.0.1', port: 3000, strictPort: true,
    proxy: {'/v1': proxy, '/openapi.json': proxy},
  },
});
