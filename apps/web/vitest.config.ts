// 테스트 설정. 앱과 같은 Vite 설정(경로 별칭, SEED 플러그인)을 그대로 쓰고 브라우저 대신 jsdom에서 돌린다.

import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: true,
      // SEED 패키지는 안에서 CSS를 불러오므로 Node로 바로 실행하지 않고 Vite로 변환해서 쓴다.
      server: { deps: { inline: [/@seed-design\//] } },
    },
  }),
)
