import react from '@vitejs/plugin-react'
import { seedDesignPlugin } from '@seed-design/vite-plugin'
import { defineConfig } from 'vite'

// 백엔드(apps/api) 주소. 화면은 /api로만 요청하고, 개발 서버가 여기로 넘긴다.
// 같은 출처로 보이게 해야 세션 쿠키가 그대로 오간다 (API 명세 3장).
const apiTarget = process.env.A2D_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    // 시연 영상을 일정하게 찍기 위해 라이트 모드로 고정한다.
    seedDesignPlugin({ colorMode: 'light-only' }),
  ],
  resolve: {
    // tsconfig의 "seed-design/*" 경로 별칭을 Vite도 따르게 한다.
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
    },
  },
})
