// 화면이 바뀔 때 새 화면이 아래에서 살짝 떠오르며 나타나게 한다.
// 주소(pathname)를 key로 써서, 주소가 바뀌면 React가 새 요소로 보고 모션을 다시 재생한다.

import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const reduce = useReducedMotion()

  return (
    <motion.div
      key={pathname}
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}
