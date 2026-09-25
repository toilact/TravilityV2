import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// base './' để bản build chạy được khi pywebview mở file tĩnh
export default defineConfig({ plugins: [react(), tailwindcss()], base: './' })
