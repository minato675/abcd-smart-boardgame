import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv, type ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // 프론트가 실제로 요청하는 접두어. src/config/env.ts 의 API_BASE_URL 과 같아야 한다.
  const apiPrefix = env.VITE_API_BASE_URL || '/inte'
  const apiTarget = env.VITE_DEV_API_TARGET || 'http://localhost:8111'

  /*
   * inte-server 에는 CORS 설정이 전혀 없어서 :5173 → :8111 직접 호출은
   * 브라우저가 막는다. dev 서버가 같은 오리진에서 프록시해 우회한다.
   * 백엔드에 context-path 가 없으므로 rewrite 로 접두어를 벗겨야 한다.
   */
  const proxy: Record<string, ProxyOptions> = {}
  if (apiPrefix.startsWith('/') && apiPrefix.length > 1) {
    proxy[apiPrefix] = {
      target: apiTarget,
      changeOrigin: true,
      rewrite: (path) => path.slice(apiPrefix.length) || '/',
    }
  }

  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: { proxy },
  }
})
