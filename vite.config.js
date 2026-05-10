import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  // If building the SDK library
  if (mode === 'sdk') {
    return {
      build: {
        lib: {
          entry: resolve(__dirname, 'src/sdk/index.js'),
          name: 'Entropy',
          fileName: (format) => `entropy.${format === 'umd' ? '' : format + '.'}js`,
          formats: ['umd'] // For easy <script> inclusion
        },
        outDir: 'public/sdk',
        emptyOutDir: false, // Don't wipe the directory as it contains our public assets
        minify: 'esbuild',
      }
    }
  }

  // Standard React App build
  return {
    plugins: [react()],
    build: {
      target: 'esnext',
      minify: 'esbuild',
      sourcemap: process.env.NODE_ENV === 'production' ? false : true,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            tensorflow: ['@tensorflow/tfjs'],
          }
        }
      }
    },
    server: {
      port: 3000,
      strictPort: false,
      proxy: {
        '/api': {
          target: process.env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
          timeout: 30000
        }
      }
    },
    preview: {
      port: 3000
    }
  }
})
