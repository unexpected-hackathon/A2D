// 화면 안의 흰 카드. 모든 카드가 같은 둥글기·그림자·안쪽 여백을 쓰도록 한 곳에서 정한다.

import { Box, type BoxProps } from '@seed-design/react'

export function Surface(props: BoxProps) {
  return (
    <Box
      bg="bg.layerDefault"
      borderRadius="r4"
      borderWidth={1}
      borderColor="stroke.neutralSubtle"
      boxShadow="s1"
      p="x5"
      {...props}
    />
  )
}
