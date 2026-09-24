import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // dev: `npm run dev` on :5173 proxies API calls to the FastAPI server
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
