import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import svgr from 'vite-plugin-svgr'

export default defineConfig(({ mode }) => {
  let alias = {
    'src': '/src/',
  }
  if (mode === 'profiling') {
    alias['react-dom$'] = 'react-dom/profiling'
    alias['scheduler/tracing'] = 'scheduler/tracing-profiling'
  }
  return {
    plugins: [react({
      babel: {
        plugins: ['babel-plugin-react-compiler'],
      },
    }), svgr()],
    resolve: {
      alias: alias,
    },
    // https://stackoverflow.com/a/79003101
    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern-compiler'
        }
      }
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'react': ['react', 'react-dom', 'react-dom/client', 'react-router-dom'],
            'd3': ['d3'],
            'vendor': [
              '@fortawesome/react-fontawesome',
              '@fortawesome/free-solid-svg-icons',
              'highlight.js',
              'immutable',
            ]
          }
        }
      }
    }
  }
})
