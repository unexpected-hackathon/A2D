// 앱이 시작되는 곳. CSS를 정해진 순서로 불러오고 <App />을 그린다.
// 순서: SEED 기본 CSS → Pretendard 글꼴 → A2D 브랜드 덮어쓰기 → 전역 스타일

import '@seed-design/css/base.css'
// 시연은 오프라인이라 글꼴을 CDN이 아니라 설치한 패키지 파일에서 불러온다.
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import './theme/brand.css'
import './theme/global.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { LazyMotion, domAnimation } from 'motion/react'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* SEED의 숫자 애니메이션(AnimateNumber)이 쓰는 가벼운 모션 기능을 켠다. */}
    <LazyMotion features={domAnimation}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </LazyMotion>
  </StrictMode>,
)
