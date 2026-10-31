// 모든 테스트 전에 한 번 실행된다.
// jsdom에 없는 브라우저 기능을 비슷하게 채워, SEED·모션 컴포넌트가 테스트에서도 그려지게 한다.

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// 모션 라이브러리와 SEED가 화면 크기·움직임 줄이기 설정을 물을 때 쓴다.
// 화면 폭 질문(min-width)은 jsdom의 창 폭(기본 1024px, 노트북)으로 답한다.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: (() => {
      const min = /min-width:\s*(\d+)px/.exec(query)
      return min ? window.innerWidth >= Number(min[1]) : false
    })(),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver

// 칩 탭 가로 스크롤(ChipTabsCarousel)이 쓴다.
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}
globalThis.IntersectionObserver ??= IntersectionObserverStub as unknown as typeof IntersectionObserver

Element.prototype.scrollIntoView ??= vi.fn()
