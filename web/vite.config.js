import { defineConfig } from "vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  base: '/',
  plugins: [TanStackRouterVite({ autoCodeSplitting: true }), viteReact(), tailwindcss()],
  test: {
    globals: true,
    environment: "jsdom",
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      'plotly.js/dist/plotly': path.resolve(__dirname, './node_modules/plotly.js/dist/plotly.js')
    }
  },
  server: {
    host: '0.0.0.0',
    port: 8080
  },
  optimizeDeps: {
    include: ['d3-array', '@d3fc/d3fc-technical-indicator', 'plotly.js', 'plotly.js/dist/plotly'],
    exclude: ['@finos/perspective', '@finos/perspective-viewer', '@finos/perspective-viewer-d3fc']
  },
  build: {
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks: undefined,
        format: 'es'
      }
    },
    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true
    }
  }
});
