// 로그인·등록 화면의 틀. 왼쪽은 브랜드 패널, 오른쪽은 양식 카드.
// 좁은 화면에서는 브랜드 패널을 숨기고 카드만 보인다.

import { Box, Grid, Text, VStack } from '@seed-design/react'
import type { ReactNode } from 'react'
import logoUrl from '../assets/a2d-logo.svg'
import { PageTransition } from './PageTransition'

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <Grid columns={{ base: 1, lg: 2 }} minHeight="100vh">
      <Box display={{ base: 'none', lg: 'flex' }} bg="bg.layerDefault" borderRightWidth={1} borderColor="stroke.neutralSubtle">
        <VStack justify="space-between" p="x12" width="full">
          <img src={logoUrl} alt="A2D" height={44} style={{ alignSelf: 'flex-start' }} />
          <VStack gap="x4" maxWidth="440px">
            <div className="a2d-flow-line" data-running="true" style={{ width: 120 }} aria-hidden="true" />
            <Text as="p" textStyle="t11Bold" color="fg.neutral">
              공격자보다 먼저,
              <br />
              우리 회사의 약한 고리를 봅니다.
            </Text>
            <Text as="p" textStyle="t5Regular" color="fg.neutralMuted">
              소유권을 증명한 도메인만, 읽기 전용으로 점검하고 오늘 고칠 3가지를 알려 드립니다.
            </Text>
          </VStack>
          <Text textStyle="t3Regular" color="fg.neutralSubtle">
            A2D · Attack to Defense
          </Text>
        </VStack>
      </Box>
      <VStack justify="center" align="center" p="x6">
        <Box width="full" maxWidth="420px">
          <PageTransition>{children}</PageTransition>
        </Box>
      </VStack>
    </Grid>
  )
}
